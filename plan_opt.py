import json
import logging
from typing import Optional
from datetime import datetime, timedelta
import time
import argparse
import uuid

from app.core.plan.evaluator import evaulate_answer
from app.core.task.utils import describe_goal
from app.llm.interface import LLMInterface
from app.config.settings import EVALUATION_LLM_PROVIDER, EVALUATION_LLM_MODEL
from app.instructions import global_tools_hub

from plan_optimization.plan_chat_optimizer import (
    get_task_answer,
    update_plan,
    execute_task_using_new_plan,
)
from plan_optimization.tasks import (
    get_evaluation_pending_tasks,
    record_evaluation,
    record_human_evaluation,
)
from plan_optimization.plan_mcts_optimizer import MCTSPlanOptimizer
from plan_optimization.tasks import save_best_plan_from_url


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
)

logger = logging.getLogger(__name__)

global_tools_hub.load_tools("tools")
eval_llm = LLMInterface(EVALUATION_LLM_PROVIDER, EVALUATION_LLM_MODEL)


def optimize_plan(task_id: str, branch_name: Optional[str] = "main", max_iteration=3):
    current_branch_name = branch_name
    error_message = None
    iteration_round = 0

    while True:
        iteration_round += 1
        logger.info(
            f"Start to evaluate plan for task(id={task_id},branch={current_branch_name})"
        )
        detail = get_task_answer(task_id, current_branch_name)

        if detail is not None:
            goal = detail.get("goal")
            final_answer = detail.get("final_answer")
            plan = detail.get("plan")
            metadata = detail.get("metadata")

            if plan is None:
                record_evaluation(task_id, "REJECTED", "No plan found")
                return "REJECTED"

            goal_description = describe_goal(goal, metadata)
            eval_res = evaulate_answer(eval_llm, goal_description, final_answer, plan)
            eval_status = (
                "APPROVED"
                if eval_res.get("accept", False)
                else "WAITING_FOR_EVALUATION"
            )
            eval_reason = json.dumps(eval_res, indent=2)

            record_evaluation(task_id, eval_status, eval_reason)

            if eval_res.get("accept", False) is True:
                logger.info(f"Goal Pass! {goal}, evaluation result:{eval_reason}")
                return eval_status

            logger.info(f"Goal Not Pass! {goal}, the evaluation result:{eval_reason}")

            if iteration_round >= max_iteration:
                break

            revised_plan = update_plan(goal, metadata, eval_reason, plan)
            logger.info("revised plan: %s", revised_plan)
            reasoning = revised_plan.get("reasoning", None)
            revised_plan = revised_plan.get("plan", None)

            try:
                updated_result = execute_task_using_new_plan(
                    task_id, revised_plan, reasoning
                )
                logger.info("Revised plan execution result %s", updated_result)
            except Exception as e:
                error_message = f"Failed to execute task using new plan {e}"
                break

            current_branch_name = updated_result.get("branch_name", None)
            current_final_answer = updated_result.get("final_answer", None)
            if current_branch_name is None or current_final_answer is None:
                error_message = "Failed to execut task using new plan, get empty answer"
                break

    if error_message is None:
        error_message = f"Still failed after {max_iteration} evaluations round."
    logger.info(f"Failed to evaluate plan for task(id={task_id}): {error_message}")
    return "WAITING_FOR_EVALUATION"


def print_node(node):
    logger.info("*" * 100)
    logger.info(
        f"seq_no: {node.state.seq_no}, commit_hash: {node.state.commit_hash}, visits: {node.visits}, value: {node.value}"
    )
    for suggestion in node.optimization_suggestions:
        logger.info(f"branch_name: {suggestion['branch_name']}")
        logger.info(f"suggestion: {suggestion['suggestion']}")
    for child in node.children:
        print_node(child)


def uuid_to_int(uuid_str):
    """Convert UUID string to integer using its hex representation"""
    return int(uuid_str.replace("-", ""), 16)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--process_id",
        type=int,
        required=True,
        help="Process ID (0 to num_processes-1)",
    )
    parser.add_argument(
        "--num_processes", type=int, required=True, help="Total number of processes"
    )
    args = parser.parse_args()

    if not (0 <= args.process_id < args.num_processes):
        raise ValueError(f"Process ID must be between 0 and {args.num_processes-1}")

    last_run_time = datetime.utcnow() - timedelta(hours=48)  # Initial start time

    while True:  # Run forever
        current_time = datetime.utcnow() - timedelta(minutes=10)
        logger.info(
            f"Round started at {current_time} (Process {args.process_id}/{args.num_processes})"
        )

        try:
            pending_tasks = get_evaluation_pending_tasks(
                start_time=last_run_time, end_time=current_time
            )
            logger.info("Found %d pending tasks", len(pending_tasks))

            for task in pending_tasks:
                task_id = task["id"]
                """
                status = optimize_plan(task_id, "main", max_iteration=1)
                logger.info("Task %s status: %s", task_id, status)

                if status != "WAITING_FOR_EVALUATION":
                    logger.info("Task %s is not waiting for evaluation, skip", task_id)
                """
                # Convert UUID to integer and check if this process should handle this task
                task_num = uuid_to_int(task_id)
                if task_num % args.num_processes != args.process_id:
                    continue

                logger.info(f"Process {args.process_id} handling task {task_id}")
                try:
                    logger.info(
                        "optimizing task %s created at %s", task_id, task["created_at"]
                    )
                    optimizer = MCTSPlanOptimizer(
                        task_id=task_id, max_iterations=5, time_limit_seconds=1800
                    )
                    print_node(optimizer.root)
                    optimizer.optimize()
                    answers = optimizer.sort_final_answers()
                    logger.info("Answer benchmark: %s", answers)
                    if len(answers) > 0:
                        save_best_plan_from_url(
                            task_id=task_id, commit_hash=answers[0]["commit_hash"]
                        )
                        logger.info(
                            "Save best plan from url %s", answers[0]["commit_hash"]
                        )
                        record_evaluation(
                            task_id,
                            "APPROVED",
                            f"The plan is optimized by the LLM, and choose the best answer among {len(answers)} answers.",
                        )
                    else:
                        record_evaluation(task_id, "REJECTED", "No plan found")
                        record_human_evaluation(
                            task_id,
                            "WAITING_FOR_EVALUATION",
                            "The plan is optimized by the LLM, but no better answer is found.",
                        )
                except Exception as e:
                    record_human_evaluation(task_id, "WAITING_FOR_EVALUATION", str(e))
                    logger.error("Failed to optimize task %s: %s", task_id, e)

            # Update last run time and sleep
            last_run_time = current_time
            logger.info("Round completed. Sleeping for 1 minute...")
            time.sleep(60)  # Sleep for 1 minute
        except Exception as e:
            logger.error("Error in main loop: %s", e)
            time.sleep(60)  # Sleep even if there's an error
