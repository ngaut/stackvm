"""
Visualization module for the VM execution and Git repository management.
"""

import json
import logging
from datetime import datetime, timedelta
from queue import Queue, Empty
from threading import Thread

from git.exc import GitCommandError
from flask import (
    Blueprint,
    render_template,
    jsonify,
    request,
    current_app,
    Response,
    stream_with_context,
    send_from_directory,
)
from flask_cors import CORS

from app.config.database import SessionLocal
from app.config.settings import (
    BACKEND_CORS_ORIGINS,
    GENERATED_FILES_DIR,
)
from app.storage.models import TaskStatus, EvaluationStatus

from .streaming_protocol import StreamingProtocol
from app.core.task.manager import TaskService
from app.core.task.utils import parse_goal_response_format
from app.core.labels.classifier import get_label_path
from app.core.plan.generator import PlanUnavailableError

api_blueprint = Blueprint("api", __name__, url_prefix="/api")

if BACKEND_CORS_ORIGINS and len(BACKEND_CORS_ORIGINS) > 0:
    CORS(
        api_blueprint,
        resources={
            r"/*": {
                "origins": [str(origin).strip("/") for origin in BACKEND_CORS_ORIGINS]
            }
        },
    )

logger = logging.getLogger(__name__)

ts = TaskService()


def log_and_return_error(message, error_type, status_code):
    if error_type == "warning":
        current_app.logger.warning("%s", message)
    elif error_type == "error":
        current_app.logger.error("%s", message)
    else:
        current_app.logger.info("%s", message)
    return jsonify({"error": message}), status_code


# Define a new blueprint for non-API routes
main_blueprint = Blueprint("main", __name__)


@main_blueprint.route("/")
def index():
    return render_template("index.html")


@api_blueprint.route("/tasks/<task_id>/branches/<branch>/details")
def get_execution_details(task_id, branch):
    with SessionLocal() as session:
        task = ts.get_task(session, task_id)
        if not task:
            return jsonify([]), 200

        try:
            vm_states = task.get_execution_details(branch)
        except Exception as e:
            return log_and_return_error(
                f"Unexpected error fetching VM state for branch {branch} for task {task_id}: {str(e)}",
                "error",
                500,
            )

        return jsonify(vm_states)


@api_blueprint.route("/tasks/<task_id>/commits/<commit_hash>/detail")
def get_execution_detail(task_id, commit_hash):
    with SessionLocal() as session:
        task = ts.get_task(session, task_id)
        if not task:
            return log_and_return_error(
                f"Task with ID {task_id} not found.", "error", 404
            )

        try:
            vm_states = task.get_execution_details(commit_hash=commit_hash)
            if vm_states is None or len(vm_states) != 1:
                return log_and_return_error(
                    f"VM state not found for commit {commit_hash} for task {task_id}: {vm_states}",
                    "warning",
                    404,
                )
            return jsonify(vm_states[0])
        except Exception as e:
            return log_and_return_error(
                f"Unexpected error fetching VM state for commit {commit_hash} for task {task_id}: {str(e)}",
                "error",
                500,
            )


@api_blueprint.route("/tasks/<task_id>/branches/<branch_name>/answer_detail")
def get_answer_detail(task_id, branch_name):
    with SessionLocal() as session:
        task = ts.get_task(session, task_id)
        if not task:
            return log_and_return_error(
                f"Task with ID {task_id} not found.", "error", 404
            )

        try:
            vm_state = task.get_answer_detail(branch_name)
            if vm_state is None:
                return log_and_return_error(
                    f"Final answer detail not found for branch {branch_name} for task {task_id}: {vm_state}",
                    "warning",
                    404,
                )
            return jsonify(
                {
                    "id": task.task_orm.id,
                    "goal": task.task_orm.goal,
                    "status": task.task_orm.status.value,
                    "created_at": task.task_orm.created_at,
                    "updated_at": task.task_orm.updated_at,
                    "logs": task.task_orm.logs,
                    "best_plan": task.task_orm.best_plan,
                    "metadata": task.task_orm.meta,
                    "evaluation_status": task.task_orm.evaluation_status.value,
                    "evaluation_reason": task.task_orm.evaluation_reason,
                    "vm_state": vm_state,
                    "namespace": task.task_orm.namespace_name,
                }
            )
        except Exception as e:
            return log_and_return_error(
                f"Unexpected error fetching final answer detail not found for branch {branch_name} for task {task_id}: {str(e)}",
                "error",
                500,
            )


