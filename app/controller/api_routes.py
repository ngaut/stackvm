"""
Visualization module for the VM execution and Git repository management.
"""

import os
import json
import logging
from datetime import datetime

import git
from git import NULL_TREE
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
from app.config.settings import GIT_REPO_PATH
from app.services import parse_commit_message
from app.services.plan_manager import PlanManager

from .streaming_protocol import StreamingProtocol
from .task import TaskService


api_blueprint = Blueprint("api", __name__)

logger = logging.getLogger(__name__)

plan_manager = PlanManager()

ts = TaskService()

def log_and_return_error(message, error_type, status_code):
    if error_type == "warning":
        current_app.logger.warning("%s", message)
    elif error_type == "error":
        current_app.logger.error("%s", message)
    else:
        current_app.logger.info("%s", message)
    return jsonify({"error": message}), status_code


@api_blueprint.route("/")
def index():
    return render_template("index.html")


@api_blueprint.route("/vm_data")
def get_vm_data():
    branch = request.args.get("branch", "main")
    task_id = request.args.get("task_id")

    task = ts.get_task(task_id)
    if not task:
        return jsonify([]), 200

    commits = task.git_manager.get_commits(branch)

    vm_states = []
    for commit in commits:
        commit_time = datetime.fromtimestamp(commit.committed_date)
        seq_no, title, details, commit_type = parse_commit_message(commit.message)

        vm_state = task.git_manager.load_commit_state(commit.hexsha)
        vm_states.append(
            {
                "time": commit_time.isoformat(),
                "title": title,
                "details": details,
                "commit_hash": commit.hexsha,
                "seq_no": seq_no,
                "vm_state": vm_state,
                "commit_type": commit_type,
            }
        )

    return jsonify(vm_states)


@api_blueprint.route("/vm_state/<task_id>/<commit_hash>")
def get_vm_state(task_id, commit_hash):
    task = ts.get_task(task_id)
    if not task:
        return log_and_return_error(f"Task with ID {task_id} not found.", "error", 404)

    try:
        vm_state = task.git_manager.load_commit_state(commit_hash)
        if vm_state is None:
            return log_and_return_error(
                f"VM state not found for commit {commit_hash} for repo {task.repo_path}",
                "warning",
                404,
            )
        return jsonify(vm_state)
    except Exception as e:
        return log_and_return_error(
            f"Unexpected error fetching VM state for commit {commit_hash} for repo {task.repo_path}: {str(e)}",
            "error",
            500,
        )


@api_blueprint.route("/code_diff/<task_id>/<commit_hash>")
def code_diff(task_id, commit_hash):
    task = ts.get_task(task_id)
    if not task:
        return log_and_return_error(f"Task with ID {task_id} not found.", "error", 404)

    try:
        diff = task.git_manager.get_code_diff(commit_hash)
        return jsonify({"diff": diff})
    except Exception as e:
        return log_and_return_error(
            f"Error generating diff for commit {commit_hash} in repository '{task.repo_path}': {str(e)}",
            "error",
            404,
        )


@api_blueprint.route("/commit_details/<task_id>/<commit_hash>")
def commit_details(task_id, commit_hash):
    task = ts.get_task(task_id)
    if not task:
        return log_and_return_error(f"Task with ID {task_id} not found.", "error", 404)

    try:
        commit = task.git_manager.get_commit(commit_hash)

        if commit.parents:
            diff = commit.diff(commit.parents[0])
        else:
            diff = commit.diff(NULL_TREE)

        seq_no, _, _, _ = parse_commit_message(commit.message)
        details = {
            "hash": commit.hexsha,
            "author": commit.author.name,
            "date": commit.committed_datetime.isoformat(),
            "message": commit.message,
            "seq_no": seq_no,
            "files_changed": [item.a_path for item in diff],
        }
        return jsonify(details)
    except Exception as e:
        return log_and_return_error(
            f"Error fetching commit details for {commit_hash} in repository '{task.repo_path}': {str(e)}",
            "error",
            404,
        )


@api_blueprint.route("/execute_vm", methods=["POST"])
def execute_vm():
    """
    API endpoint to execute VM operations.
    """
    data = request.json
    current_app.logger.info(f"Received execute_vm request with data: {data}")

    commit_hash = data.get("commit_hash")
    suggestion = data.get("suggestion")
    steps = int(data.get("steps", 20))
    task_id = data.get("task_id")

    if not all([commit_hash, steps, task_id]):
        return log_and_return_error("Missing required parameters", "error", 400)

    task = ts.get_task(task_id)
    if not task:
        return log_and_return_error(f"Task with ID {task_id} not found.", "error", 404)

    try:
        result = task.auto_update(commit_hash, suggestion=suggestion, steps=steps)
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.error(f"Failed to execute VM for task {task_id}: {str(e)}", exc_info=True)
        return log_and_return_error("Failed to execute VM.", "error", 500)


