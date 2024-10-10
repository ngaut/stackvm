import sys
import os
import json
import logging
import argparse
from datetime import datetime

try:
    import git
    from git import Repo, NULL_TREE
    from git.exc import GitCommandError
except ImportError:
    logging.error("GitPython is not installed. Please install it using: pip install GitPython")

try:
    from flask import Flask, render_template, jsonify, request, current_app
except ImportError:
    logging.error("Flask is not installed. Please install it using: pip install Flask")

from config import GIT_REPO_PATH, VM_SPEC_CONTENT
from git_manager import GitManager
from utils import load_state, save_state, parse_commit_message, get_commit_message_schema, StepType,find_first_json_array, find_first_json_object, parse_plan
from vm import PlanExecutionVM

# Add these imports at the top of the file
from llm_interface import LLMInterface
from config import LLM_MODEL

# Add this import at the top of the file
from prompts import get_plan_update_prompt, get_should_update_plan_prompt, get_generate_plan_prompt

# Add this import at the top of the file
from commit_message_wrapper import commit_message_wrapper

# Add this near the top of the file, after other global variables
llm_interface = LLMInterface(LLM_MODEL)

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Initialize Flask app
app = Flask(__name__)

# Configure logging
def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
    app.logger.setLevel(logging.INFO)
    for handler in app.logger.handlers:
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'))

setup_logging()

# Initialize GitManager
git_manager = GitManager(GIT_REPO_PATH)

def get_repo(repo_path):
    try:
        return Repo(repo_path)
    except Exception as e:
        app.logger.error(f"Failed to initialize repository at {repo_path}: {str(e)}", exc_info=True)
        return None

def get_commits(repo, branch_name):
    try:
        commits = list(repo.iter_commits(branch_name))
        return commits
    except GitCommandError as e:
        app.logger.error(f"Error fetching commits for branch {branch_name}: {str(e)}", exc_info=True)
        return []

def get_vm_state_for_commit(repo, commit):
    try:
        vm_state_content = repo.git.show(f'{commit.hexsha}:vm_state.json')
        return json.loads(vm_state_content)
    except GitCommandError:
        app.logger.error(f"vm_state.json not found in commit {commit.hexsha}")
    except json.JSONDecodeError:
        app.logger.error(f"Invalid JSON in vm_state.json for commit {commit.hexsha}")
    return None

def log_and_return_error(message, error_type, status_code):
    if error_type == 'warning':
        current_app.logger.warning(message)
    elif error_type == 'error':
        current_app.logger.error(message)
    else:
        current_app.logger.info(message)
    return jsonify({'error': message}), status_code

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/vm_data')
def get_vm_data():
    branch = request.args.get('branch', 'main')
    repo_name = request.args.get('repo')
    
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
        
        vm_states.append({
            'time': commit_time.isoformat(),
            'title': title,
            'details': details,
            'commit_hash': commit.hexsha,
            'seq_no': seq_no,
            'vm_state': vm_state,
            'commit_type': commit_type
        })

    return jsonify(vm_states)

@app.route('/vm_state/<commit_hash>')
def get_vm_state(commit_hash):
    repo = get_repo(get_current_repo_path())
    try:
        commit = repo.commit(commit_hash)
        vm_state = get_vm_state_for_commit(repo, commit)
        if vm_state is None:
            return log_and_return_error(f"VM state not found for commit {commit_hash}", 'warning', 404)
        return jsonify(vm_state)
    except Exception as e:
        return log_and_return_error(f"Unexpected error fetching VM state for commit {commit_hash}: {str(e)}", 'error', 500)

@app.route('/code_diff/<commit_hash>')
def code_diff(commit_hash):
    repo = get_repo(get_current_repo_path())
    try:
        commit = repo.commit(commit_hash)
        if commit.parents:
            parent = commit.parents[0]
            diff = repo.git.diff(parent, commit, '--unified=3')
        else:
            diff = repo.git.show(commit, '--pretty=format:', '--no-commit-id', '-p')
        return jsonify({'diff': diff})
    except Exception as e:
        return log_and_return_error(f"Error generating diff for commit {commit_hash}: {str(e)}", 'error', 404)

