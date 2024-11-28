"""
Visualization module for the VM execution and Git repository management.
"""

import os
import json
import logging
from datetime import datetime
from queue import Queue, Empty
from threading import Thread

import git
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

from app.database import SessionLocal
from app.config.settings import (
    BACKEND_CORS_ORIGINS,
    GIT_REPO_PATH,
    GENERATED_FILES_DIR,
    TASK_QUEUE_WORKERS,
)
from app.utils import parse_goal_requirements

from .streaming_protocol import StreamingProtocol
from .task import TaskService
from .task_queue import TaskQueue
from .label_classifier import get_label_path

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

# create global task queue instance
task_queue = TaskQueue(max_concurrent_tasks=TASK_QUEUE_WORKERS)
task_queue.start_workers()


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
                f"Error generating diff for commit {commit_hash} in repository '{task.repo_path}': {str(e)}",
                "error",
                404,
            )


@api_blueprint.route("/tasks/<task_id>/update", methods=["POST"])
def update_task(task_id):
    """
    API endpoint to update the plan and execute the VM.
    """
    data = request.json
    current_app.logger.info(f"Received update_task request with data: {data}")

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
        branch_name = f"plan_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if not task.create_branch(branch_name, commit_hash):
            return log_and_return_error(
                f"[Update Task] Failed to create branch {branch_name} for task {task_id}.",
                "error",
                500,
            )

        task_queue.add_task(
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


@api_blueprint.route("/tasks/<task_id>/dynamic_update", methods=["POST"])
def dynamic_update(task_id):
    """
    API endpoint to dynamic update the plan and execute the VM.
    """
    data = request.json
    current_app.logger.info(f"Received dynamic_update request with data: {data}")

    commit_hash = data.get("commit_hash")
    suggestion = data.get("suggestion")
    steps = int(data.get("steps", 20))

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
        if not task.create_branch(branch_name, commit_hash):
            return log_and_return_error(
                f"[Dynamic Update Task] Failed to create branch {branch_name} for task {task_id}.",
                "error",
                500,
            )

        task_queue.add_task(
            task_id,
            {
                "new_branch_name": branch_name,
                "commit_hash": commit_hash,
                "suggestion": suggestion,
                "steps": steps,
            },
            task.dynamic_update,
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
                    "status": task.status,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                    "logs": task.logs,
                    "repo_path": task.repo_path,
                    "tenant_id": task.tenant_id,
                    "project_id": task.project_id,
                    "best_plan": task.best_plan,
                }
                for task in tasks
            ]
            return jsonify(
                {"tasks": task_ids, "pagination": {"limit": limit, "offset": offset}}
            )
    except Exception as e:
        current_app.logger.error(f"Error fetching tasks: {str(e)}", exc_info=True)
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
                f"Error fetching branches for repository '{task.repo_path}': {str(e)}",
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
                    "message": f"Switched to branch {branch_name} in repository '{task.repo_path}'",
                }
            )
        except GitCommandError as e:
            return log_and_return_error(
                f"Error switching to branch {branch_name}: {str(e)}", "error", 400
            )


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
                    "message": f"Branch {branch_name} deleted successfully in repository '{task.repo_path}'",
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
    if not goal:
        return log_and_return_error("Missing 'goal' parameter", "error", 400)

    clean_goal, requirements = parse_goal_requirements(goal)
    if not clean_goal:
        return log_and_return_error("Invalid goal format", "error", 400)

    current_app.logger.info(
        f"Receive goal: {clean_goal} with requirements: {requirements}"
    )

    def event_stream():
        protocol = StreamingProtocol()

        with SessionLocal() as session:
            task = ts.create_task(
                session,
                clean_goal,
                datetime.now().strftime("%Y%m%d%H%M%S"),
                {
                    "requirements": requirements
                },
            )
            task_id = task.id
            task_branch = task.get_current_branch()

        try:
            current_app.logger.info(f"Starting VM execution with goal: {clean_goal}")
            # Generate Plan
            plan = task.generate_plan()
            if not plan:
                error_message = "Failed to generate plan."
                current_app.logger.error(error_message)
                yield protocol.send_error(error_message)
                yield protocol.send_finish_message("error")
                return

            current_app.logger.info("Generated Plan: %s", json.dumps(plan))

            final_answer_structure = task.vm.parse_final_answer()
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
                    dependencies_steps = task.vm.parse_dependencies(
                        dependencies_variables
                    )
                    streaming_response_steps = dependencies_steps[
                        dependencies_variables[0]
                    ]

            current_app.logger.info(
                f"streaming_response_steps {streaming_response_steps}"
            )

            # Start executing steps
            while True:
                step = task.vm.get_current_step()
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
                        step_result = task.vm.step(stream_queue=queue)

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
                    step_result = task.vm.step()

                if not step_result:
                    error_message = "Failed to execute step."
                    current_app.logger.error(error_message)
                    yield protocol.send_state(
                        task_id, task_branch, step_seq_no, task.vm.state
                    )
                    yield protocol.send_error(error_message)
                    yield protocol.send_finish_message("error")
                    task.task_orm.status = "failed"
                    task.task_orm.logs = f"Error during VM execution: {error_message}"
                    task.save()
                    return

                if not step_result.get("success", False):
                    error = step_result.get(
                        "error", "Unknown error during step execution."
                    )
                    current_app.logger.error(f"Error executing step: {error}")
                    yield protocol.send_state(
                        task_id, task_branch, step_seq_no, task.vm.state
                    )
                    yield protocol.send_error(error)
                    yield protocol.send_finish_message("error")
                    task.task_orm.status = "failed"
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
                yield protocol.send_state(
                    task_id, task_branch, step_seq_no, task.vm.state
                )
                # Step Finish (Part e)
                yield protocol.send_step_finish(seq_no)

                # Check if goal is completed
                final_answer = None
                if task.vm.state.get("goal_completed"):
                    current_app.logger.info("Goal completed during plan execution.")
                    # Fetch the final_answer
                    final_answer = task.vm.get_variable("final_answer")
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
            task.task_orm.status = "failed"
            task.task_orm.logs = "Execution was interrupted by the client."
            task.save()
            raise
        except Exception as e:
            error_message = f"Error during VM execution ({task.id}): {str(e)}"
            current_app.logger.error(error_message, exc_info=True)
            yield protocol.send_error(error_message)
            task.task_orm.status = "failed"
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
