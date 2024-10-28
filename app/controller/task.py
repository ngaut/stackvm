import logging
import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, List
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Task as TaskORM
from app.config.settings import LLM_PROVIDER, LLM_MODEL
from app.services import (
    LLMInterface,
    PlanExecutionVM,
    get_step_update_prompt,
    parse_step,
    StepType,
)
from app.instructions import global_tools_hub
from app.config.settings import VM_SPEC_CONTENT
from .engine import generate_updated_plan, should_update_plan, generate_plan


logger = logging.getLogger(__name__)


class Task:
    def __init__(self, task_orm: TaskORM, llm_interface: LLMInterface):
        self.task_orm = task_orm
        self.vm = PlanExecutionVM(task_orm.repo_path, llm_interface)

    @property
    def id(self):
        return self.task_orm.id

    @property
    def repo_path(self):
        return self.task_orm.repo_path

    def run(self):
        self.vm.set_goal(self.task_orm.goal)
        plan = generate_plan(self.vm.llm_interface, self.task_orm.goal)
        if plan:
            logger.info("Generated Plan:")
            self.vm.state["current_plan"] = plan

            while True:
                execution_result = self.vm.step()
                if execution_result.get("success") is not True:
                    self.task_orm.status = "failed"
                    self.task_orm.logs = f"Execution result is not successful:{execution_result.get('error')}"
                    self.save()
                    raise ValueError(self.task_orm.logs)
                commit_hash = execution_result.get("commit_hash")
                if not commit_hash:
                    raise ValueError("Failed to commit changes")

                if self.vm.state.get("goal_completed"):
                    logger.info("Goal completed during plan execution.")
                    break

            if self.vm.state.get("goal_completed"):
                self.task_orm.status = "completed"
                self.task_orm.logs = "Plan execution completed."
                final_answer = self.vm.get_variable("final_answer")
                if final_answer:
                    logger.info("final_answer: %s", final_answer)
                else:
                    logger.info("No result was generated.")
            else:
                self.task_orm.status = "failed"
                self.task_orm.logs = self.vm.state.get("errors")
                logger.error(
                    "Plan execution failed or did not complete: %s",
                    self.vm.state.get("errors"),
                )
        else:
            self.task_orm.status = "failed"
            self.task_orm.logs = f"Failed to generate plan {plan}"
            logger.error("task %s:%s", self.task_orm.id, self.task_orm.logs)

        self.save()

    def update(
        self, commit_hash: str, suggestion: Optional[str] = None, steps: int = 20
    ) -> Dict[str, Any]:
        try:
            self.vm.set_state(commit_hash)
            steps_executed = 0
            last_commit_hash = commit_hash

            logger.info(
                f"Starting VM execution for Task ID {self.task_orm.id} from commit hash {commit_hash} to address the suggestion {suggestion}"
            )

            for _ in range(steps):
                should_update, explanation, key_factors = should_update_plan(
                    self.vm, suggestion
                )
                if should_update:
                    updated_plan = generate_updated_plan(
                        self.vm, explanation, key_factors
                    )
                    logger.info(
                        f"Generated updated plan: {json.dumps(updated_plan, indent=2)}"
                    )
                    branch_name = (
                        f"plan_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    )

                    if self.vm.git_manager.create_branch_from_commit(
                        branch_name, last_commit_hash
                    ) and self.vm.git_manager.checkout_branch(branch_name):
                        self.vm.state["current_plan"] = updated_plan
                        self.vm.recalculate_variable_refs()
                        self.vm.save_state()
                        new_commit_hash = self.vm.git_manager.commit_changes(
                            StepType.PLAN_UPDATE,
                            str(self.vm.state["program_counter"]),
                            explanation,
                            {"updated_plan": updated_plan},
                            {},
                        )
                        if new_commit_hash:
                            last_commit_hash = new_commit_hash
                            logger.info(
                                f"Resumed execution with updated plan on branch '{branch_name}'. New commit: {new_commit_hash}"
                            )
                        else:
                            logger.error("Failed to commit updated plan")
                            break
                    else:
                        logger.error(
                            f"Failed to create or checkout branch '{branch_name}'"
                        )
                        break

                try:
                    execution_result = self.vm.step()
                except Exception as e:
                    error_msg = f"Error during VM step execution: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    raise e

                if execution_result.get("success") is not True:
                    raise ValueError(
                        f"Execution result is not successful:{execution_result.get('error')}"
                    )

                commit_hash = execution_result.get("commit_hash")
                if not commit_hash:
                    raise ValueError("Failed to commit changes")

                last_commit_hash = commit_hash
                steps_executed += 1

                if self.vm.state.get("goal_completed"):
                    logger.info("Goal completed. Stopping execution.")
                    break

            self.task_orm.status = (
                "completed" if self.vm.state.get("goal_completed") else "failed"
            )
            self.save()

            return {
                "success": True,
                "steps_executed": steps_executed,
                "current_branch": self.vm.git_manager.get_current_branch(),
                "last_commit_hash": last_commit_hash,
            }
        except Exception as e:
            logger.error(
                f"Failed to run task {self.task_orm.id}: {str(e)}", exc_info=True
            )
            raise e

    def optimize_step(
        self, commit_hash: str, seq_no: int, suggestion: str
    ) -> Dict[str, Any]:
        try:
            self.vm.set_state(commit_hash)
            last_commit_hash = commit_hash
            prompt = get_step_update_prompt(
                self.vm,
                seq_no,
                VM_SPEC_CONTENT,
                global_tools_hub.get_tools_description(),
                suggestion,
            )
            updated_step_response = self.vm.llm_interface.generate(prompt)

            if not updated_step_response:
                raise ValueError("Failed to generate updated step")

            updated_step = parse_step(updated_step_response)
            if not updated_step:
                raise ValueError(
                    f"Failed to parse updated step {updated_step_response}"
                )

            logger.info(
                f"Updating step: {updated_step}, program_counter: {self.vm.state['program_counter']}"
            )

            current_commit = self.vm.git_manager.get_current_commit(commit_hash)
            if current_commit.parents:
                previous_commit_hash = current_commit.parents[0].hexsha
            else:
                raise ValueError("Cannot update the first commit")

            self.vm.set_state(previous_commit_hash)
            branch_name = f"update_step_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            if self.vm.git_manager.create_branch_from_commit(
                branch_name, previous_commit_hash
            ) and self.vm.git_manager.checkout_branch(branch_name):
                self.vm.state["current_plan"][seq_no] = updated_step
                self.vm.state["program_counter"] = seq_no
                self.vm.recalculate_variable_refs()
                self.vm.save_state()

                new_commit_hash = self.vm.git_manager.commit_changes(
                    StepType.STEP_OPTIMIZATION,
                    str(self.vm.state["program_counter"]),
                    suggestion,
                    {"updated_step": updated_step},
                    {},
                )

                if new_commit_hash:
                    last_commit_hash = new_commit_hash
                    logger.info(
                        f"Resumed execution with updated plan on branch '{branch_name}'. New commit: {new_commit_hash}"
                    )
                else:
                    raise ValueError("Failed to commit step optimization")
            else:
                raise ValueError(f"Failed to create or checkout branch '{branch_name}'")

            # Re-execute the plan from the updated step
            while True:
                execution_result = self.vm.step()
                if execution_result.get("success") is not True:
                    raise ValueError(
                        f"Execution result is not successful:{execution_result.get('error')}"
                    )
                commit_hash = execution_result.get("commit_hash")
                if not commit_hash:
                    raise ValueError("Failed to commit changes")

                last_commit_hash = commit_hash

                if self.vm.state.get("goal_completed"):
                    logger.info("Goal completed during plan execution.")
                    break

            self.task_orm.status = (
                "completed" if self.vm.state.get("goal_completed") else "failed"
            )
            self.save()

            if self.vm.state.get("goal_completed"):
                final_answer = self.vm.get_variable("final_answer")
                if final_answer:
                    logger.info("Final answer: %s", final_answer)
                else:
                    logger.info("No result was generated.")
            else:
                logger.warning("Plan execution failed or did not complete.")
                logger.error(self.vm.state.get("errors"))

            return {
                "success": True,
                "current_branch": self.vm.git_manager.get_current_branch(),
                "last_commit_hash": last_commit_hash,
            }
        except Exception as e:
            logger.error(
                f"Failed to optimize step {seq_no} for task {self.task_orm.id}: {str(e)}",
                exc_info=True,
            )
            raise e

    def save(self):
        try:
            session: Session = SessionLocal()
            session.add(self.task_orm)
            session.commit()
            session.refresh(self.task_orm)
            session.close()
            logger.info("Saved task %s to the database.", self.task_orm.id)
        except Exception as e:
            logger.error(
                "Failed to save task %s: %s", self.task_orm.id, str(e), exc_info=True
            )
            raise e

    def delete(self):
        try:
            session: Session = SessionLocal()
            session.delete(self.task_orm)
            session.commit()
            session.close()
            logger.info("Deleted task %s and associated Git branch.", self.task_orm.id)
        except Exception as e:
            logger.error(
                "Failed to delete task %s: %s", self.task_orm.id, str(e), exc_info=True
            )
            raise e


