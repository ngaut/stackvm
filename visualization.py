"""
Visualization module for the VM execution and Git repository management.
"""

import sys
import os
import json
import logging
import argparse
from datetime import datetime

import git
from git import Repo, NULL_TREE
from git.exc import GitCommandError
from flask import Flask, render_template, jsonify, request, current_app

from config import GIT_REPO_PATH, VM_SPEC_CONTENT, LLM_MODEL
from git_manager import GitManager
from utils import (
    save_state,
    parse_commit_message,
    StepType,
    find_first_json_object,
    parse_plan,
    parse_step,
)
from vm import PlanExecutionVM
from llm_interface import LLMInterface
from prompts import (
    get_plan_update_prompt,
    get_should_update_plan_prompt,
    get_generate_plan_prompt,
    get_step_update_prompt,
)
from commit_message_wrapper import commit_message_wrapper

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Initialize Flask app
app = Flask(__name__)

# Initialize LLM interface
llm_interface = LLMInterface(LLM_MODEL)

# Initialize GitManager
git_manager = GitManager(GIT_REPO_PATH)


def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    )
    app.logger.setLevel(logging.INFO)
    for handler in app.logger.handlers:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
            )
        )


setup_logging()


def get_repo(repo_path):
    """Initialize and return a Git repository object."""
    try:
        return Repo(repo_path)
    except Exception as exc:
        app.logger.error(
            "Failed to initialize repository at %s: %s",
            repo_path,
            str(exc),
            exc_info=True,
        )
        return None


def get_commits(repo, branch_name):
    """Fetch commits for a given branch."""
    try:
        return list(repo.iter_commits(branch_name))
    except GitCommandError as exc:
        app.logger.error(
            "Error fetching commits for branch %s: %s",
            branch_name,
            str(exc),
            exc_info=True,
        )
        return []


def get_vm_state_for_commit(repo, commit):
    """Retrieve VM state from a specific commit."""
    try:
        vm_state_content = repo.git.show(f"{commit.hexsha}:vm_state.json")
        return json.loads(vm_state_content)
    except GitCommandError:
        app.logger.error("vm_state.json not found in commit %s", commit.hexsha)
    except json.JSONDecodeError:
        app.logger.error("Invalid JSON in vm_state.json for commit %s", commit.hexsha)
    return None


def log_and_return_error(message, error_type, status_code):
    if error_type == "warning":
        current_app.logger.warning(message)
    elif error_type == "error":
        current_app.logger.error(message)
    else:
        current_app.logger.info(message)
    return jsonify({"error": message}), status_code


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/vm_data")
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


@app.route("/vm_state/<commit_hash>")
def get_vm_state(commit_hash):
    repo = get_repo(get_current_repo_path())
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


@app.route("/code_diff/<commit_hash>")
def code_diff(commit_hash):
    repo = get_repo(get_current_repo_path())
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


@app.route("/commit_details/<commit_hash>")
def commit_details(commit_hash):
    repo = get_repo(get_current_repo_path())
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


def generate_plan(goal, custom_prompt=None):
    if not goal:
        app.logger.error("No goal is set.")
        return []

    prompt = custom_prompt or get_generate_plan_prompt(goal, VM_SPEC_CONTENT)
    plan_response = llm_interface.generate(prompt)

    app.logger.info(f"Generating plan using LLM: {plan_response}")

    if not plan_response:
        app.logger.error(f"LLM failed to generate a response: {plan_response}")
        return []

    plan = parse_plan(plan_response)

    if plan:
        return plan
    else:
        app.logger.error(f"Failed to parse the generated plan: {plan_response}")
        return []


def generate_updated_plan(vm: PlanExecutionVM, explanation: str, key_factors: list):
    prompt = get_plan_update_prompt(vm, VM_SPEC_CONTENT, explanation, key_factors)
    new_plan = generate_plan(vm.state["goal"], custom_prompt=prompt)
    return new_plan


def should_update_plan(vm: PlanExecutionVM):
    if vm.state.get("errors"):
        app.logger.info("Plan update triggered due to errors.")
        return (
            True,
            "Errors detected in VM state",
            [{"factor": "VM errors", "impact": "Critical"}],
        )

    prompt = get_should_update_plan_prompt(vm)
    response = llm_interface.generate(prompt)

    json_response = find_first_json_object(response)
    if json_response:
        analysis = json.loads(json_response)
    else:
        app.logger.error("No valid JSON object found in the response.")
        return False, "No valid JSON object found.", []

    should_update = analysis.get("should_update", False)
    explanation = analysis.get("explanation", "")
    key_factors = analysis.get("key_factors", [])

    if should_update:
        app.logger.info(f"LLM suggests updating the plan: {explanation}")
        for factor in key_factors:
            app.logger.info(f"Factor: {factor['factor']}, Impact: {factor['impact']}")
    else:
        app.logger.info(f"LLM suggests keeping the current plan: {explanation}")

    return should_update, explanation, key_factors


