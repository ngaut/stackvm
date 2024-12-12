import logging
import json
import os
import uuid
import threading
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
from app.config.settings import VM_SPEC_CONTENT, GIT_REPO_PATH

from .plan import generate_updated_plan, should_update_plan, generate_plan
from .label_classifier import LabelClassifier
from .simple_cache import initialize_cache

logger = logging.getLogger(__name__)
classifier = LabelClassifier()
simple_semantic_cache = initialize_cache()


class Task:
    def __init__(self, task_orm: TaskORM, llm_interface: LLMInterface):
        self.task_orm = task_orm
        if task_orm.status == "deleted":
            raise ValueError(f"Task {task_orm.id} is deleted.")
        if task_orm.repo_path != "":
            self.vm = PlanExecutionVM(
                repo_name=task_orm.repo_path, llm_interface=llm_interface
            )
        else:
            self.vm = PlanExecutionVM(task_id=task_orm.id, llm_interface=llm_interface)
        self.vm.set_goal(task_orm.goal)
        self._lock = threading.RLock()

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

    def create_branch(self, branch_name: str, commit_hash: str):
        with self._lock:
            return self.vm.branch_manager.checkout_branch_from_commit(
                branch_name, commit_hash
            )

    def get_branches(self):
        return self.branch_manager.list_branches()

    def set_branch(self, branch_name: str):
        with self._lock:
            self.branch_manager.checkout_branch(branch_name)

    def delete_branch(self, branch_name: str):
        with self._lock:
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

    def mark_as_completed(self):
        self.task_orm.status = "completed"
        self.task_orm.logs = "Plan execution completed."
        self.save()

    def generate_plan(self):
        """Generate a plan for the task."""
        example_str = None
        plan = None
        best_pratices = None
        response_format = (
            self.task_orm.meta.get("response_format") if self.task_orm.meta else None
        )

        # check if the goal is in the cache
        try:
            candidate = simple_semantic_cache.get(self.task_orm.goal, response_format)
            if candidate:
                if candidate.get("matched") is True:
                    plan = candidate["cached_goal"].get("best_plan", None)

                if plan is not None:
                    logger.info("Reusing the cache plan of goal %s", self.task_orm.goal)
                elif candidate.get("reference_goal"):
                    logger.info(
                        "Using the reference goal %s to generate a new plan",
                        candidate["reference_goal"]["goal"],
                    )
                    example_goal = candidate["reference_goal"].get("goal", None)
                    example_plan = candidate["reference_goal"].get("best_plan", None)
                    if example_goal and example_plan:
                        example_str = f"**Goal**:\n{example_goal}\n**The plan:**\n{example_plan}\n"
        except Exception as e:
            logger.error("Failed to get plan from cache: %s", str(e), exc_info=True)

        if plan is None and example_str is None:
            # find the similar task from label tree
            try:
                label_path, example, best_pratices = classifier.generate_label_path(
                    self.task_orm.goal
                )
                example_goal = example.get("goal", None) if example else None
                example_plan = example.get("best_plan", None) if example else None
                logger.info(
                    "Label path: %s for task %s", label_path, self.task_orm.goal
                )
                # use it as an example to generate a plan
                if example_goal and example_plan:
                    example_str = (
                        f"**Goal**:\n{example_goal}\n**The plan:**\n{example_plan}\n"
                    )
            except Exception as e:
                logger.error("Failed to generate label path: %s", str(e), exc_info=True)

        # generate plan if not found in cache
        if plan is None:
            goal = self.task_orm.goal
            if response_format:
                goal = f"{goal} {response_format}"
            logger.info("Generating plan for goal: %s", goal)
            plan = generate_plan(
                self.vm.llm_interface,
                goal,
                example=example_str,
                best_practices=best_pratices,
            )

        if plan:
            self.vm.set_plan(plan)

        return plan

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
        with self._lock:
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

    def re_execute(
        self,
        commit_hash: Optional[str] = None,
        plan: Optional[List[Dict[str, Any]]] = None,
    ):
        with self._lock:
            branch_name = f"re_execute_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            try:
                if commit_hash:
                    self.vm.set_state(commit_hash)
                    if not self.branch_manager.checkout_branch_from_commit(
                        branch_name, commit_hash
                    ) or not self.branch_manager.checkout_branch(branch_name):
                        raise ValueError(
                            f"Failed to create or checkout branch '{branch_name}'"
                        )
                else:
                    hashes = self.branch_manager.get_commit_hashes()
                    if len(hashes) <= 1:
                        raise ValueError(
                            "Please choose the existing branch with plan to re-execute"
                        )

                    earliest_commit_hash = hashes[-1]
                    print("earliest_commit_hash", earliest_commit_hash)

                    if not plan:
                        plan = self.vm.state.get("current_plan", None)
                        if not plan:
                            raise ValueError("Failed to get plan")

                    if not self.branch_manager.checkout_branch_from_commit(
                        branch_name, earliest_commit_hash
                    ):
                        raise ValueError(
                            f"Failed to create or checkout branch '{branch_name}'"
                        )

                    self.vm.clear_state()
                    self.vm.set_plan(plan)

                self._run()
            except Exception as e:
                self.task_orm.status = "failed"
                self.task_orm.logs = f"Failed to run task {self.task_orm.id}, goal: {self.task_orm.goal}: {str(e)}"
                self.save()
                raise ValueError(self.task_orm.logs)

    def update_plan(self, branch_name: str, suggestion: str, key_factors: list = []):
        updated_plan = generate_updated_plan(self.vm, suggestion, key_factors)
        logger.info("Generated updated plan: %s", json.dumps(updated_plan, indent=2))

        self.vm.set_plan(updated_plan)
        self.vm.recalculate_variable_refs()
        self.vm.save_state()
        new_commit_hash = self.vm.branch_manager.commit_changes(
            commit_info={
                "type": StepType.PLAN_UPDATE.value,
                "seq_no": str(self.vm.state["program_counter"]),
                "description": suggestion,
                "input_parameters": {"updated_plan": updated_plan},
                "output_variables": {},
            }
        )
        if new_commit_hash:
            logger.info(
                f"Resumed execution with updated plan on branch '{branch_name}'. New commit: {new_commit_hash}"
            )
            return new_commit_hash

        logger.error("Failed to commit updated plan for branch '%s'", branch_name)
        return None

    def update(
        self, new_branch_name: str, commit_hash: str, suggestion: Optional[str] = None
    ) -> Dict[str, Any]:
        with self._lock:
            try:
                self.vm.set_state(commit_hash)
                last_commit_hash = commit_hash

                logger.info(
                    f"Update plan for Task ID {self.task_orm.id} from commit hash: {commit_hash} to address the suggestion: {suggestion}"
                )

                if not self.branch_manager.checkout_branch(new_branch_name):
                    raise ValueError(
                        f"Failed to create or checkout branch '{new_branch_name}'"
                    )

                new_commit_hash = self.update_plan(new_branch_name, suggestion)
                if new_commit_hash:
                    last_commit_hash = new_commit_hash
                else:
                    raise ValueError("Failed to commit updated plan")

                self._run()
                return {
                    "success": True,
                    "current_branch": self.vm.branch_manager.get_current_branch(),
                }
            except Exception as e:
                self.task_orm.status = "failed"
                self.task_orm.logs = f"Failed to update task {self.task_orm.id}, goal: {self.task_orm.goal}: {str(e)}"
                logger.error(self.task_orm.logs, exc_info=True)
                self.save()
                raise e

    def dynamic_update(
        self,
        new_branch_name: str,
        commit_hash: str,
        suggestion: Optional[str] = None,
        steps: int = 20,
    ) -> Dict[str, Any]:
        with self._lock:
            try:
                self.vm.set_state(commit_hash)
                steps_executed = 0
                last_commit_hash = commit_hash

                logger.info(
                    f"Dynamic update plan for Task ID {self.task_orm.id} from commit hash: {commit_hash} to address the suggestion: {suggestion}"
                )

                if not self.branch_manager.checkout_branch(new_branch_name):
                    raise ValueError(
                        f"Failed to create or checkout branch '{branch_name}'"
                    )

                for _ in range(steps):
                    should_update, explanation, key_factors = should_update_plan(
                        self.vm, suggestion
                    )
                    if should_update:
                        new_commit_hash = self.update_plan(
                            new_branch_name, explanation, key_factors
                        )
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
        with self._lock:
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
                branch_name = (
                    f"optimize_step_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )

                if self.branch_manager.checkout_branch_from_commit(
                    branch_name, previous_commit_hash
                ):
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
                    raise ValueError(
                        f"Failed to create or checkout branch '{branch_name}'"
                    )

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

    def save_best_plan(self, commit_hash: str):
        # get the plan from the highest seq_no in this selected branch
        detail = self.get_execution_details(commit_hash=commit_hash)
        if (
            detail
            and "vm_state" in detail[0]
            and "current_plan" in detail[0]["vm_state"]
        ):
            current_plan = detail[0]["vm_state"]["current_plan"]
            self.task_orm.best_plan = current_plan
            self.save()
            return True

        logger.error(
            "Failed to find plan for task %s from commit hash %s",
            self.task_orm.id,
            commit_hash,
        )
        return False

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

    def create_task(
        self, session: Session, goal: str, repo_name: str, meta: Optional[Dict] = None
    ) -> Task:
        try:
            task_orm = TaskORM(
                id=uuid.uuid4(),
                goal=goal,
                repo_path="",
                status="pending",
                meta=meta,
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
            task_orm = (
                session.query(TaskORM)
                .filter(TaskORM.id == task_id, TaskORM.status != "deleted")
                .first()
            )
            if task_orm:
                logger.info(f"Retrieved task with ID {task_id}")
                if task_orm.repo_path != "" and not os.path.exists(task_orm.repo_path):
                    task_orm.status = "deleted"
                    session.add(task_orm)
                    session.commit()
                    logger.warning(f"Task with ID {task_id} is deleted.")
                    return None

                return Task(task_orm, self.llm_interface)
            else:
                logger.warning(f"Task with ID {task_id} not found.")
                return None
        except Exception as e:
            logger.error(f"Failed to retrieve task {task_id}: {str(e)}", exc_info=True)
            raise e

    def list_tasks(self, session, limit=10, offset=0):
        """
        List tasks with pagination support.

        Args:
            session: Database session
            limit (int): Maximum number of tasks to return
            offset (int): Number of tasks to skip

        Returns:
            List of Task objects
        """
        return (
            session.query(TaskORM)
            .filter(TaskORM.status != "deleted")
            .order_by(TaskORM.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def list_best_plans(self, session, limit=50, offset=0):
        """
        List best plans with pagination support.
        """
        return (
            session.query(TaskORM)
            .filter(TaskORM.best_plan != None)
            .order_by(TaskORM.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_best_plans(self, session):
        """
        Count best plans.
        """
        return session.query(TaskORM).filter(TaskORM.best_plan != None).count()
