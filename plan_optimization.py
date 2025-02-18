import json
import logging
from typing import Optional
from datetime import datetime, timedelta

from app.core.plan.evaluator import evaulate_answer
from app.llm.interface import LLMInterface
from app.config.settings import EVALUATION_LLM_PROVIDER, EVALUATION_LLM_MODEL
from app.instructions import global_tools_hub

from notebooks.plan_chat_optimizer import (
    get_task_answer,
    update_plan,
    execute_task_using_new_plan,
)
from notebooks.tasks import get_evaluation_pending_tasks, record_evaluation, record_human_evaluation
from notebooks.plan_mcts_optimizer import MCTSPlanOptimizer
from notebooks.tasks import save_best_plan_from_url


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

            eval_res = evaulate_answer(eval_llm, goal, metadata, final_answer, plan)
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
        error_message = "Still failed after two evaluations round."
    logger.info(f"Failed to evaluate plan for task(id={task_id}): {error_message}")
    return "WAITING_FOR_EVALUATION"


def print_node(node):
    logger.info("*" * 100)
    logger.info(node.state.seq_no, node.state.commit_hash, node.visits, node.value)
    for suggestion in node.optimization_suggestions:
        logger.info(suggestion["branch_name"])
        logger.info(suggestion["suggestion"])
    for child in node.children:
        print_node(child)


if __name__ == "__main__":
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=12)

    logger.info("Round started at %s", end_time)

    pending_tasks = get_evaluation_pending_tasks(start_time=start_time)

    logger.info("Found %d pending tasks", len(pending_tasks))
    for task in pending_tasks:
        task_id = task["id"]
        status = optimize_plan(task_id, "main", max_iteration=1)
        logger.info("Task %s status: %s", task_id, status)

        if status != "WAITING_FOR_EVALUATION":
            logger.info("Task %s is not waiting for evaluation, skip", task_id)
            continue

        try:
            logger.info("optimizing task", task_id)
            optimizer = MCTSPlanOptimizer(
                task_id=task_id, max_iterations=3, time_limit_seconds=900
            )
            print_node(optimizer.root)
            optimizer.optimize()
            answers = optimizer.sort_final_answers()
            logger.info("Answer benchmark: %s", answers)
            save_best_plan_from_url(task_id, answers[0]["final_answer"])
            if len(answers) > 0:
                save_best_plan_from_url(
                    task_id=task_id, commit_hash=answers[0]["commit_hash"]
                )
                logger.info("Save best plan from url %s", answers[0]["commit_hash"])
        except Exception as e:
            record_human_evaluation(task_id, "WAITING_FOR_EVALUATION", str(e))
            logger.error("Failed to optimize task %s: %s", task_id, e)
