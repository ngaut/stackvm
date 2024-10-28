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

from app.config.settings import (
    LLM_PROVIDER,
    GIT_REPO_PATH,
    LLM_MODEL,
    VM_SPEC_CONTENT,
    LLM_PROVIDER,
)
from app.services import (
    parse_commit_message,
    StepType,
    parse_step,
)
from app.services import (
    LLMInterface,
    PlanExecutionVM,
    commit_message_wrapper,
    get_step_update_prompt,
)
from app.instructions import global_tools_hub
from .plan_repo import (
    RepoManager,
    get_commits,
    get_vm_state_for_commit,
    commit_vm_changes,
    get_repo,
)
from app.services.plan_manager import PlanManager
from .engine import generate_updated_plan, should_update_plan, generate_plan
from .streaming_protocol import StreamingProtocol
from .task import TaskService


api_blueprint = Blueprint("api", __name__)

logger = logging.getLogger(__name__)

plan_manager = PlanManager()
repo_manager = RepoManager(GIT_REPO_PATH)

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
    repo_name = request.args.get("repo")

    repo = repo_manager.get_repo(repo_name)
    if not repo:
        return jsonify([]), 200
    commits = get_commits(repo, branch)

    vm_states = []
    for commit in commits:
        commit_time = datetime.fromtimestamp(commit.committed_date)
        seq_no, title, details, commit_type = parse_commit_message(commit.message)

        vm_state = get_vm_state_for_commit(repo, commit)

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


@api_blueprint.route("/vm_state/<repo_name>/<commit_hash>")
def get_vm_state(repo_name, commit_hash):
    if not repo_name:
        return log_and_return_error("Missing 'repo' parameter", "error", 400)

    try:
        with repo_manager.lock_repo_for_read(repo_name):
            repo = repo_manager.get_repo(repo_name)
            if not repo:
                return log_and_return_error(
                    f"Repository {repo_name} not found", "error", 404
                )

            commit = repo.commit(commit_hash)
            vm_state = get_vm_state_for_commit(repo, commit)
            if vm_state is None:
                return log_and_return_error(
                    f"VM state not found for commit {commit_hash} for repo {repo_name}",
                    "warning",
                    404,
                )
            return jsonify(vm_state)
    except Exception as e:
        return log_and_return_error(
            f"Unexpected error fetching VM state for commit {commit_hash} for repo {repo_name}: {str(e)}",
            "error",
            500,
        )


@api_blueprint.route("/code_diff/<repo_name>/<commit_hash>")
def code_diff(repo_name, commit_hash):
    try:
        with repo_manager.lock_repo_for_read(repo_name):
            repo = repo_manager.get_repo(repo_name)
            if not repo:
                return log_and_return_error(
                    f"Repository '{repo_name}' not found", "error", 404
                )

            commit = repo.commit(commit_hash)
            if commit.parents:
                parent = commit.parents[0]
                diff = repo.git.diff(parent, commit, "--unified=3")
            else:
                diff = repo.git.show(commit, "--pretty=format:", "--no-commit-id", "-p")
            return jsonify({"diff": diff})
    except Exception as e:
        return log_and_return_error(
            f"Error generating diff for commit {commit_hash} in repository '{repo_name}': {str(e)}",
            "error",
            404,
        )


@api_blueprint.route("/commit_details/<repo_name>/<commit_hash>")
def commit_details(repo_name, commit_hash):
    try:
        with repo_manager.lock_repo_for_read(repo_name):
            repo = repo_manager.get_repo(repo_name)
            if not repo:
                return log_and_return_error(
                    f"Repository '{repo_name}' not found", "error", 404
                )

            commit = repo.commit(commit_hash)

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
            f"Error fetching commit details for {commit_hash} in repository '{repo_name}': {str(e)}",
            "error",
            404,
        )


@api_blueprint.route("/execute_vm", methods=["POST"])
def execute_vm():
    """
    API endpoint to execute VM operations.
    Ensures mutual exclusion using repo_manager.lock_repo_for_write to handle concurrent access.
    """
    data = request.json
    current_app.logger.info(f"Received execute_vm request with data: {data}")

    commit_hash = data.get("commit_hash")
    suggestion = data.get("suggestion")
    steps = int(data.get("steps", 20))
    task_id = data.get("repo")

    if not all([commit_hash, steps, task_id]):
        return log_and_return_error("Missing required parameters", "error", 400)

    task = ts.get_task(task_id)
    if not task:
        return log_and_return_error(f"Task with ID {task_id} not found.", "error", 404)

    try:
        result = task.update(commit_hash, suggestion=suggestion, steps=steps)
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
    task_id = data.get("repo")

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