@api_blueprint.route("/tasks/<task_id>/commits/<commit_hash>/diff")
def code_diff(task_id, commit_hash):
    with SessionLocal() as session:
        task = ts.get_task(session, task_id)
        if not task:
            return log_and_return_error(
                f"Task with ID {task_id} not found.", "error", 404
            )

        try:
            diff = task.get_state_diff(commit_hash)
            return jsonify({"diff": diff})
        except Exception as e:
            return log_and_return_error(
                f"Error generating diff for commit {commit_hash} for task '{task_id}': {str(e)}",
                "error",
                404,
            )


@api_blueprint.route("/tasks/<task_id>/update", methods=["POST"])
def update_task(task_id):
    """
    API endpoint to update the plan and execute the VM.

    Args:
        task_id (str): The ID of the task

    Expected JSON payload:
        - suggestion (str): Required. The suggestion for updating the plan
        - commit_hash (str): Optional. The commit hash to update from
        - from_scratch (bool): Optional. Whether to start from scratch. Defaults to False
        - source_branch (str): Optional. The branch to be updated from
    """
    data = request.json
    current_app.logger.info(f"Received update_task request with data: {data}")

    commit_hash = data.get("commit_hash")
    suggestion = data.get("suggestion")
    from_scratch = data.get("from_scratch", False)
    source_branch = data.get("source_branch")  # The branch to be updated from

    if not all([suggestion]):
        return log_and_return_error(
            "Missing required parameters: suggestion", "error", 400
        )

    with SessionLocal() as session:
        task = ts.get_task(session, task_id)
        if not task:
            return log_and_return_error(
                f"Task with ID {task_id} not found.", "error", 404
            )

    try:
        branch_name = f"plan_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        ts.task_queue.add_task(
            task_id,
            {
                "new_branch_name": branch_name,
                "commit_hash": commit_hash,
                "suggestion": suggestion,
                "from_scratch": from_scratch,
                "source_branch": source_branch,  # The branch we want to update from
            },
            task.update,
            datetime.utcnow(),
        )
        return (
            jsonify(
                {
                    "success": True,
                    "current_branch": branch_name,
                }
            ),
            200,
        )
    except Exception as e:
        current_app.logger.error(
            f"Failed to update plan for task {task_id}: {str(e)}", exc_info=True
        )
        return log_and_return_error("Failed to update plan.", "error", 500)


@api_blueprint.route("/tasks/<task_id>/dynamic_update", methods=["POST"])
def dynamic_update(task_id):
    """
    API endpoint to dynamic update the plan and execute the VM.
    """
    data = request.json
    current_app.logger.info(f"Received dynamic_update request with data: {data}")

    commit_hash = data.get("commit_hash")
    suggestion = data.get("suggestion")

    if not all([commit_hash, suggestion]):
        return log_and_return_error("Missing required parameters", "error", 400)

    with SessionLocal() as session:
        task = ts.get_task(session, task_id)
        if not task:
            return log_and_return_error(
                f"Task with ID {task_id} not found.", "error", 404
            )

    try:
        branch_name = f"dynamic_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        ts.task_queue.add_task(
            task_id,
            {
                "new_branch_name": branch_name,
                "commit_hash": commit_hash,
                "suggestion": suggestion,
            },
            task.update,
            datetime.utcnow(),
        )
        return (
            jsonify(
                {
                    "success": True,
                    "current_branch": branch_name,
                }
            ),
            200,
        )
    except Exception as e:
        current_app.logger.error(
            f"Failed to update plan for task {task_id}: {str(e)}", exc_info=True
        )
        return log_and_return_error("Failed to update plan.", "error", 500)


@api_blueprint.route("/tasks/<task_id>/optimize_step", methods=["POST"])
def optimize_step(task_id):
    data = request.json
    current_app.logger.info(f"Received update_step request with data: {data}")

    commit_hash = data.get("commit_hash")
    suggestion = data.get("suggestion")
    seq_no_str = data.get("seq_no")

    if not all([commit_hash, suggestion, seq_no_str]):
        return log_and_return_error("Missing required parameters", "error", 400)

    with SessionLocal() as session:
        seq_no = int(seq_no_str)
        task = ts.get_task(session, task_id)
        if not task:
            return log_and_return_error(
                f"Task with ID {task_id} not found.", "error", 404
            )

    try:
        result = task.optimize_step(commit_hash, seq_no, suggestion)
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.error(
            f"Failed to optimize step {seq_no} for task {task_id}: {str(e)}",
            exc_info=True,
        )
        return log_and_return_error("Failed to optimize step.", "error", 500)