@api_blueprint.route("/optimize_step", methods=["POST"])
def optimize_step():
    data = request.json
    current_app.logger.info(f"Received update_step request with data: {data}")

    commit_hash = data.get("commit_hash")
    suggestion = data.get("suggestion")
    seq_no_str = data.get("seq_no")
    task_id = data.get("task_id")

    if not all([commit_hash, suggestion, seq_no_str, task_id]):
        return log_and_return_error("Missing required parameters", "error", 400)

    seq_no = int(seq_no_str)
    task = ts.get_task(task_id)
    if not task:
        return log_and_return_error(f"Task with ID {task_id} not found.", "error", 404)

    try:
        result = task.optimize_step(commit_hash, seq_no, suggestion)
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.error(f"Failed to optimize step {seq_no} for task {task_id}: {str(e)}", exc_info=True)
        return log_and_return_error("Failed to optimize step.", "error", 500)


@api_blueprint.route("/vm_state_details/<task_id>/<commit_hash>")
def vm_state_details(task_id, commit_hash):
    task = ts.get_task(task_id)
    if not task:
        return log_and_return_error(f"Task with ID {task_id} not found.", "error", 404)

    try:
        vm_state = task.git_manager.load_commit_state(commit_hash)
        if vm_state is None:
            return log_and_return_error(
                f"vm_state.json not found for commit: {commit_hash} in repository '{task.repo_path}'",
                "warning",
                404,
            )

        variables = vm_state.get("variables", {})

        return jsonify({"variables": variables})
    except git.exc.BadName:
        return log_and_return_error(
            f"Invalid commit hash: {commit_hash} in repository '{task.repo_path}'",
            "error",
            404,
        )
    except Exception as e:
        return log_and_return_error(
            f"Unexpected error: {str(e)} in repository '{task.repo_path}'", "error", 500
        )


@api_blueprint.route("/get_tasks")
def get_tasks():
    try:
        tasks = ts.list_tasks()
        task_ids = [task.id for task in tasks]
        return jsonify(task_ids)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_blueprint.route("/get_branches/<task_id>")
def get_branches(task_id):
    try:
        task = ts.get_task(task_id)
        if not task:
            return log_and_return_error(f"Task with ID {task_id} not found.", "error", 404)

        branches = task.git_manager.list_branches()
        branch_data = [
            {
                "name": branch.name,
                "last_commit_date": branch.commit.committed_datetime.isoformat(),
                "last_commit_message": branch.commit.message.split("\n")[0],
                "is_active": branch.name == task.git_manager.get_current_branch(),
            }
            for branch in branches
        ]
        branch_data.sort(
            key=lambda x: (-x["is_active"], x["last_commit_date"]), reverse=True
        )
        return jsonify(branch_data)
    except GitCommandError as e:
        return log_and_return_error(
            f"Error fetching branches for repository '{task.repo_path}': {str(e)}",
            "error",
            500,
        )


@api_blueprint.route("/set_branch/<task_id>/<branch_name>")
def set_branch_route(task_id, branch_name):
    """
    API endpoint to switch to a specified branch within a repository.

    Args:
        task_id (str): The ID of the task.
        branch_name (str): The name of the branch to switch to.

    Returns:
        JSON response indicating success or failure.
    """
    task = ts.get_task(task_id)
    if not task:
        return log_and_return_error(f"Task with ID {task_id} not found.", "error", 404)

    try:
        task.git_manager.checkout_branch(branch_name)
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


@api_blueprint.route("/delete_branch/<task_id>/<branch_name>", methods=["POST"])
def delete_branch_route(task_id, branch_name):
    """
    API endpoint to delete a specified branch within a repository.

    Args:
        task_id (str): The ID of the task.
        branch_name (str): The name of the branch to delete.

    Returns:
        JSON response indicating success or failure.
    """
    task = ts.get_task(task_id)
    if not task:
        return log_and_return_error(f"Task with ID {task_id} not found.", "error", 404)

    try:
        if branch_name == task.git_manager.get_current_branch():
            available_branches = [
                b.name for b in task.git_manager.list_branches() if b.name != branch_name
            ]
            if not available_branches:
                return log_and_return_error(
                    "Cannot delete the only branch in the repository",
                    "error",
                    400,
                )

            switch_to = (
                "main"
                if "main" in available_branches
                else available_branches[0]
            )
            task.git_manager.checkout_branch(switch_to)
            current_app.logger.info(
                f"Switched to branch {switch_to} before deleting {branch_name}"
            )

        task.git_manager.delete_branch(branch_name)
        return jsonify(
            {
                "success": True,
                "message": f"Branch {branch_name} deleted successfully in repository '{task.repo_path}'",
                "new_active_branch": task.git_manager.get_current_branch(),
            }
        )
    except GitCommandError as e:
        return log_and_return_error(
            f"Error deleting branch {branch_name}: {str(e)}", "error", 400
        )