@api_blueprint.route("/vm_state_details/<repo_name>/<commit_hash>")
def vm_state_details(repo_name, commit_hash):
    try:
        with repo_manager.lock_repo_for_read(repo_name):
            repo = repo_manager.get_repo(repo_name)
            if not repo:
                return log_and_return_error(
                    f"Repository '{repo_name}' not found", "error", 404
                )

            commit = repo.commit(commit_hash)
            vm_state = get_vm_state_for_commit(repo, commit)

            if vm_state is None:
                return log_and_return_error(
                    f"vm_state.json not found for commit: {commit_hash} in repository '{repo_name}'",
                    "warning",
                    404,
                )

            variables = vm_state.get("variables", {})

            return jsonify({"variables": variables})
    except git.exc.BadName:
        return log_and_return_error(
            f"Invalid commit hash: {commit_hash} in repository '{repo_name}'",
            "error",
            404,
        )
    except Exception as e:
        return log_and_return_error(
            f"Unexpected error: {str(e)} in repository '{repo_name}'", "error", 500
        )


@api_blueprint.route("/get_directories")
def get_directories():
    try:
        directories = [
            d
            for d in os.listdir(GIT_REPO_PATH)
            if os.path.isdir(os.path.join(GIT_REPO_PATH, d))
        ]
        # filter out .git directories
        directories = [d for d in directories if not d.endswith(".git")]
        return jsonify(directories)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_blueprint.route("/get_branches/<repo_name>")
def get_branches(repo_name):
    try:
        with repo_manager.lock_repo_for_read(repo_name):
            repo = repo_manager.get_repo(repo_name)
            if not repo:
                return log_and_return_error(
                    f"Repository '{repo_name}' not found", "error", 404
                )

            branches = repo.branches
            branch_data = [
                {
                    "name": branch.name,
                    "last_commit_date": branch.commit.committed_datetime.isoformat(),
                    "last_commit_message": branch.commit.message.split("\n")[0],
                    "is_active": branch.name == repo.active_branch.name,
                }
                for branch in branches
            ]
            branch_data.sort(
                key=lambda x: (-x["is_active"], x["last_commit_date"]), reverse=True
            )
            return jsonify(branch_data)
    except GitCommandError as e:
        return log_and_return_error(
            f"Error fetching branches for repository '{repo_name}': {str(e)}",
            "error",
            500,
        )


@api_blueprint.route("/set_branch/<repo_name>/<branch_name>")
def set_branch_route(repo_name, branch_name):
    """
    API endpoint to switch to a specified branch within a repository.

    Args:
        repo_name (str): The name of the repository.
        branch_name (str): The name of the branch to switch to.

    Returns:
        JSON response indicating success or failure.
    """
    try:
        with repo_manager.lock_repo_for_write(repo_name):
            repo = repo_manager.get_repo(repo_name)
            if not repo:
                return log_and_return_error(
                    f"Repository '{repo_name}' not found", "error", 404
                )

            try:
                repo.git.checkout(branch_name)
                return jsonify(
                    {
                        "success": True,
                        "message": f"Switched to branch {branch_name} in repository '{repo_name}'",
                    }
                )
            except GitCommandError as e:
                return log_and_return_error(
                    f"Error switching to branch {branch_name}: {str(e)}", "error", 400
                )
    except TimeoutError as e:
        return log_and_return_error(str(e), "error", 500)
    except Exception as e:
        current_app.logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return log_and_return_error("An unexpected error occurred.", "error", 500)


