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
from flask import Blueprint, render_template, jsonify, request, current_app

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
    global_repo,
    get_commits,
    get_vm_state_for_commit,
    get_repo,
    commit_vm_changes,
    repo_exists,
)
from .engine import generate_updated_plan, should_update_plan
from app.services.plan_manager import PlanManager


api_blueprint = Blueprint("api", __name__)

logger = logging.getLogger(__name__)

plan_manager = PlanManager()


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

    repo_path = os.path.join(GIT_REPO_PATH, repo_name) if repo_name else GIT_REPO_PATH
    repo = get_repo(repo_path)
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


@api_blueprint.route("/vm_state/<commit_hash>")
def get_vm_state(commit_hash):
    repo = get_repo(global_repo.get_current_repo_path())
    try:
        commit = repo.commit(commit_hash)
        vm_state = get_vm_state_for_commit(repo, commit)
        if vm_state is None:
            return log_and_return_error(
                f"VM state not found for commit {commit_hash} for {repo}",
                "warning",
                404,
            )
        return jsonify(vm_state)
    except Exception as e:
        return log_and_return_error(
            f"Unexpected error fetching VM state for commit {commit_hash} for {repo}: {str(e)}",
            "error",
            500,
        )


@api_blueprint.route("/code_diff/<commit_hash>")
def code_diff(commit_hash):
    repo = get_repo(global_repo.get_current_repo_path())
    try:
        commit = repo.commit(commit_hash)
        if commit.parents:
            parent = commit.parents[0]
            diff = repo.git.diff(parent, commit, "--unified=3")
        else:
            diff = repo.git.show(commit, "--pretty=format:", "--no-commit-id", "-p")
        return jsonify({"diff": diff})
    except Exception as e:
        return log_and_return_error(
            f"Error generating diff for commit {commit_hash}: {str(e)}", "error", 404
        )


@api_blueprint.route("/commit_details/<commit_hash>")
def commit_details(commit_hash):
    repo = get_repo(global_repo.get_current_repo_path())
    try:
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
            f"Error fetching commit details for {commit_hash} for repo {repo}: {str(e)}",
            "error",
            404,
        )


@api_blueprint.route("/execute_vm", methods=["POST"])
def execute_vm():
    data = request.json
    current_app.logger.info(f"Received execute_vm request with data: {data}")

    commit_hash = data.get("commit_hash")
    suggestion = data.get("suggestion")
    steps = int(data.get("steps", 20))
    repo_name = data.get("repo")
    new_branch = data.get("new_branch")

    if not all([commit_hash, steps, repo_name]):
        return log_and_return_error("Missing required parameters", "error", 400)

    repo_path = global_repo.get_current_repo_path()

    try:
        vm = PlanExecutionVM(
            repo_path, LLMInterface(model=LLM_MODEL, provider=LLM_PROVIDER)
        )
    except ImportError as e:
        return log_and_return_error(str(e), "error", 500)

    vm.set_state(commit_hash)
    repo = git.Repo(repo_path)

    steps_executed = 0
    last_commit_hash = commit_hash

    if not new_branch:
        new_branch = f"re_execute_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    vm.git_manager.create_branch_from_commit(new_branch, commit_hash)
    vm.git_manager.checkout_branch(new_branch)
    current_branch = repo.active_branch.name
    current_app.logger.info(f"Using branch: {current_branch}")

    for _ in range(steps):
        should_update, explanation, key_factors = should_update_plan(vm, suggestion)
        if should_update:
            updated_plan = generate_updated_plan(vm, explanation, key_factors)
            current_app.logger.info(
                "Generated updated plan: %s", json.dumps(updated_plan, indent=2)
            )
            branch_name = f"plan_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if vm.git_manager.create_branch(
                branch_name
            ) and vm.git_manager.checkout_branch(branch_name):
                vm.state["current_plan"] = updated_plan
                vm.recalculate_variable_refs()  # Recalculate variable references
                commit_message_wrapper.set_commit_message(
                    StepType.PLAN_UPDATE,
                    str(vm.state["program_counter"]),
                    explanation,
                    {"updated_plan": updated_plan},
                    {},  # No output variables for this operation
                )
                vm.save_state()

                new_commit_hash = commit_vm_changes(vm)
                if new_commit_hash:
                    last_commit_hash = new_commit_hash
                    current_app.logger.info(
                        f"Resumed execution with updated plan on branch '{branch_name}'. New commit: {new_commit_hash}"
                    )
                else:
                    current_app.logger.error("Failed to commit updated plan")
                    break
            else:
                current_app.logger.error(
                    f"Failed to create or checkout branch '{branch_name}'"
                )
                break

        try:
            success = vm.step()
        except Exception as e:
            error_msg = f"Error during VM step execution: {str(e)}"
            current_app.logger.error(error_msg, exc_info=True)
            return log_and_return_error(error_msg, "error", 500)

        commit_hash = commit_vm_changes(vm)
        if commit_hash:
            last_commit_hash = commit_hash

        steps_executed += 1

        if vm.state.get("goal_completed"):
            current_app.logger.info("Goal completed. Stopping execution.")
            break

    return jsonify(
        {
            "success": True,
            "steps_executed": steps_executed,
            "current_branch": vm.git_manager.get_current_branch(),
            "last_commit_hash": last_commit_hash,
        }
    )