@app.route('/commit_details/<commit_hash>')
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
            'hash': commit.hexsha,
            'author': commit.author.name,
            'date': commit.committed_datetime.isoformat(),
            'message': commit.message,
            'seq_no': seq_no,
            'files_changed': [item.a_path for item in diff]
        }
        return jsonify(details)
    except Exception as e:
        return log_and_return_error(f"Error fetching commit details for {commit_hash}: {str(e)}", 'error', 404)

def generate_plan(goal, custom_prompt=None):
    if not goal:
        app.logger.error("No goal is set.")
        return []

    
    if custom_prompt:
        prompt = custom_prompt
    else:
        prompt = get_generate_plan_prompt(goal, VM_SPEC_CONTENT)

    plan_response = llm_interface.generate(prompt)

    app.logger.info(f"Generating plan using LLM: {plan_response}")

    if not plan_response:
        app.logger.error(f"LLM failed to generate a response: {plan_response}")
        return []
    
    plan = parse_plan(plan_response)
    
    if plan:
        return plan
    else:
        app.logger.error("Failed to parse the generated plan.")
        return []

# Update the generate_updated_plan function to use the new generate_plan function
def generate_updated_plan(vm: PlanExecutionVM, explanation: str, key_factors: list):    
    prompt = get_plan_update_prompt(vm.state, VM_SPEC_CONTENT, explanation, key_factors)
    new_plan = generate_plan(vm.state['goal'], custom_prompt=prompt)
    app.logger.info(f"Generated updated plan: {new_plan}, previous plan: {vm.state['current_plan']}")
    return new_plan

def should_update_plan(vm: PlanExecutionVM):
    if vm.state.get('errors'):
        app.logger.info("Plan update triggered due to errors.")
        return True, "Errors detected in VM state", [{"factor": "VM errors", "impact": "Critical"}]
    
    # Use LLM to judge if we should update the plan
    prompt = get_should_update_plan_prompt(vm.state)
    response = llm_interface.generate(prompt)
    
    # Use the new find_first_json_object function to find the first JSON object in the response
    json_response = find_first_json_object(response)
    if json_response:
        analysis = json.loads(json_response)
    else:
        app.logger.error("No valid JSON object found in the response.")
        return log_and_return_error("No valid JSON object found.", 'error', 400)
    
    should_update = analysis.get('should_update', False)
    explanation = analysis.get('explanation', '')
    key_factors = analysis.get('key_factors', [])
    
    if should_update:
        app.logger.info(f"LLM suggests updating the plan: {explanation}")
        for factor in key_factors:
            app.logger.info(f"Factor: {factor['factor']}, Impact: {factor['impact']}")
        return True, explanation, key_factors
    else:
        app.logger.info(f"LLM suggests keeping the current plan: {explanation}")
        return False, explanation, key_factors

