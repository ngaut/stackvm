import logging
import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, List
from sqlalchemy.orm import Session

from app.models import Task as TaskORM
from app.config.settings import LLM_PROVIDER, LLM_MODEL
from app.services import (
    LLMInterface,
    PlanExecutionVM,
    get_step_update_prompt,
    parse_step,
    StepType,
)

from app.database import SessionLocal
from app.instructions import global_tools_hub
from app.config.settings import VM_SPEC_CONTENT

from .plan import generate_updated_plan, should_update_plan, generate_plan


logger = logging.getLogger(__name__)


class Task:
    def __init__(self, task_orm: TaskORM, llm_interface: LLMInterface):
        self.task_orm = task_orm
        if task_orm.status == "deleted":
            raise ValueError(f"Task {task_orm.id} is deleted.")
        self.vm = PlanExecutionVM(task_orm.repo_path, llm_interface)
        self.vm.set_goal(task_orm.goal)

    @property
    def id(self):
        """Return the ID of the task."""
        return self.task_orm.id

    @property
    def repo_path(self):
        """Return the repository path of the task."""
        return self.task_orm.repo_path

    @property
    def branch_manager(self):
        """Return the repository of the task."""
        return self.vm.branch_manager

    def get_current_branch(self):
        return self.branch_manager.get_current_branch()

    def get_branches(self):
        return self.branch_manager.list_branches()

    def set_branch(self, branch_name: str):
        self.branch_manager.checkout_branch(branch_name)

    def delete_branch(self, branch_name: str):
        self.branch_manager.delete_branch(branch_name)

    def get_execution_details(
        self, branch_name: Optional[str] = None, commit_hash: Optional[str] = None
    ):
        if commit_hash:
            return [self.branch_manager.get_commit(commit_hash)]

        if not branch_name:
            raise ValueError("Branch name or commit hash is required.")

        return self.branch_manager.get_commits(branch_name)

    def get_state_diff(self, commit_hash: str):
        return self.branch_manager.get_state_diff(commit_hash)

    def generate_plan(self):
        """Generate a plan for the task."""
        plan = generate_plan(self.vm.llm_interface, self.task_orm.goal)
        if plan:
            self.vm.set_plan(plan)
        return plan

    def mark_as_completed(self):
        self.task_orm.status = "completed"
        self.task_orm.logs = "Plan execution completed."
        self.save()

    def _run(self):
        """Execute the plan for the task."""
        while True:
            execution_result = self.vm.step()
            if execution_result.get("success") is not True:
                raise ValueError(
                    f"Failed to execute step:{execution_result.get('error')}"
                )

            if self.vm.state.get("goal_completed"):
                logger.info("Goal completed during plan execution.")
                break

        if self.vm.state.get("goal_completed"):
            self.mark_as_completed()
            final_answer = self.vm.get_variable("final_answer")
            if final_answer:
                logger.info("final_answer: %s", final_answer)
            else:
                logger.info("No result was generated.")
        else:
            raise ValueError(
                "Plan execution failed or did not complete: %s",
                self.vm.state.get("errors"),
            )

    def execute(self):
        try:
            plan = self.generate_plan()
            if not plan:
                raise ValueError("Failed to generate plan")

            logger.info("Generated Plan:%s", json.dumps(plan, indent=2))
            self._run()
        except Exception as e:
            self.task_orm.status = "failed"
            self.task_orm.logs = f"Failed to run task {self.task_orm.id}, goal: {self.task_orm.goal}: {str(e)}"
            self.save()
            raise ValueError(self.task_orm.logs)

    def update_plan(self, commit_hash: str, suggestion: str):
        should_update, explanation, key_factors = should_update_plan(
            self.vm, suggestion
        )
        if should_update:
            updated_plan = generate_updated_plan(self.vm, explanation, key_factors)
            logger.info(
                "Generated updated plan: %s", json.dumps(updated_plan, indent=2)
            )
            branch_name = f"plan_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            if self.vm.branch_manager.checkout_branch_from_commit(
                branch_name, commit_hash
            ) and self.vm.branch_manager.checkout_branch(branch_name):
                self.vm.set_plan(updated_plan)
                self.vm.recalculate_variable_refs()
                self.vm.save_state()
                new_commit_hash = self.vm.branch_manager.commit_changes(
                    commit_info={
                        "type": StepType.PLAN_UPDATE.value,
                        "seq_no": str(self.vm.state["program_counter"]),
                        "description": explanation,
                        "input_parameters": {"updated_plan": updated_plan},
                        "output_variables": {},
                    }
                )
                if new_commit_hash:
                    logger.info(
                        f"Resumed execution with updated plan on branch '{branch_name}'. New commit: {new_commit_hash}"
                    )
                    return new_commit_hash
                else:
                    logger.error("Failed to commit updated plan")
            else:
                logger.error(f"Failed to create or checkout branch '{branch_name}'")

        return None

    def auto_update(
        self, commit_hash: str, suggestion: Optional[str] = None, steps: int = 20
    ) -> Dict[str, Any]:
        try:
            self.vm.set_state(commit_hash)
            steps_executed = 0
            last_commit_hash = commit_hash

            logger.info(
                f"Starting VM execution for Task ID {self.task_orm.id} from commit hash {commit_hash} to address the suggestion {suggestion}"
            )

            branch_name = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.vm.branch_manager.checkout_branch_from_commit(branch_name, commit_hash)
            self.vm.branch_manager.checkout_branch(branch_name)

            for _ in range(steps):
                new_commit_hash = self.update_plan(last_commit_hash, suggestion)
                if new_commit_hash:
                    last_commit_hash = new_commit_hash

                try:
                    execution_result = self.vm.step()
                except Exception as e:
                    error_msg = f"Error during VM step execution: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    raise e

                if execution_result.get(
                    "success"
                ) is not True or not execution_result.get("commit_hash"):
                    raise ValueError(
                        f"Execution result is not successful:{execution_result.get('error')}"
                    )

                last_commit_hash = execution_result.get("commit_hash")
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
                "current_branch": self.vm.branch_manager.get_current_branch(),
            }
        except Exception as e:
            self.task_orm.status = "failed"
            self.task_orm.logs = f"Failed to update task {self.task_orm.id}, goal: {self.task_orm.goal}: {str(e)}"
            logger.error(self.task_orm.logs, exc_info=True)
            self.save()
            raise e

    def optimize_step(
        self, commit_hash: str, seq_no: int, suggestion: str
    ) -> Dict[str, Any]:
        try:
            self.vm.set_state(commit_hash)
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

            previous_commit_hash = self.branch_manager.get_parent_commit_hash(
                commit_hash
            )

            self.vm.set_state(previous_commit_hash)
            branch_name = f"update_step_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            if self.branch_manager.checkout_branch_from_commit(
                branch_name, previous_commit_hash
            ) and self.branch_manager.checkout_branch(branch_name):
                self.vm.state["current_plan"][seq_no] = updated_step
                self.vm.state["program_counter"] = seq_no
                self.vm.recalculate_variable_refs()
                self.vm.save_state()

                new_commit_hash = self.vm.branch_manager.commit_changes(
                    commit_info={
                        "type": StepType.STEP_OPTIMIZATION.value,
                        "seq_no": str(self.vm.state["program_counter"]),
                        "description": suggestion,
                        "input_parameters": {"updated_step": updated_step},
                        "output_variables": {},
                    }
                )

                if new_commit_hash:
                    logger.info(
                        f"Resumed execution with updated plan on branch '{branch_name}'. New commit: {new_commit_hash}"
                    )
                else:
                    raise ValueError("Failed to commit step optimization")
            else:
                raise ValueError(f"Failed to create or checkout branch '{branch_name}'")

            self._run()
            return {
                "success": True,
                "current_branch": self.vm.branch_manager.get_current_branch(),
                "latest_commit_hash": self.vm.branch_manager.get_current_commit_hash(),
            }
        except Exception as e:
            self.task_orm.status = "failed"
            self.task_orm.logs = f"Failed to optimize step {seq_no} for task {self.task_orm.id}, goal: {self.task_orm.goal}: {str(e)}"
            logger.error(self.task_orm.logs, exc_info=True)
            self.save()
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