@api_blueprint.route("/tasks/<task_id>/re_execute", methods=["POST"])
def re_execute_task(task_id):
    current_app.logger.info(f"Re-execute task: {task_id}")

    data = request.json
    commit_hash = data.get("commit_hash", None) if data else None
    reasoning = data.get("reasoning", None) if data else None
    plan = data.get("plan", None) if data else None

    task = None
    with SessionLocal() as session:
        task = ts.get_task(session, task_id)
        if not task:
            return log_and_return_error(
                f"Task with ID {task_id} not found.", "error", 404
            )

    try:
        current_app.logger.info(f"re-execute task {task_id}")
        result = task.re_execute(reasoning, commit_hash, plan)
        if result.get("completed"):
            if result.get("final_answer"):
                return (
                    jsonify(
                        {
                            "final_answer": result.get("final_answer"),
                            "branch_name": result.get("branch_name"),
                        }
                    ),
                    200,
                )
            else:
                return (
                    jsonify(
                        f"re-execute task {task_id}, it completed, but not found final answer"
                    ),
                    200,
                )
        else:
            return (
                jsonify(
                    f"re-execute task {task_id}, goal not completed: {task.task_orm}"
                ),
                500,
            )
    except Exception as e:
        current_app.logger.error(
            f"Failed to re-execute task {task_id}: {str(e)}",
            exc_info=True,
        )
        return log_and_return_error(
            f"Failed to re-exeucte task {task_id}.", "error", 500
        )


@api_blueprint.route("/download/<filename>", methods=["GET"])
def download_file(filename):
    try:
        return send_from_directory(GENERATED_FILES_DIR, filename, as_attachment=True)
    except FileNotFoundError:
        return log_and_return_error("File not found.", "error", 404)


@api_blueprint.route(
    "/tasks/<task_id>/commits/<commit_hash>/save_best_plan", methods=["POST"]
)
def save_best_plan(task_id: str, commit_hash: str):
    with SessionLocal() as session:
        task = ts.get_task(session, task_id)
        if not task:
            return log_and_return_error(
                f"Task with ID {task_id} not found.", "error", 404
            )

    success = task.save_best_plan(commit_hash)
    if success:
        return jsonify({"success": True}), 200
    else:
        return log_and_return_error(
            f"Failed to save best plan for task {task_id} from commit hash {commit_hash}",
            "error",
            500,
        )