@api_blueprint.route("/save_plan", methods=["POST"])
def save_plan():
    """
    API endpoint to save the current plan's project directory to a specified folder.
    Expects JSON payload with 'task_id' and 'target_directory'.
    """
    data = request.json
    current_app.logger.info(f"Received save_plan request with data: {data}")

    task_id = data.get("task_id")
    target_directory = data.get("target_directory")

    if not all([task_id, target_directory]):
        return log_and_return_error(
            "Missing 'task_id' or 'target_directory' parameters.", "error", 400
        )

    try:
        task = ts.get_task(task_id)
        if not task:
            return log_and_return_error(f"Task with ID {task_id} not found.", "error", 404)
        repo = get_repo(task.repo_path)
        if not repo:
            return log_and_return_error(
                f"Repository '{task.repo_path}' not found for task {task_id}", "error", 404
            )

        success = plan_manager.save_current_plan(repo, target_directory)

        if success:
            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Plan '{task.repo_path}' saved successfully to '{target_directory}'.",
                    }
                ),
                200,
            )
        else:
            return log_and_return_error(
                f"Failed to save plan '{task.repo_path}' to '{target_directory}'.",
                "error",
                500,
            )
    except TimeoutError as e:
        return log_and_return_error(str(e), "error", 500)
    except Exception as e:
        current_app.logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return log_and_return_error("An unexpected error occurred.", "error", 500)


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
    repo_path = os.path.join(
        GIT_REPO_PATH, datetime.now().strftime("%Y%m%d%H%M%S")
    )

    def event_stream():
        protocol = StreamingProtocol()
        task = ts.create_task(goal, repo_path)
        task_id = task.id

        try:
            current_app.logger.info(f"Starting VM execution with goal: {goal}")
            # Generate Plan
            plan = task.generate_plan()
            if not plan:
                error_message = "Failed to generate plan."
                current_app.logger.error(error_message)
                yield protocol.send_error(error_message)
                yield protocol.send_finish_message('error')
                return

            current_app.logger.info("Generated Plan: %s", json.dumps(plan))

            # Start executing steps
            while True:
                step = task.vm.get_current_step()
                if step['type'] == "calling":
                    params = step.get("parameters", {})
                    tool_call_id = step["seq_no"]
                    tool_name = params.get("tool", "Unknown")
                    tool_args = params.get("params", {})
                    yield protocol.send_tool_call(tool_call_id, tool_name, tool_args)

                step_result = task.vm.step()
                if not step_result:
                    error_message = "Failed to execute step."
                    current_app.logger.error(error_message)
                    yield protocol.send_state(task_id, task.vm.state)
                    yield protocol.send_error(error_message)
                    yield protocol.send_finish_message('error')
                    return

                if not step_result.get("success", False):
                    error = step_result.get(
                        "error", "Unknown error during step execution."
                    )
                    current_app.logger.error(f"Error executing step: {error}")
                    yield protocol.send_state(task_id, task.vm.state)
                    yield protocol.send_error(error)
                    yield protocol.send_finish_message('error')
                    return

                step_type = step_result.get("step_type")
                params = step_result.get("parameters", {})
                output = step_result.get("output", {})
                seq_no = step_result.get("seq_no", -1)  # -1 means unknown.

                # Tool Call (Part 9) if the step is a tool call
                if step_type == "calling":
                    yield protocol.send_tool_result(seq_no, output)

                # Step Finish (Part e)
                yield protocol.send_state(task_id, task.vm.state)
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
                                    chunk += "."
                                yield protocol.send_text_part(chunk)
                    break

            # Finish Message (Part d)
            yield protocol.send_finish_message()

        except Exception as e:
            error_message = f"Error during VM execution: {str(e)}"
            current_app.logger.error(error_message, exc_info=True)
            yield protocol.send_error(error_message)

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream", headers={
        "X-Content-Type-Options": "nosniff",
    })