class TaskService:
    def __init__(self):
        self.llm_interface = LLMInterface(LLM_PROVIDER, LLM_MODEL)

    def create_task(self, session: Session, goal: str, repo_path: str) -> Task:
        try:
            task_orm = TaskORM(
                id=uuid.uuid4(), goal=goal, repo_path=repo_path, status="pending"
            )
            session.add(task_orm)
            session.commit()
            session.refresh(task_orm)
            logger.info(f"Created new task with ID {task_orm.id}")
            return Task(task_orm, self.llm_interface)
        except Exception as e:
            logger.error(f"Failed to create task: {str(e)}", exc_info=True)
            raise e

    def get_task(self, session: Session, task_id: uuid.UUID) -> Optional[Task]:
        try:
            task_orm = session.query(TaskORM).filter(TaskORM.id == task_id).first()
            if task_orm:
                logger.info(f"Retrieved task with ID {task_id}")
                _ = task_orm.status
                _ = task_orm.repo_path
                if not os.path.exists(task_orm.repo_path):
                    task_orm.status = "deleted"
                    session.add(task_orm)
                    session.commit()
                    logger.warning(f"Task with ID {task_id} not found.")
                    return None

                return Task(task_orm, self.llm_interface)
            else:
                logger.warning(f"Task with ID {task_id} not found.")
                return None
        except Exception as e:
            logger.error(f"Failed to retrieve task {task_id}: {str(e)}", exc_info=True)
            raise e

    def list_tasks(self, session: Session) -> List[Task]:
        try:
            tasks = session.query(TaskORM).all()
            # filter out tasks that are not found
            vaild_tasks = []
            for task in tasks:
                session.refresh(task)
                if os.path.exists(task.repo_path):
                    vaild_tasks.append(task)
                else:
                    task.status = "deleted"
                    session.add(task)
                    session.commit()

            return vaild_tasks
        except Exception as e:
            logger.error(f"Failed to list tasks: {str(e)}", exc_info=True)
            raise e