@app.route('/execute_vm', methods=['POST'])
def execute_vm():
    data = request.json
    app.logger.info(f"Received execute_vm request with data: {data}")

    commit_hash = data.get('commit_hash')
    steps = int(data.get('steps', 20)) # maximum number of steps to execute
    repo_name = data.get('repo')
    new_branch = data.get('new_branch')
    seq_no = data.get('seq_no')

    if not all([commit_hash, steps, repo_name]):
        return log_and_return_error('Missing required parameters', 'error', 400)

    repo_path = get_current_repo_path()
    
    try:
        vm = PlanExecutionVM(repo_path, llm_interface)
    except ImportError as e:
        return log_and_return_error(str(e), 'error', 500)

    vm.set_state(commit_hash)
    repo = git.Repo(repo_path)

    if new_branch:
        app.logger.info(f"Switching to new branch: {new_branch}")
        repo.git.checkout(new_branch)
    current_branch = repo.active_branch.name
    app.logger.info(f"Using branch: {current_branch}")

    """
    # Set program_counter based on seq_no if provided
    # It had been handled by vm.set_state(commit_hash) above
    if seq_no is not None:
        start_index = next((i for i, step in enumerate(vm.state['current_plan']) if str(step.get('seq_no')) == str(seq_no)), None)
        if start_index is None:
            return log_and_return_error(f'Step with seq_no {seq_no} not found in the plan.', 'error', 400)
        vm.state['program_counter'] = start_index
    else:
        # Ensure program_counter is initialized
        if 'program_counter' not in vm.state:
            vm.state['program_counter'] = 0
    """

    steps_executed = 0
    last_commit_hash = commit_hash

    for _ in range(steps):
        try:
            success = vm.step()
        except Exception as e:
            error_msg = f"Error during VM step execution: {str(e)}"
            app.logger.error(error_msg, exc_info=True)
            return log_and_return_error(error_msg, 'error', 500)

        commit_hash = commit_vm_changes(vm)
        if commit_hash:
            last_commit_hash = commit_hash

        # Check if plan needs to be updated
        should_update, explanation, key_factors = should_update_plan(vm)
        if should_update:
            updated_plan = generate_updated_plan(vm, explanation, key_factors)

            # Create a new branch for the updated plan
            branch_name = f"plan_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if vm.git_manager.create_branch(branch_name) and vm.git_manager.checkout_branch(branch_name):
                # Update the VM state with the new plan
                vm.state['current_plan'] = updated_plan
                commit_message_wrapper.set_commit_message(StepType.PLAN_UPDATE, vm.state['program_counter'], explanation)
                save_state(vm.state, repo_path)
                
                new_commit_hash = commit_vm_changes(vm)
                if new_commit_hash:
                    last_commit_hash = new_commit_hash
                    app.logger.info(f"Resumed execution with updated plan on branch '{branch_name}'. New commit: {new_commit_hash}")
                else:
                    app.logger.error("Failed to commit updated plan")
                    break
            else:
                app.logger.error(f"Failed to create or checkout branch '{branch_name}'")
                break

        steps_executed += 1

        if vm.state.get('goal_completed'):
            app.logger.info("Goal completed. Stopping execution.")
            break

    return jsonify({
        'success': True,
        'steps_executed': steps_executed,
        'current_branch': vm.git_manager.get_current_branch(),
        'last_commit_hash': last_commit_hash
    })

@app.route('/vm_state_details/<commit_hash>')
def vm_state_details(commit_hash):
    repo = get_repo(get_current_repo_path())
    try:
        commit = repo.commit(commit_hash)
        vm_state = get_vm_state_for_commit(repo, commit)
        
        if vm_state is None:
            return log_and_return_error(f"vm_state.json not found for commit: {commit_hash}", 'warning', 404)
        
        variables = vm_state.get('variables', {})
        parameters = vm_state.get('parameters', {})
        
        return jsonify({'variables': variables, 'parameters': parameters})
    except git.exc.BadName:
        return log_and_return_error(f"Invalid commit hash: {commit_hash}", 'error', 404)
    except Exception as e:
        return log_and_return_error(f"Unexpected error: {str(e)}", 'error', 500)

@app.route('/get_directories')
def get_directories():
    try:
        directories = [d for d in os.listdir(GIT_REPO_PATH) if os.path.isdir(os.path.join(GIT_REPO_PATH, d))]
        return jsonify(directories)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/set_repo/<path:repo_name>')
def set_repo(repo_name):
    global git_manager
    if repo_exists(repo_name):
        new_repo_path = os.path.join(GIT_REPO_PATH, repo_name)
        git_manager = GitManager(new_repo_path)
        return jsonify({'success': True, 'message': f'Repository set to {repo_name}'})
    else:
        return jsonify({'success': False, 'message': 'Invalid repository path'}), 400

@app.route('/get_branches')
def get_branches():
    repo = get_repo(get_current_repo_path())
    try:
        branches = repo.branches
        branch_data = [
            {
                'name': branch.name,
                'last_commit_date': branch.commit.committed_datetime.isoformat(),
                'last_commit_message': branch.commit.message.split('\n')[0],
                'is_active': branch.name == repo.active_branch.name
            }
            for branch in branches
        ]
        branch_data.sort(key=lambda x: (-x['is_active'], x['last_commit_date']), reverse=True)
        return jsonify(branch_data)
    except GitCommandError as e:
        return log_and_return_error(f"Error fetching branches: {str(e)}", 'error', 500)