@app.route("/execute_vm", methods=["POST"])
def execute_vm():
    data = request.json
    app.logger.info(f"Received execute_vm request with data: {data}")

    commit_hash = data.get("commit_hash")
    steps = int(data.get("steps", 20))
    repo_name = data.get("repo")
    new_branch = data.get("new_branch")

    if not all([commit_hash, steps, repo_name]):
        return log_and_return_error("Missing required parameters", "error", 400)

    repo_path = get_current_repo_path()

    try:
        vm = PlanExecutionVM(repo_path, llm_interface)
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
    app.logger.info(f"Using branch: {current_branch}")

    for _ in range(steps):
        try:
            success = vm.step()
        except Exception as e:
            error_msg = f"Error during VM step execution: {str(e)}"
            app.logger.error(error_msg, exc_info=True)
            return log_and_return_error(error_msg, "error", 500)

        commit_hash = commit_vm_changes(vm)
        if commit_hash:
            last_commit_hash = commit_hash

        should_update, explanation, key_factors = should_update_plan(vm)
        if should_update:
            updated_plan = generate_updated_plan(vm, explanation, key_factors)
            app.logger.info(f"Generated updated plan: {updated_plan}")

            branch_name = f"plan_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if vm.git_manager.create_branch(
                branch_name
            ) and vm.git_manager.checkout_branch(branch_name):
                vm.state["current_plan"] = updated_plan
                vm.recalculate_variable_refs()  # Recalculate variable references
                commit_message_wrapper.set_commit_message(
                    StepType.PLAN_UPDATE, vm.state["program_counter"], explanation
                )
                vm.save_state()

                new_commit_hash = commit_vm_changes(vm)
                if new_commit_hash:
                    last_commit_hash = new_commit_hash
                    app.logger.info(
                        f"Resumed execution with updated plan on branch '{branch_name}'. New commit: {new_commit_hash}"
                    )
                else:
                    app.logger.error("Failed to commit updated plan")
                    break
            else:
                app.logger.error(f"Failed to create or checkout branch '{branch_name}'")
                break

        steps_executed += 1

        if vm.state.get("goal_completed"):
            app.logger.info("Goal completed. Stopping execution.")
            break

    return jsonify(
        {
            "success": True,
            "steps_executed": steps_executed,
            "current_branch": vm.git_manager.get_current_branch(),
            "last_commit_hash": last_commit_hash,
        }
    )


@app.route("/optimize_step", methods=["POST"])
def optimize_step():
    data = request.json
    app.logger.info(f"Received update_step request with data: {data}")

    commit_hash = data.get("commit_hash")
    suggestion = data.get("suggestion")
    seq_no_str = data.get("seq_no")
    repo_name = data.get("repo")

    if not all([commit_hash, suggestion, seq_no_str, repo_name]):
        return log_and_return_error("Missing required parameters", "error", 400)

    seq_no = int(seq_no_str)
    repo_path = get_current_repo_path()

    try:
        vm = PlanExecutionVM(repo_path, llm_interface)
    except ImportError as e:
        return log_and_return_error(str(e), "error", 500)

    vm.set_state(commit_hash)
    repo = git.Repo(repo_path)

    # Generate the updated step using LLM
    prompt = get_step_update_prompt(vm, seq_no, suggestion)
    updated_step_response = llm_interface.generate(prompt)

    if not updated_step_response:
        return log_and_return_error("Failed to generate updated step", "error", 500)

    updated_step = parse_step(updated_step_response)
    if not updated_step:
        return log_and_return_error(f"Failed to parse updated step {updated_step_response}", "error", 500)
    
    print(f"Updated step: {updated_step}")
    print(f"Current plan: {vm.state['current_plan'][vm.state['program_counter']]}")
    print("program_counter", vm.state['program_counter'])

    current_commit =  repo.commit(commit_hash)
    if current_commit.parents:
        previous_commit_hash = current_commit.parents[0].hexsha
    else:
        log_and_return_error("Cannot update the first commit", "error", 400)
    
    # checkout from the previous commit of specified seq_no
    vm.set_state(previous_commit_hash)
    branch_name = f"update_step_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if vm.git_manager.create_branch_from_commit(branch_name, previous_commit_hash) and vm.git_manager.checkout_branch(branch_name):
        vm.state["current_plan"][seq_no] = updated_step
        vm.state["program_counter"] = seq_no
        vm.recalculate_variable_refs()  # Recalculate variable references
        commit_message_wrapper.set_commit_message(
            StepType.STEP_OPTIMIZATION, vm.state["program_counter"], suggestion
        )
        vm.save_state()

        new_commit_hash = commit_vm_changes(vm)
        if new_commit_hash:
            last_commit_hash = new_commit_hash
            app.logger.info(
                f"Resumed execution with updated plan on branch '{branch_name}'. New commit: {new_commit_hash}"
            )
        else:
            log_and_return_error("Failed to commit step optimization", "error", 500)
    else:
        log_and_return_error(f"Failed to create or checkout branch '{branch_name}'", "error", 500)

    print(f"Current plan: {vm.state['current_plan'][vm.state['program_counter']]}")
    print("program_counter", vm.state['program_counter'])

    # Re-execute the plan from the updated step
    while True:
        success = vm.step()
        commit_hash = commit_vm_changes(vm)
        if commit_hash:
            last_commit_hash = commit_hash
        if not success:
            break

        if vm.state.get("goal_completed"):
            logging.info("Goal completed during plan execution.")
            break

    if vm.state.get("goal_completed"):
        final_answer = vm.get_variable("final_answer")
        if final_answer:
            logging.info(f"\nfinal_answer: {final_answer}")
        else:
            logging.info("\nNo result was generated.")
    else:
        logging.warning("Plan execution failed or did not complete.")
        logging.error(vm.state.get("errors"))

    return jsonify(
        {
            "success": True,
            "current_branch": vm.git_manager.get_current_branch(),
            "last_commit_hash": last_commit_hash,
        }
    )