@api_blueprint.route("/optimize_step", methods=["POST"])
def optimize_step():
    data = request.json
    current_app.logger.info(f"Received update_step request with data: {data}")

    commit_hash = data.get("commit_hash")
    suggestion = data.get("suggestion")
    seq_no_str = data.get("seq_no")
    repo_name = data.get("repo")

    if not all([commit_hash, suggestion, seq_no_str, repo_name]):
        return log_and_return_error("Missing required parameters", "error", 400)

    seq_no = int(seq_no_str)
    repo_path = global_repo.get_current_repo_path()

    try:
        vm = PlanExecutionVM(repo_path, LLMInterface(LLM_PROVIDER, LLM_MODEL))
    except ImportError as e:
        return log_and_return_error(str(e), "error", 500)

    vm.set_state(commit_hash)
    repo = git.Repo(repo_path)

    # Generate the updated step using LLM
    prompt = get_step_update_prompt(
        vm,
        seq_no,
        VM_SPEC_CONTENT,
        global_tools_hub.get_tools_description(),
        suggestion,
    )
    updated_step_response = vm.llm_interface.generate(prompt)

    if not updated_step_response:
        return log_and_return_error("Failed to generate updated step", "error", 500)

    updated_step = parse_step(updated_step_response)
    if not updated_step:
        return log_and_return_error(
            f"Failed to parse updated step {updated_step_response}", "error", 500
        )

    logger.info(
        f"Updating step: {updated_step}, program_counter: {vm.state['program_counter']}"
    )

    current_commit = repo.commit(commit_hash)
    if current_commit.parents:
        previous_commit_hash = current_commit.parents[0].hexsha
    else:
        log_and_return_error("Cannot update the first commit", "error", 400)

    # checkout from the previous commit of specified seq_no
    vm.set_state(previous_commit_hash)
    branch_name = f"update_step_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if vm.git_manager.create_branch_from_commit(
        branch_name, previous_commit_hash
    ) and vm.git_manager.checkout_branch(branch_name):
        vm.state["current_plan"][seq_no] = updated_step
        vm.state["program_counter"] = seq_no
        vm.recalculate_variable_refs()  # Recalculate variable references
        commit_message_wrapper.set_commit_message(
            StepType.STEP_OPTIMIZATION,
            str(vm.state["program_counter"]),
            suggestion,
            {"updated_step": updated_step},
            {},  # No output variables for this operation
        )
        vm.save_state()

        new_commit_hash = commit_vm_changes(vm)
        if new_commit_hash:
            last_commit_hash = new_commit_hash
            current_app.logger.info(
                f"Resumed execution with updated plan on branch '{branch_name}'. New commit: {new_commit_hash}"
            )
        else:
            log_and_return_error("Failed to commit step optimization", "error", 500)
    else:
        log_and_return_error(
            f"Failed to create or checkout branch '{branch_name}'", "error", 500
        )

    logger.info(
        f"Updated step: {vm.state['current_plan'][vm.state['program_counter']]}, program_counter: {vm.state['program_counter']}"
    )

    # Re-execute the plan from the updated step
    while True:
        success = vm.step()
        commit_hash = commit_vm_changes(vm)
        if commit_hash:
            last_commit_hash = commit_hash
        if not success:
            break

        if vm.state.get("goal_completed"):
            logger.info("Goal completed during plan execution.")
            break

    if vm.state.get("goal_completed"):
        final_answer = vm.get_variable("final_answer")
        if final_answer:
            logger.info(f"\nfinal_answer: {final_answer}")
        else:
            logger.info("\nNo result was generated.")
    else:
        logger.warning("Plan execution failed or did not complete.")
        logger.error(vm.state.get("errors"))

    return jsonify(
        {
            "success": True,
            "current_branch": vm.git_manager.get_current_branch(),
            "last_commit_hash": last_commit_hash,
        }
    )