@app.route('/set_branch/<branch_name>')
def set_branch(branch_name):
    repo = get_repo(get_current_repo_path())
    try:
        repo.git.checkout(branch_name)
        return jsonify({'success': True, 'message': f'Switched to branch {branch_name}'})
    except GitCommandError as e:
        return log_and_return_error(f"Error switching to branch {branch_name}: {str(e)}", 'error', 400)

@app.route('/delete_branch/<branch_name>', methods=['POST'])
def delete_branch(branch_name):
    repo = get_repo(get_current_repo_path())
    try:
        if branch_name == repo.active_branch.name:
            available_branches = [b.name for b in repo.branches if b.name != branch_name]
            if not available_branches:
                return log_and_return_error('Cannot delete the only branch in the repository', 'error', 400)
            
            switch_to = 'main' if 'main' in available_branches else available_branches[0]
            repo.git.checkout(switch_to)
            app.logger.info(f"Switched to branch {switch_to} before deleting {branch_name}")
        
        repo.git.branch('-D', branch_name)
        return jsonify({'success': True, 'message': f'Branch {branch_name} deleted successfully', 'new_active_branch': repo.active_branch.name})
    except GitCommandError as e:
        return log_and_return_error(f"Error deleting branch {branch_name}: {str(e)}", 'error', 400)

def get_current_repo_path():
    global git_manager
    return git_manager.repo_path if git_manager else GIT_REPO_PATH

def repo_exists(repo_name):
    repo_path = os.path.join(GIT_REPO_PATH, repo_name)
    return os.path.exists(repo_path) and os.path.isdir(os.path.join(repo_path, '.git'))

def commit_vm_changes(vm):
    if commit_message_wrapper.get_commit_message():
        commit_hash = vm.git_manager.commit_changes(commit_message_wrapper.get_commit_message())
        if commit_hash:
            app.logger.info(f"Committed changes: {commit_hash}")
        else:
            app.logger.warning("Failed to commit changes")
        commit_message_wrapper.clear_commit_message()  # Reset commit message
        return commit_hash
    return None

# Add a new function to get LLM response
def get_llm_response(prompt):
    return llm_interface.generate(prompt)

# Update the run_vm_with_goal function
def run_vm_with_goal(goal, repo_path):
    vm = PlanExecutionVM(repo_path, llm_interface) 
    vm.set_goal(goal)
    
    plan = generate_plan(goal)
    if plan:
        logging.info("Generated Plan:")
        vm.state['current_plan'] = plan
        
        while True:
            success = vm.step()
            if not success:
                break
            
            # Commit changes after each successful step
            commit_vm_changes(vm)
            
            if vm.state.get('goal_completed'):
                logging.info("Goal completed during plan execution.")
                break

        if vm.state.get('goal_completed'):
            result = vm.get_variable('result')
            if result:
                logging.info(f"\nFinal Result: {result}")
            else:
                logging.info("\nNo result was generated.")
        else:
            logging.warning("Plan execution failed or did not complete.")
            logging.error(vm.state.get('errors'))
    else:
        logging.error("Failed to generate plan.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the VM with a specified goal or start the visualization server.")
    parser.add_argument("--goal", help="Set a goal for the VM to achieve")
    parser.add_argument("--server", action="store_true", help="Start the visualization server")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the visualization server on")  # Add this line

    args = parser.parse_args()

    if args.goal:
        repo_path = os.path.join(GIT_REPO_PATH, datetime.now().strftime("%Y%m%d%H%M%S"))
        run_vm_with_goal(args.goal, repo_path)
        logging.info("VM execution completed")    
    elif args.server:
        logging.info("Starting visualization server...")
        current_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(current_dir)
        app.run(debug=True, port=args.port)  # Update this line to use args.port
    else:
        logging.info("Please specify --goal to run the VM with a goal or --server to start the visualization server")