@app.route("/vm_state_details/<commit_hash>")
def vm_state_details(commit_hash):
    repo = get_repo(get_current_repo_path())
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


@app.route("/get_directories")
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


@app.route("/set_repo/<path:repo_name>")
def set_repo(repo_name):
    global git_manager
    if repo_exists(repo_name):
        new_repo_path = os.path.join(GIT_REPO_PATH, repo_name)
        git_manager = GitManager(new_repo_path)
        return jsonify({"success": True, "message": f"Repository set to {repo_name}"})
    else:
        return jsonify({"success": False, "message": "Invalid repository path"}), 400


@app.route("/get_branches")
def get_branches():
    repo = get_repo(get_current_repo_path())
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


@app.route("/set_branch/<branch_name>")
def set_branch(branch_name):
    repo = get_repo(get_current_repo_path())
    try:
        repo.git.checkout(branch_name)
        return jsonify(
            {"success": True, "message": f"Switched to branch {branch_name}"}
        )
    except GitCommandError as e:
        return log_and_return_error(
            f"Error switching to branch {branch_name}: {str(e)}", "error", 400
        )


@app.route("/delete_branch/<branch_name>", methods=["POST"])
def delete_branch(branch_name):
    repo = get_repo(get_current_repo_path())
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
            app.logger.info(
                f"Switched to branch {switch_to} before deleting {branch_name}"
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


def get_current_repo_path():
    global git_manager
    return git_manager.repo_path if git_manager else GIT_REPO_PATH


def repo_exists(repo_name):
    repo_path = os.path.join(GIT_REPO_PATH, repo_name)
    return os.path.exists(repo_path) and os.path.isdir(os.path.join(repo_path, ".git"))


def commit_vm_changes(vm):
    if commit_message_wrapper.get_commit_message():
        commit_hash = vm.git_manager.commit_changes(
            commit_message_wrapper.get_commit_message()
        )
        if commit_hash:
            app.logger.info(f"Committed changes: {commit_hash}")
        else:
            app.logger.warning("Failed to commit changes")
        commit_message_wrapper.clear_commit_message()
        return commit_hash
    return None


def get_llm_response(prompt):
    return llm_interface.generate(prompt)


def run_vm_with_goal(goal, repo_path):
    vm = PlanExecutionVM(repo_path, llm_interface)
    vm.set_goal(goal)

    plan = generate_plan(goal)
    if plan:
        logging.info("Generated Plan:")
        vm.state["current_plan"] = plan

        while True:
            success = vm.step()
            commit_vm_changes(vm)
            if not success:
                break

            if vm.state.get("goal_completed"):
                logging.info("Goal completed during plan execution.")
                break

        if vm.state.get("goal_completed"):
            final_answer = vm.get_variable("final_answer")
            if final_answer:
                logging.info(f"\nfinal_answer: {final_answer}")
            else:
                logging.info("\nNo result was generated.")
        else:
            logging.warning("Plan execution failed or did not complete.")
            logging.error(vm.state.get("errors"))
    else:
        logging.error("Failed to generate plan.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the VM with a specified goal or start the visualization server."
    )
    parser.add_argument("--goal", help="Set a goal for the VM to achieve")
    parser.add_argument(
        "--server", action="store_true", help="Start the visualization server"
    )
    parser.add_argument(
        "--port", type=int, default=5000, help="Port to run the visualization server on"
    )

    args = parser.parse_args()

    if args.goal:
        repo_path = os.path.join(GIT_REPO_PATH, datetime.now().strftime("%Y%m%d%H%M%S"))
        run_vm_with_goal(args.goal, repo_path)
        logging.info("VM execution completed")
    elif args.server:
        logging.info("Starting visualization server...")
        current_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(current_dir)
        app.run(debug=True, port=args.port)
    else:
        logging.info(
            "Please specify --goal to run the VM with a goal or --server to start the visualization server"
        )