@api_blueprint.route("/delete_branch/<repo_name>/<branch_name>", methods=["POST"])
def delete_branch_route(repo_name, branch_name):
    """
    API endpoint to delete a specified branch within a repository.

    Args:
        repo_name (str): The name of the repository.
        branch_name (str): The name of the branch to delete.

    Returns:
        JSON response indicating success or failure.
    """
    try:
        with repo_manager.lock_repo_for_write(repo_name):
            repo = repo_manager.get_repo(repo_name)
            if not repo:
                return log_and_return_error(
                    f"Repository '{repo_name}' not found", "error", 404
                )

            try:
                if branch_name == repo.active_branch.name:
                    available_branches = [
                        b.name for b in repo.branches if b.name != branch_name
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
                    repo.git.checkout(switch_to)
                    current_app.logger.info(
                        f"Switched to branch {switch_to} before deleting {branch_name}"
                    )

                repo.git.branch("-D", branch_name)
                return jsonify(
                    {
                        "success": True,
                        "message": f"Branch {branch_name} deleted successfully in repository '{repo_name}'",
                        "new_active_branch": repo.active_branch.name,
                    }
                )
            except GitCommandError as e:
                return log_and_return_error(
                    f"Error deleting branch {branch_name}: {str(e)}", "error", 400
                )
    except TimeoutError as e:
        return log_and_return_error(str(e), "error", 500)
    except Exception as e:
        current_app.logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return log_and_return_error("An unexpected error occurred.", "error", 500)


@api_blueprint.route("/save_plan", methods=["POST"])
def save_plan():
    """
    API endpoint to save the current plan's project directory to a specified folder.
    Expects JSON payload with 'repo_name' and 'target_directory'.
    """
    data = request.json
    current_app.logger.info(f"Received save_plan request with data: {data}")

    repo_name = data.get("repo_name")
    target_directory = data.get("target_directory")

    if not all([repo_name, target_directory]):
        return log_and_return_error(
            "Missing 'repo_name' or 'target_directory' parameters.", "error", 400
        )

    try:
        with repo_manager.lock_repo_for_write(repo_name):
            repo = repo_manager.get_repo(repo_name)
            if not repo:
                return log_and_return_error(
                    f"Repository '{repo_name}' not found", "error", 404
                )

            success = plan_manager.save_current_plan(repo, target_directory)

            if success:
                return (
                    jsonify(
                        {
                            "success": True,
                            "message": f"Plan '{repo_name}' saved successfully to '{target_directory}'.",
                        }
                    ),
                    200,
                )
            else:
                return log_and_return_error(
                    f"Failed to save plan '{repo_name}' to '{target_directory}'.",
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
    task = ts.create_task(goal, repo_path)

    def event_stream(task_id, vm):
        protocol = StreamingProtocol()
        try:
            current_app.logger.info(f"Starting VM execution with goal: {goal}")
            vm.set_goal(goal)

            # Generate Plan
            plan = generate_plan(vm.llm_interface, goal)
            if not plan:
                error_message = "Failed to generate plan."
                current_app.logger.error(error_message)
                yield protocol.send_error(error_message)
                yield protocol.send_finish_message('error')
                return

            vm.state["current_plan"] = plan
            current_app.logger.info("Generated Plan: %s", json.dumps(plan))

            # Start executing steps
            while True:
                step = vm.get_current_step()
                if step['type'] == "calling":
                    params = step.get("parameters", {})
                    tool_call_id = step["seq_no"]
                    tool_name = params.get("tool", "Unknown")
                    tool_args = params.get("params", {})
                    yield protocol.send_tool_call(tool_call_id, tool_name, tool_args)

                step_result = vm.step()
                if not step_result:
                    error_message = "Failed to execute step."
                    current_app.logger.error(error_message)
                    yield protocol.send_state(task_id, vm.state)
                    yield protocol.send_error(error_message)
                    yield protocol.send_finish_message('error')
                    return

                if not step_result.get("success", False):
                    error = step_result.get(
                        "error", "Unknown error during step execution."
                    )
                    current_app.logger.error(f"Error executing step: {error}")
                    yield protocol.send_state(task_id, vm.state)
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
                yield protocol.send_state(task_id, vm.state)
                yield protocol.send_step_finish(seq_no)

                # Check if goal is completed
                if vm.state.get("goal_completed"):
                    current_app.logger.info("Goal completed during plan execution.")
                    # Fetch the final_answer
                    final_answer = vm.get_variable("final_answer")
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

    return Response(stream_with_context(event_stream(task.id(), task.vm)), mimetype="text/event-stream", headers={
        "X-Content-Type-Options": "nosniff",
    })