@api_blueprint.route("/tasks/evaluation")
def list_tasks_evaluation():
    try:
        # Extract query parameters
        start_time_str = request.args.get("start_time")
        end_time_str = request.args.get("end_time")
        evaluation_status_param = request.args.get("evaluation_status")

        # Parse end_time
        if not end_time_str:
            end_time = datetime.utcnow()
        else:
            try:
                end_time = datetime.fromisoformat(end_time_str)
            except ValueError:
                return log_and_return_error(
                    "Invalid 'end_time' format. Expected ISO format.", "error", 400
                )

        # Parse start_time
        if not start_time_str:
            start_time = end_time - timedelta(days=2)
        else:
            try:
                start_time = datetime.fromisoformat(start_time_str)
            except ValueError:
                return log_and_return_error(
                    "Invalid 'start_time' format. Expected ISO format.", "error", 400
                )

        # Parse evaluation_status
        evaluation_statuses = None
        if evaluation_status_param:
            # Split by comma in case of multiple statuses
            status_strings = [
                status.strip() for status in evaluation_status_param.split(",")
            ]
            evaluation_statuses = []
            for status_str in status_strings:
                try:
                    evaluation_status = EvaluationStatus(status_str.upper())
                    evaluation_statuses.append(evaluation_status)
                except ValueError:
                    valid_statuses = [status.value for status in EvaluationStatus]
                    return log_and_return_error(
                        f"Invalid 'evaluation_status' value: '{status_str}'. "
                        f"Must be one of {valid_statuses}.",
                        "error",
                        400,
                    )

        with SessionLocal() as session:
            tasks_orm = ts.list_tasks_evaluation(
                session, start_time, end_time, evaluation_statuses
            )
            tasks = [
                {
                    "id": task.id,
                    "goal": task.goal,
                    "status": task.status.value,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                    "logs": task.logs,
                    "best_plan": task.best_plan,
                    "metadata": task.meta,
                    "evaluation_status": task.evaluation_status.value,  # Include evaluation_status if needed
                }
                for task in tasks_orm
            ]
            return jsonify(tasks)
    except Exception as e:
        current_app.logger.error(f"Error fetching tasks: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@api_blueprint.route("/tasks")
def get_tasks():
    try:
        limit = request.args.get("limit", default=10, type=int)
        offset = request.args.get("offset", default=0, type=int)

        with SessionLocal() as session:
            tasks = ts.list_tasks(session, limit=limit, offset=offset)
            task_ids = [
                {
                    "id": task.id,
                    "goal": task.goal,
                    "status": task.status.value,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                    "logs": task.logs,
                    "repo_path": (
                        "change storage from git to tidb"
                        if task.repo_path == ""
                        else task.repo_path
                    ),
                    "tenant_id": task.tenant_id,
                    "project_id": task.project_id,
                    "best_plan": task.best_plan,
                    "metadata": task.meta,
                    "evaluation_status": task.evaluation_status.value,
                    "evaluation_reason": task.evaluation_reason,
                    "namespace": task.namespace_name,
                }
                for task in tasks
            ]
            return jsonify(
                {"tasks": task_ids, "pagination": {"limit": limit, "offset": offset}}
            )
    except Exception as e:
        current_app.logger.error(f"Error fetching tasks: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@api_blueprint.route("/tasks/<task_id>")
def get_task(task_id):
    try:
        with SessionLocal() as session:
            task = ts.get_task(session, task_id)
            return jsonify(
                {
                    "id": task.task_orm.id,
                    "goal": task.task_orm.goal,
                    "status": task.task_orm.status.value,
                    "created_at": task.task_orm.created_at,
                    "updated_at": task.task_orm.updated_at,
                    "logs": task.task_orm.logs,
                    "best_plan": task.task_orm.best_plan,
                    "metadata": task.task_orm.meta,
                    "evaluation_status": task.task_orm.evaluation_status.value,
                    "evaluation_reason": task.task_orm.evaluation_reason,
                    "namespace": task.task_orm.namespace_name,
                }
            )
    except Exception as e:
        current_app.logger.error(
            f"Error fetching task({task_id}): {str(e)}", exc_info=True
        )
        return jsonify({"error": str(e)}), 500


@api_blueprint.route("/tasks/<task_id>/branches")
def get_branches(task_id):
    with SessionLocal() as session:
        try:
            task = ts.get_task(session, task_id)
            if not task:
                return log_and_return_error(
                    f"Task with ID {task_id} not found.", "error", 404
                )

            branch_data = task.get_branches()
            return jsonify(branch_data)
        except GitCommandError as e:
            return log_and_return_error(
                f"Error fetching branches for task '{task_id}': {str(e)}",
                "error",
                500,
            )


@api_blueprint.route("/tasks/<task_id>/set_branch", methods=["POST"])
def set_branch_route(task_id):
    """
    API endpoint to switch to a specified branch within a repository.

    Args:
        task_id (str): The ID of the task.
        branch_name (str): The name of the branch to switch to.

    Returns:
        JSON response indicating success or failure.
    """
    data = request.json
    branch_name = data.get("branch_name")
    if not branch_name:
        return log_and_return_error("Missing 'branch_name' parameter", "error", 400)

    return jsonify(
        {
            "success": True,
            "message": f"Switched to branch {branch_name} for task '{task_id}'",
        }
    )

    """ Deprecated Code to remove later
    with SessionLocal() as session:
        task = ts.get_task(session, task_id)
        if not task:
            return log_and_return_error(
                f"Task with ID {task_id} not found.", "error", 404
            )

        try:
            task.set_branch(branch_name)
            return jsonify(
                {
                    "success": True,
                    "message": f"Switched to branch {branch_name} for task '{task_id}'",
                }
            )
        except GitCommandError as e:
            return log_and_return_error(
                f"Error switching to branch {branch_name}: {str(e)}", "error", 400
            )
    """


@api_blueprint.route("/tasks/<task_id>/branches/<branch_name>", methods=["DELETE"])
def delete_branch_route(task_id, branch_name):
    """
    API endpoint to delete a specified branch within a repository.

    Args:
        task_id (str): The ID of the task.
        branch_name (str): The name of the branch to delete.

    Returns:
        JSON response indicating success or failure.
    """

    with SessionLocal() as session:
        task = ts.get_task(session, task_id)
        if not task:
            return log_and_return_error(
                f"Task with ID {task_id} not found.", "error", 404
            )

        try:
            task.delete_branch(branch_name)
            return jsonify(
                {
                    "success": True,
                    "message": f"Branch {branch_name} deleted successfully for task '{task_id}'",
                    "new_active_branch": task.get_current_branch(),
                }
            )
        except GitCommandError as e:
            return log_and_return_error(
                f"Error deleting branch {branch_name}: {str(e)}", "error", 400
            )


@api_blueprint.route("/best_plans")
def get_best_plans():
    limit = request.args.get("limit", default=10, type=int)
    offset = request.args.get("offset", default=0, type=int)

    with SessionLocal() as session:
        tasks = ts.list_best_plans(session, limit=limit, offset=offset)
        total = ts.count_best_plans(session)
        best_plans = [
            {
                "id": task.id,
                "goal": task.goal,
                "best_plan": task.best_plan,
                "label_path": get_label_path(task.label) if task.label else [],
            }
            for task in tasks
        ]
        return jsonify(
            {
                "best_plans": best_plans,
                "pagination": {"limit": limit, "offset": offset, "total": total},
            }
        )


@api_blueprint.route("/stream_execute_vm", methods=["POST"])
def stream_execute_vm():
    """
    API endpoint to execute VM operations with event streaming.
    Accepts a goal and streams each step's execution result using the Vercel AI SDK Data Stream Protocol.
    """

    data = request.json
    goal = data.get("goal")
    response_format = data.get("response_format")
    namespace_name = data.get("namespace_name")
    if not goal:
        return log_and_return_error("Missing 'goal' parameter", "error", 400)

    if response_format and not isinstance(response_format, dict):
        try:
            response_format = json.loads(response_format)
        except json.JSONDecodeError:
            return log_and_return_error(
                "Invalid response format, it should be a json object", "error", 400
            )

    clean_goal, response_format = (
        parse_goal_response_format(goal)
        if not response_format
        else (goal, response_format)
    )
    if not clean_goal:
        return log_and_return_error("Invalid goal format", "error", 400)

    current_app.logger.info(
        f"Receive goal: {clean_goal} with response format: {response_format}"
    )

    def event_stream():
        protocol = StreamingProtocol()

        with SessionLocal() as session:
            try:
                task = ts.create_task(
                    session,
                    clean_goal,
                    datetime.now().strftime("%Y%m%d%H%M%S"),
                    {"response_format": response_format},
                    namespace_name,
                )
                task_id = task.id
                task_branch = task.get_current_branch()
            except Exception as e:
                error_message = f"Error during Goal initilization (goal): {str(e)}"
                current_app.logger.error(error_message, exc_info=True)
                yield protocol.send_error(error_message)

        try:
            current_app.logger.info(f"Starting VM execution with goal: {clean_goal}")
            # Generate Plan
            reasoning, plan = task.generate_plan()
            if not plan:
                error_message = "Failed to generate plan."
                current_app.logger.error(error_message)
                yield protocol.send_error(error_message)
                yield protocol.send_finish_message("error")
                return

            vm = task.create_vm()
            vm.set_plan(reasoning, plan)

            current_app.logger.info(
                "Generated Plan: %s", json.dumps(plan, ensure_ascii=False)
            )

            final_answer_structure = vm.parse_final_answer()
            # Determine the last or second last calling step
            already_streamed = False
            streaming_response_steps = []

            current_app.logger.info(f"final_answer_structure {final_answer_structure}")

            if final_answer_structure:
                if (
                    final_answer_structure.get("is_template", False)
                    or final_answer_structure.get("variables") is None
                ):
                    streaming_response_steps = [
                        final_answer_structure.get("seq_no", -1)
                    ]
                elif len(final_answer_structure.get("variables")) == 1:
                    dependencies_variables = final_answer_structure.get("variables")
                    current_app.logger.info(
                        f"dependencies_variables {dependencies_variables}"
                    )
                    dependencies_steps = vm.parse_dependencies(dependencies_variables)
                    streaming_response_steps = dependencies_steps[
                        dependencies_variables[0]
                    ]

            current_app.logger.info(
                f"streaming_response_steps {streaming_response_steps}"
            )

            # Start executing steps
            while True:
                step = vm.get_current_step()
                step_seq_no = step.get("seq_no", -1)

                if step["type"] == "calling":
                    params = step.get("parameters", {})
                    tool_call_id = step["seq_no"]
                    tool_name = params.get("tool_name", "Unknown")
                    tool_args = params.get("tool_params", {})
                    yield protocol.send_tool_call(tool_call_id, tool_name, tool_args)

                # Pass the queue only to the last calling step
                if step_seq_no in streaming_response_steps:
                    # Execute step in a separate thread when stream_queue is needed
                    step_result = None
                    queue = Queue()

                    def execute_step():
                        nonlocal step_result
                        step_result = vm.step(stream_queue=queue)

                    step_thread = Thread(target=execute_step)
                    step_thread.start()

                    # Consume the queue and yield messages until it's empty
                    while True:
                        try:
                            chunk = queue.get(timeout=1)  # 1-second timeout
                            yield protocol.send_text_part(chunk)
                            already_streamed = True
                        except Empty:
                            if not step_thread.is_alive():
                                break
                            continue

                    # Wait for the thread to finish and get step_result
                    step_thread.join()
                else:
                    # Normal execution without stream_queue
                    step_result = vm.step()

                if not step_result:
                    error_message = "Failed to execute step."
                    current_app.logger.error(error_message)
                    yield protocol.send_state(
                        task_id, task_branch, step_seq_no, vm.state
                    )
                    yield protocol.send_error(error_message)
                    yield protocol.send_finish_message("error")
                    task.task_orm.status = TaskStatus.failed
                    task.task_orm.logs = f"Error during VM execution: {error_message}"
                    task.save()
                    return

                if not step_result.get("success", False):
                    error = step_result.get(
                        "error", "Unknown error during step execution."
                    )
                    current_app.logger.error(f"Error executing step: {error}")
                    yield protocol.send_state(
                        task_id, task_branch, step_seq_no, vm.state
                    )
                    yield protocol.send_error(error)
                    yield protocol.send_finish_message("error")
                    task.task_orm.status = TaskStatus.failed
                    task.task_orm.logs = f"Error during VM execution: {error}"
                    task.save()
                    return

                step_type = step_result.get("step_type")
                params = step_result.get("parameters", {})
                output = step_result.get("output", {})
                seq_no = step_result.get("seq_no", -1)  # -1 means unknown.

                # Tool Call (Part a) if the step is a tool call
                if step_type == "calling":
                    yield protocol.send_tool_result(seq_no, output)

                # Step State (Part 8)
                yield protocol.send_state(task_id, task_branch, step_seq_no, vm.state)
                # Step Finish (Part e)
                yield protocol.send_step_finish(seq_no)

                # Check if goal is completed
                final_answer = None
                if vm.state.get("goal_completed"):
                    current_app.logger.info("Goal completed during plan execution.")
                    # Fetch the final_answer
                    final_answer = vm.get_variable("final_answer")
                    if final_answer:
                        if already_streamed is False:
                            # Stream the final_answer using Part 0
                            for chunk in final_answer.split(". "):
                                if chunk:
                                    if not chunk.endswith("."):
                                        chunk += ". "
                                    yield protocol.send_text_part(chunk)

                    task.mark_as_completed()
                    break

            # Finish Message (Part d)
            yield protocol.send_finish_message(response=final_answer)
        except GeneratorExit:
            current_app.logger.info(f"Client disconnected ({task.id}). Cleaning up.")
            task.task_orm.status = TaskStatus.failed
            task.task_orm.logs = "Execution was interrupted by the client."
            task.save()
            raise
        except PlanUnavailableError as e:
            yield protocol.send_text_part(str(e))
            yield protocol.send_finish_message(response=str(e))
            task.task_orm.status = TaskStatus.completed
            task.task_orm.logs = str(e)
            task.save()
        except Exception as e:
            error_message = f"Error during VM execution ({task.id}): {str(e)}"
            current_app.logger.error(error_message, exc_info=True)
            yield protocol.send_error(error_message)
            task.task_orm.status = TaskStatus.failed
            task.task_orm.logs = f"Error during VM execution: {error_message}"
            task.save()

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "X-Content-Type-Options": "nosniff",
        },
    )


@main_blueprint.route("/best_plans")
def best_plans_page():
    """
    Route to render the Best Plans page.
    """
    return render_template("best_plans.html")