@api_blueprint.route("/vm_state_details/<commit_hash>")
def vm_state_details(commit_hash):
    repo = get_repo(global_repo.get_current_repo_path())
    try:
        commit = repo.commit(commit_hash)
        vm_state = get_vm_state_for_commit(repo, commit)

        if vm_state is None:
            return log_and_return_error(
                f"vm_state.json not found for commit: {commit_hash} for repo {repo}",
                "warning",
                404,
            )

        variables = vm_state.get("variables", {})

        return jsonify({"variables": variables})
    except git.exc.BadName:
        return log_and_return_error(
            f"Invalid commit hash: {commit_hash} for repo {repo}", "error", 404
        )
    except Exception as e:
        return log_and_return_error(
            f"Unexpected error: {str(e)} for repo {repo}", "error", 500
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


@api_blueprint.route("/set_repo/<path:repo_name>")
def set_repo(repo_name):
    if repo_exists(repo_name):
        new_repo_path = os.path.join(GIT_REPO_PATH, repo_name)
        global_repo.set_repo(new_repo_path)
        return jsonify({"success": True, "message": f"Repository set to {repo_name}"})
    else:
        return jsonify({"success": False, "message": "Invalid repository path"}), 400


@api_blueprint.route("/get_branches")
def get_branches():
    repo = get_repo(global_repo.get_current_repo_path())
    try:
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
        return log_and_return_error(f"Error fetching branches: {str(e)}", "error", 500)


@api_blueprint.route("/set_branch/<branch_name>")
def set_branch(branch_name):
    repo = get_repo(global_repo.get_current_repo_path())
    try:
        repo.git.checkout(branch_name)
        return jsonify(
            {"success": True, "message": f"Switched to branch {branch_name}"}
        )
    except GitCommandError as e:
        return log_and_return_error(
            f"Error switching to branch {branch_name}: {str(e)}", "error", 400
        )


@api_blueprint.route("/delete_branch/<branch_name>", methods=["POST"])
def delete_branch(branch_name):
    repo = get_repo(global_repo.get_current_repo_path())
    try:
        if branch_name == repo.active_branch.name:
            available_branches = [
                b.name for b in repo.branches if b.name != branch_name
            ]
            if not available_branches:
                return log_and_return_error(
                    "Cannot delete the only branch in the repository", "error", 400
                )

            switch_to = (
                "main" if "main" in available_branches else available_branches[0]
            )
            repo.git.checkout(switch_to)
            current_app.logger.info(
                "Switched to branch %s before deleting %s",
                switch_to,
                branch_name
            )

        repo.git.branch("-D", branch_name)
        return jsonify(
            {
                "success": True,
                "message": f"Branch {branch_name} deleted successfully",
                "new_active_branch": repo.active_branch.name,
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
    Expects JSON payload with 'repo_name' and 'target_directory'.
    """
    data = request.json
    current_app.logger.info(f"Received save_plan request with data: {data}")

    repo_path = global_repo.get_current_repo_path()
    repo_name = os.path.basename(repo_path)
    print(f"repo_name: {repo_name}")
    print(f"repo_path: {repo_path}")
    target_directory = data.get("target_directory")
    print(f"target_directory: {target_directory}")
    print(not repo_name)
    print(not target_directory)

    if not all([repo_name, target_directory]):
        return log_and_return_error("Missing 'repo_name' or 'target_directory' parameters.", "error", 400)

    success = plan_manager.save_current_plan(repo_name, target_directory)

    if success:
        return jsonify({"success": True, "message": f"Plan '{repo_name}' saved successfully to '{target_directory}'."}), 200
    else:
        return log_and_return_error(f"Failed to save plan '{repo_name}' to '{target_directory}'.", "error", 500)
