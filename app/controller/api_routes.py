"""
Visualization module for the VM execution and Git repository management.
"""

import os
import json
import logging
from datetime import datetime

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
)
from app.database import SessionLocal

from .streaming_protocol import StreamingProtocol
from .task import TaskService


api_blueprint = Blueprint("api", __name__, url_prefix="/api")

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


@api_blueprint.route("/tasks/<task_id>/auto_update", methods=["POST"])
def auto_update(task_id):
    """
    API endpoint to auto update the plan and execute the VM.
    """
    data = request.json
    current_app.logger.info(f"Received auto_update request with data: {data}")

    commit_hash = data.get("commit_hash")
    suggestion = data.get("suggestion")
    steps = int(data.get("steps", 20))

    if not all([commit_hash, steps]):
        return log_and_return_error("Missing required parameters", "error", 400)

    with SessionLocal() as session:
        task = ts.get_task(session, task_id)
        if not task:
            return log_and_return_error(
                f"Task with ID {task_id} not found.", "error", 404
            )

    try:
        result = task.auto_update(commit_hash, suggestion=suggestion, steps=steps)
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.error(
            f"Failed to execute VM for task {task_id}: {str(e)}", exc_info=True
        )
        return log_and_return_error("Failed to execute VM.", "error", 500)


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

    def event_stream():
        protocol = StreamingProtocol()

        with SessionLocal() as session:
            task = ts.create_task(
                session, goal, datetime.now().strftime("%Y%m%d%H%M%S")
            )
            task_id = task.id
            task_branch = task.get_current_branch()

        try:
            current_app.logger.info(f"Starting VM execution with goal: {goal}")
            # Generate Plan
            plan = task.generate_plan()
            if not plan:
                error_message = "Failed to generate plan."
                current_app.logger.error(error_message)
                yield protocol.send_error(error_message)
                yield protocol.send_finish_message("error")
                return

            current_app.logger.info("Generated Plan: %s", json.dumps(plan))

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

                step_result = task.vm.step()
                if not step_result:
                    error_message = "Failed to execute step."
                    current_app.logger.error(error_message)
                    yield protocol.send_state(
                        task_id, task_branch, step_seq_no, task.vm.state
                    )
                    yield protocol.send_error(error_message)
                    yield protocol.send_finish_message("error")
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
                    return

                step_type = step_result.get("step_type")
                params = step_result.get("parameters", {})
                output = step_result.get("output", {})
                seq_no = step_result.get("seq_no", -1)  # -1 means unknown.

                # Tool Call (Part 9) if the step is a tool call
                if step_type == "calling":
                    yield protocol.send_tool_result(seq_no, output)

                # Step Finish (Part e)
                yield protocol.send_state(
                    task_id, task_branch, step_seq_no, task.vm.state
                )
                yield protocol.send_step_finish(seq_no)

                # Check if goal is completed
                if task.vm.state.get("goal_completed"):
                    current_app.logger.info("Goal completed during plan execution.")
                    # Fetch the final_answer
                    final_answer = task.vm.get_variable("final_answer")
                    if final_answer:
                        # Stream the final_answer using Part 0
                        # You can customize the chunking strategy as needed
                        for chunk in final_answer.split(". "):
                            if chunk:
                                # Add a period back if it was split
                                if not chunk.endswith("."):
                                    chunk += ". "
                                yield protocol.send_text_part(chunk)
                    task.mark_as_completed()
                    break

            # Finish Message (Part d)
            yield protocol.send_finish_message()

        except Exception as e:
            error_message = f"Error during VM execution: {str(e)}"
            current_app.logger.error(error_message, exc_info=True)
            yield protocol.send_error(error_message)

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "X-Content-Type-Options": "nosniff",
        },
    )