class TaskService:
    def __init__(self):
        self.llm_interface = LLMInterface(LLM_PROVIDER, LLM_MODEL)

    def create_task(self, goal: str, repo_path: str) -> Task:
        try:
            session: Session = SessionLocal()
            task_orm = TaskORM(
                id=uuid.uuid4(), goal=goal, repo_path=repo_path, status="pending"
            )
            session.add(task_orm)
            session.commit()
            session.refresh(task_orm)
            session.close()
            logger.info(f"Created new task with ID {task_orm.id}")
            return Task(task_orm, self.llm_interface)
        except Exception as e:
            logger.error(f"Failed to create task: {str(e)}", exc_info=True)
            raise e

    def get_task(self, task_id: uuid.UUID) -> Optional[Task]:
        try:
            session: Session = SessionLocal()
            task_orm = session.query(TaskORM).filter(TaskORM.id == task_id).first()
            session.close()
            if task_orm:
                logger.info(f"Retrieved task with ID {task_id}")
                return Task(task_orm, self.llm_interface)
            else:
                logger.warning(f"Task with ID {task_id} not found.")
                return None
        except Exception as e:
            logger.error(f"Failed to retrieve task {task_id}: {str(e)}", exc_info=True)
            raise e

    def update_task(self, task_id: uuid.UUID, **kwargs) -> Optional[Task]:
        try:
            task = self.get_task(task_id)
            if task:
                for key, value in kwargs.items():
                    setattr(task.task_orm, key, value)
                task.save()
                logger.info(f"Updated task {task_id} with {kwargs}")
                return task
            return None
        except Exception as e:
            logger.error(f"Failed to update task {task_id}: {str(e)}", exc_info=True)
            raise e

    def delete_task(self, task_id: uuid.UUID) -> bool:
        try:
            task = self.get_task(task_id)
            if task:
                task.delete()
                logger.info("Deleted task %s", task_id)
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete task {task_id}: {str(e)}", exc_info=True)
            raise e

    def list_tasks(self) -> List[Task]:
        try:
            session: Session = SessionLocal()
            tasks = session.query(TaskORM).all()
            session.close()
            return tasks
        except Exception as e:
            logger.error(f"Failed to list tasks: {str(e)}", exc_info=True)
            raise e
