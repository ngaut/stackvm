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
    print("GitPython is not installed. Please install it using: pip install GitPython")

try:
    from flask import Flask, render_template, jsonify, request, current_app
except ImportError:
    print("Flask is not installed. Please install it using: pip install Flask")

from config import GIT_REPO_PATH
from git_manager import GitManager
from utils import load_state, save_state, parse_commit_message, get_commit_message_schema, StepType
from vm import PlanExecutionVM

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Initialize Flask app
app = Flask(__name__)

# Configure logging
def setup_logging():
    app.logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
    for handler in app.logger.handlers:
        handler.setFormatter(formatter)

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
        app.logger.info(f"Successfully retrieved {len(commits)} commits for branch {branch_name}")
        return commits
    except GitCommandError as e:
        app.logger.error(f"Error fetching commits for branch {branch_name}: {str(e)}", exc_info=True)
        return []

def get_vm_state_for_commit(repo, commit):
    try:
        vm_state_content = repo.git.show(f'{commit.hexsha}:vm_state.json')
        return json.loads(vm_state_content)
    except GitCommandError:
        app.logger.warning(f"vm_state.json not found in commit {commit.hexsha}")
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
    
    app.logger.info(f"get_vm_data called with branch: '{branch}', repo: '{repo_name}'")
    
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
            app.logger.info(f"Commit {commit_hash} has parents. Diffing against parent commit.")
            diff = commit.diff(commit.parents[0])
        else:
            app.logger.info(f"Commit {commit_hash} has no parents. Diffing against NULL_TREE.")
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
        app.logger.info(f"Commit details for {commit_hash}: {details}")
        return jsonify(details)
    except Exception as e:
        return log_and_return_error(f"Error fetching commit details for {commit_hash}: {str(e)}", 'error', 404)

@app.route('/update_plan', methods=['POST'])
def update_plan():
    data = request.json
    repo_name = data.get('repo')
    commit_hash = data.get('commit_hash')
    updated_plan = data.get('updated_plan')
    seq_no = data.get('seq_no')
    
    if not all([repo_name, commit_hash, updated_plan, seq_no]):
        return log_and_return_error('Missing required parameters', 'error', 400)

    repo = get_repo(get_current_repo_path())
    
    try:
        new_branch_name = f"plan_update_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        new_branch = repo.create_head(new_branch_name, commit_hash)
        repo.head.reference = new_branch
        repo.head.reset(index=True, working_tree=True)

        vm_state_path = os.path.join(repo.working_dir, 'vm_state.json')
        with open(vm_state_path, 'r') as f:
            vm_state = json.load(f)

        vm_state['current_plan'] = updated_plan
        save_state(vm_state, repo.working_dir)

        repo.index.add([vm_state_path])
        desc = f"Updated plan to execute from seq_no: {seq_no}"
        commit_message = get_commit_message_schema(
            step_type=StepType.PLAN_UPDATE.value,
            seq_no=str(seq_no),
            description=desc,
            input_parameters={},
            output_variables={}
        )
        new_commit = repo.index.commit(commit_message)

        return jsonify({
            'success': True,
            'message': desc,
            'new_commit_hash': new_commit.hexsha,
            'new_branch': new_branch_name
        })
    except Exception as e:
        return log_and_return_error(f"Error updating plan: {str(e)}", 'error', 500)

@app.route('/execute_vm', methods=['POST'])
def execute_vm():
    data = request.json
    app.logger.info(f"Received execute_vm request with data: {data}")

    commit_hash = data.get('commit_hash')
    steps = int(data.get('steps', 1))
    repo_name = data.get('repo')
    new_branch = data.get('new_branch')
    seq_no = data.get('seq_no')

    if not all([commit_hash, steps, repo_name, seq_no]):
        return log_and_return_error('Missing required parameters', 'error', 400)

    repo_path = get_current_repo_path()
    
    try:
        vm = PlanExecutionVM(repo_path)
    except ImportError as e:
        return log_and_return_error(str(e), 'error', 500)

    vm.load_state(commit_hash)
    
    repo = git.Repo(repo_path)

    if new_branch:
        app.logger.info(f"Switching to new branch: {new_branch}")
        repo.git.checkout(new_branch)
    current_branch = repo.active_branch.name
    app.logger.info(f"Using branch: {current_branch}")

    app.logger.info(f"current plan: {vm.state['current_plan']}")
    start_index = next((i for i, step in enumerate(vm.state['current_plan']) if str(step.get('seq_no')) == str(seq_no)), None)
    if start_index is None:
        return log_and_return_error(f'Step with seq_no {seq_no} not found in the plan. Available seq_no values: {[step.get("seq_no") for step in vm.state["current_plan"]]}', 'error', 400)

    plan_length = len(vm.state['current_plan'])
    steps_to_execute = min(steps, plan_length - start_index)
    
    vm.state['program_counter'] = start_index + 1

    app.logger.info(f"Executing {steps_to_execute} steps from [seq_no: {seq_no}]")
    steps_executed = 0
    last_commit_hash = None
    for _ in range(steps_to_execute):
        success = vm.step()
        if success:
            steps_executed += 1
            commit_hash = commit_vm_changes(vm)
            if commit_hash:
                last_commit_hash = commit_hash
        else:
            app.logger.info("Reached end of current plan or encountered an error")
            break

    return jsonify({
        'success': True,
        'steps_executed': steps_executed,
        'current_branch': current_branch,
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
    if vm.commit_message:
        commit_hash = vm.git_manager.commit_changes(vm.commit_message)
        if commit_hash:
            app.logger.info(f"Committed changes: {commit_hash}")
        else:
            app.logger.warning("Failed to commit changes")
        vm.commit_message = None  # Reset commit message
        return commit_hash
    return None

def run_vm_with_goal(goal, repo_path):
    vm = PlanExecutionVM(repo_path)
    vm.set_goal(goal)
    
    if vm.generate_plan():
        print("Generated Plan:")
        print(json.dumps(vm.state['current_plan'], indent=2))
        
        while True:
            success = vm.step()
            if not success:
                break
            
            # Commit changes after each successful step
            commit_vm_changes(vm)
            
            if vm.state['goal_completed']:
                print("Goal completed during plan execution.")
                break

        if vm.state['goal_completed']:
            result = vm.get_variable('result')
            if result:
                print(f"\nFinal Result: {result}")
            else:
                print("\nNo result was generated.")
        else:
            print("Plan execution failed or did not complete.")
            if vm.state['errors']:
                print("Errors encountered:")
                for error in vm.state['errors']:
                    print(f"- {error}")
    else:
        print("Failed to generate plan.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the VM with a specified goal or start the visualization server.")
    parser.add_argument("--goal", help="Set a goal for the VM to achieve")
    parser.add_argument("--server", action="store_true", help="Start the visualization server")
    args = parser.parse_args()

    if args.goal:
        repo_path = os.path.join(GIT_REPO_PATH, datetime.now().strftime("%Y%m%d%H%M%S"))
        run_vm_with_goal(args.goal, repo_path)
        print("VM execution completed")    
    elif args.server:
        print("Starting visualization server...")
        current_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(current_dir)
        app.run(debug=True)
    else:
        print("Please specify --goal to run the VM with a goal or --server to start the visualization server")