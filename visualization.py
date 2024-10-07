import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
import re
from datetime import datetime
from flask import Flask, render_template, jsonify, request, abort, send_from_directory
from config import GIT_REPO_PATH
from git_manager import GitManager
from utils import load_state, save_state, parse_commit_message, get_commit_message_schema, StepType  # Import StepType
import argparse
from vm import PlanExecutionVM
import logging

try:
    import git
    from git import Repo, NULL_TREE
    from git.exc import GitCommandError
    git_available = True
except ImportError:
    print("GitPython is not installed. Please install it using: pip install GitPython")
    git_available = False

try:
    from vm import PlanExecutionVM as VM  # Aliased PlanExecutionVM to VM
except ImportError:
    abort(500, description="VM module not found. Make sure vm.py is in the same directory and exports a VM class.")

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
for handler in app.logger.handlers:
    handler.setFormatter(formatter)
git_manager = GitManager(GIT_REPO_PATH)

def extract_vm_info(branch_name='main', repo_name=None):
    repo_path = os.path.join(GIT_REPO_PATH, repo_name) if repo_name else GIT_REPO_PATH
    app.logger.info(f"Attempting to access repository at path: {repo_path}")
    
    if not os.path.exists(repo_path):
        app.logger.error(f"Repository path does not exist: {repo_path}")
        return []
    
    try:
        repo = Repo(repo_path)
        app.logger.info(f"Successfully initialized repository at {repo_path}")
    except Exception as e:
        app.logger.error(f"Failed to initialize repository at {repo_path}: {str(e)}", exc_info=True)
        return []
    
    try:
        commits = list(repo.iter_commits(branch_name))
        app.logger.info(f"Successfully retrieved {len(commits)} commits for branch {branch_name}")
    except GitCommandError as e:
        app.logger.error(f"Error fetching commits for branch {branch_name}: {str(e)}", exc_info=True)
        return []
    
    vm_states = []
    
    for commit in commits:
        commit_time = datetime.fromtimestamp(commit.committed_date)
        seq_no, title, details, commit_type = parse_commit_message(commit.message)
        
        try:
            vm_state_content = repo.git.show(f'{commit.hexsha}:vm_state.json')
            vm_state = json.loads(vm_state_content)
        except GitCommandError:
            app.logger.warning(f"vm_state.json not found in commit {commit.hexsha}")
            vm_state = None
        except json.JSONDecodeError:
            app.logger.error(f"Invalid JSON in vm_state.json for commit {commit.hexsha}")
            vm_state = None
        
        vm_states.append({
            'time': commit_time.isoformat(),
            'title': title,
            'details': details,
            'commit_hash': commit.hexsha,
            'seq_no': seq_no,
            'vm_state': vm_state,
            'commit_type': commit_type
        })

    return vm_states

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/vm_data')
def get_vm_data():
    branch = request.args.get('branch', 'main')
    repo = request.args.get('repo')
    
    app.logger.info(f"get_vm_data called with branch: '{branch}', repo: '{repo}'")
        
    try:
        vm_states = extract_vm_info(branch, repo)
        
        if not vm_states:
            app.logger.warning(f"No VM states found for branch: {branch}, repo: {repo}")
            return jsonify([]), 200  # Return an empty array instead of a 404
        
        app.logger.info(f"Successfully retrieved {len(vm_states)} VM states for branch: {branch}, repo: {repo}")
        return jsonify(vm_states)
    except Exception as e:
        app.logger.error(f"Error fetching VM data: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/vm_state/<commit_hash>')
def get_vm_state(commit_hash):
    repo_path = get_current_repo_path()
    repo = git.Repo(repo_path)
    try:
        commit = repo.commit(commit_hash)
        vm_state_content = repo.git.show(f'{commit.hexsha}:vm_state.json')
        vm_state = json.loads(vm_state_content)
        return jsonify(vm_state)
    except GitCommandError as e:
        app.logger.warning(f"Error fetching vm_state.json for commit {commit_hash}: {str(e)}")
        return jsonify({'error': 'VM state not found for this commit'}), 404
    except json.JSONDecodeError as e:
        app.logger.error(f"Invalid JSON in vm_state.json for commit {commit_hash}: {str(e)}")
        return jsonify({'error': 'Invalid VM state data'}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error fetching VM state for commit {commit_hash}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/code_diff/<commit_hash>')
def code_diff(commit_hash):
    repo_path = get_current_repo_path()
    repo = git.Repo(repo_path)
    try:
        commit = repo.commit(commit_hash)
        if commit.parents:
            # If the commit has a parent, diff against the parent
            parent = commit.parents[0]
            diff = repo.git.diff(parent, commit, '--unified=3')
        else:
            # If it's the initial commit, show the full content of the commit
            diff = repo.git.show(commit, '--pretty=format:', '--no-commit-id', '-p')
        return jsonify({'diff': diff})
    except Exception as e:
        app.logger.error(f"Error generating diff for commit {commit_hash}: {str(e)}")
        abort(404, description=str(e))

@app.route('/commit_details/<commit_hash>')
def commit_details(commit_hash):
    repo_path = get_current_repo_path()
    repo = git.Repo(repo_path)
    try:
        commit = repo.commit(commit_hash)
        
        if commit.parents:
            app.logger.info(f"Commit {commit_hash} has parents. Diffing against parent commit.")
            diff = commit.diff(commit.parents[0])
        else:
            app.logger.info(f"Commit {commit_hash} has no parents. Diffing against NULL_TREE.")
            diff = commit.diff(NULL_TREE)
        
        seq_no, _, _, _ = parse_commit_message(commit.message)  # Ensure this is correct
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
        app.logger.error(f"Error fetching commit details for {commit_hash}: {str(e)}")
        return jsonify({'error': str(e)}), 404

@app.route('/update_plan', methods=['POST'])
def update_plan():
    data = request.json
    repo_name = data.get('repo')
    commit_hash = data.get('commit_hash')
    updated_plan = data.get('updated_plan')
    seq_no = data.get('seq_no')
    
    if not all([repo_name, commit_hash, updated_plan, seq_no]):
        return jsonify({'error': 'Missing required parameters'}), 400

    repo_path = get_current_repo_path()
    
    try:
        # Initialize repo
        repo = git.Repo(repo_path)

        # Create a new branch
        new_branch_name = f"plan_update_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        new_branch = repo.create_head(new_branch_name, commit_hash)
        repo.head.reference = new_branch
        repo.head.reset(index=True, working_tree=True)

        # Load the current vm_state.json
        vm_state_path = os.path.join(repo_path, 'vm_state.json')
        with open(vm_state_path, 'r') as f:
            vm_state = json.load(f)

        # Update the plan
        vm_state['current_plan'] = updated_plan

        save_state(vm_state, repo_path)

        # Commit the changes
        repo.index.add([vm_state_path])
        desc = "Updated plan to execute from seq_no: {}".format(seq_no)
        commit_message = get_commit_message_schema(
            step_type=StepType.PLAN_UPDATE.value,  # Use StepType enum
            seq_no=str(seq_no),
            description=desc,
            input_parameters={},  # Add any relevant input parameters if needed
            output_variables={}   # Add any relevant output variables if needed
        )
        new_commit = repo.index.commit(commit_message)

        return jsonify({
            'success': True,
            'message': desc,
            'new_commit_hash': new_commit.hexsha,
            'new_branch': new_branch_name
        })
    except Exception as e:
        app.logger.error(f"Error updating plan: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/execute_vm', methods=['POST'])
def execute_vm():
    try:
        data = request.json
        app.logger.info(f"Received execute_vm request with data: {data}")

        commit_hash = data.get('commit_hash')
        steps = int(data.get('steps', 1))
        repo_name = data.get('repo')
        new_branch = data.get('new_branch')
        seq_no = data.get('seq_no')

        if not all([commit_hash, steps, repo_name, seq_no]):
            return jsonify({'error': 'Missing required parameters'}), 400

        repo_path = get_current_repo_path()
        
        try:
            vm = PlanExecutionVM(repo_path)
        except ImportError as e:
            return jsonify({'error': str(e)}), 500

        vm.load_state(commit_hash)
        
        # Get the repo instance
        repo = git.Repo(repo_path)

        # Use the new_branch if provided, otherwise use the current active branch
        if new_branch:
            app.logger.info(f"Switching to new branch: {new_branch}")
            repo.git.checkout(new_branch)
        current_branch = repo.active_branch.name
        app.logger.info(f"Using branch: {current_branch}")

        # Find the index of the step with the given seq_no
        app.logger.info(f"current plan: {vm.state['current_plan']}")
        start_index = next((i for i, step in enumerate(vm.state['current_plan']) if str(step.get('seq_no')) == str(seq_no)), None)
        if start_index is None:
            return jsonify({'error': f'Step with seq_no {seq_no} not found in the plan. Available seq_no values: {[step.get("seq_no") for step in vm.state["current_plan"]]}'}), 400

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
    except Exception as e:
        app.logger.error(f"Error in execute_vm: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/vm_state_details/<commit_hash>')
def vm_state_details(commit_hash):
    repo_path = get_current_repo_path()
    repo = git.Repo(repo_path)
    try:
        commit = repo.commit(commit_hash)
        try:
            vm_state_content = repo.git.show(f'{commit.hexsha}:vm_state.json')
            vm_state = json.loads(vm_state_content)
            
            variables = vm_state.get('variables', {})
            parameters = vm_state.get('parameters', {})
            
            return jsonify({'variables': variables, 'parameters': parameters})
        except git.exc.GitCommandError:
            app.logger.warning(f"vm_state.json not found for commit: {commit_hash}")
            return jsonify({'error': 'vm_state.json not found for this commit'}), 404
        except json.JSONDecodeError:
            app.logger.error(f"Invalid JSON in vm_state.json for commit: {commit_hash}")
            return jsonify({'error': 'Invalid vm_state.json content'}), 500
    except git.exc.BadName:
        app.logger.error(f"Invalid commit hash: {commit_hash}")
        return jsonify({'error': 'Invalid commit hash'}), 404
    except Exception as e:
        app.logger.error(f"Unexpected error: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

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
    repo_path = get_current_repo_path()
    try:
        repo = Repo(repo_path)
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
        return jsonify({'error': str(e)}), 500

@app.route('/set_branch/<branch_name>')
def set_branch(branch_name):
    repo_path = get_current_repo_path()
    try:
        repo = Repo(repo_path)
        repo.git.checkout(branch_name)
        return jsonify({'success': True, 'message': f'Switched to branch {branch_name}'})
    except GitCommandError as e:
        return jsonify({'error': str(e)}), 400

@app.route('/delete_branch/<branch_name>', methods=['POST'])
def delete_branch(branch_name):
    repo_path = get_current_repo_path()
    try:
        repo = Repo(repo_path)
        if branch_name == repo.active_branch.name:
            # If trying to delete the active branch, switch to 'main' or another available branch first
            available_branches = [b.name for b in repo.branches if b.name != branch_name]
            if not available_branches:
                return jsonify({'error': 'Cannot delete the only branch in the repository'}), 400
            
            switch_to = 'main' if 'main' in available_branches else available_branches[0]
            repo.git.checkout(switch_to)
            app.logger.info(f"Switched to branch {switch_to} before deleting {branch_name}")
        
        repo.git.branch('-D', branch_name)
        return jsonify({'success': True, 'message': f'Branch {branch_name} deleted successfully', 'new_active_branch': repo.active_branch.name})
    except GitCommandError as e:
        return jsonify({'error': str(e)}), 400

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
            print(f"Committed changes: {commit_hash}")
        else:
            print("Failed to commit changes")
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
            # Use the program_counter as a fallback for seq_no
            current_step = vm.state['current_plan'][vm.state['program_counter'] - 1]
            seq_no = current_step.get('seq_no', str(vm.state['program_counter']))
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
        # Ensure we're using the correct path for the current file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(current_dir)
        app.run(debug=True)
    else:
        print("Please specify --goal to run the VM with a goal or --server to start the visualization server")