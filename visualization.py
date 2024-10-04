import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
import re
from datetime import datetime
from flask import Flask, render_template, jsonify, request, abort, send_from_directory
from config import GIT_REPO_PATH
from git_manager import GitManager

# Conditional imports to handle potential missing packages
try:
    import git
except ImportError:
    print("GitPython is not installed. Please install it using: pip install GitPython")
    git = None

try:
    from vm import PlanExecutionVM as VM  # Aliased PlanExecutionVM to VM
    vm_available = True
except ImportError:
    print("VM module not found. Make sure vm.py is in the same directory and exports a VM class.")
    vm_available = False

# Add these imports if not already present
from git import Repo, NULL_TREE  # Added NULL_TREE to handle initial commits
from git.exc import GitCommandError

app = Flask(__name__)
git_manager = GitManager(GIT_REPO_PATH)

def parse_commit_message(message):
    lines = message.strip().split('\n')
    title = lines[0]
    details = {}

    # Parse additional details
    for line in lines[1:]:
        if ':' in line:
            key, value = line.split(':', 1)
            details[key.strip()] = value.strip()
        else:
            details.setdefault('description', '')
            details['description'] += line.strip() + '\n'

    # Return without step_info
    return title, details  # Changed return statement to exclude step_info

def extract_vm_info(branch_name='main', repo_name=None):
    repo_path = os.path.join(GIT_REPO_PATH, repo_name) if repo_name else GIT_REPO_PATH
    repo = Repo(repo_path)
    try:
        commits = list(repo.iter_commits(branch_name))
    except GitCommandError as e:
        app.logger.error(f"Error fetching commits: {str(e)}")
        return []
    
    vm_states = []
    
    for commit in commits:
        commit_time = datetime.fromtimestamp(commit.committed_date)
        title, details = parse_commit_message(commit.message)
        
        try:
            vm_state_content = repo.git.show(f'{commit.hexsha}:vm_state.json')
            vm_state = json.loads(vm_state_content)
        except GitCommandError:
            vm_state = None
        
        vm_states.append({
            'time': commit_time.isoformat(),
            'title': title,
            'details': details,
            'commit_hash': commit.hexsha,
            'vm_state': vm_state
        })

    return vm_states

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/vm_data')
def get_vm_data():
    if not vm_available:
        return jsonify({'error': 'VM module not available'}), 500
    
    branch = request.args.get('branch', 'main')
    repo = request.args.get('repo')
    vm_states = extract_vm_info(branch, repo)
    
    return jsonify(vm_states)

@app.route('/vm_state/<commit_hash>')
def get_vm_state(commit_hash):
    if not vm_available:
        return jsonify({'error': 'VM module not available'}), 500

    repo_name = request.args.get('repo')
    repo_path = get_repo_path(repo_name)
    repo = git.Repo(repo_path)
    try:
        commit = repo.commit(commit_hash)
        vm_state_content = repo.git.show(f'{commit.hexsha}:vm_state.json')
        vm_state = json.loads(vm_state_content)
        return jsonify(vm_state)
    except Exception as e:
        abort(404, description=str(e))

@app.route('/code_diff/<commit_hash>')
def code_diff(commit_hash):
    repo_name = request.args.get('repo')
    repo_path = get_repo_path(repo_name)
    repo = git.Repo(repo_path)
    try:
        commit = repo.commit(commit_hash)
        parent = commit.parents[0] if commit.parents else None
        diff = repo.git.diff(parent, commit, '--unified=3')
        return jsonify({'diff': diff})
    except Exception as e:
        abort(404, description=str(e))

@app.route('/commit_details/<commit_hash>')
def commit_details(commit_hash):
    repo_name = request.args.get('repo')
    repo_path = get_repo_path(repo_name)
    repo = git.Repo(repo_path)
    try:
        commit = repo.commit(commit_hash)
        
        if commit.parents:
            app.logger.info(f"Commit {commit_hash} has parents. Diffing against parent commit.")
            diff = commit.diff(commit.parents[0])
        else:
            app.logger.info(f"Commit {commit_hash} has no parents. Diffing against NULL_TREE.")
            diff = commit.diff(NULL_TREE)
        
        details = {
            'hash': commit.hexsha,
            'author': commit.author.name,
            'date': commit.committed_datetime.isoformat(),
            'message': commit.message,
            'files_changed': [item.a_path for item in diff]
        }
        app.logger.info(f"Commit details for {commit_hash}: {details}")
        return jsonify(details)
    except Exception as e:
        app.logger.error(f"Error fetching commit details for {commit_hash}: {str(e)}")
        return jsonify({'error': str(e)}), 404

@app.route('/execute_vm', methods=['POST'])
def execute_vm():
    try:
        data = request.json
        app.logger.info(f"Received execute_vm request with data: {data}")

        if not vm_available:
            return jsonify({'error': 'VM module not available'}), 500

        commit_hash = data.get('commit_hash')
        steps = int(data.get('steps', 1))
        start_from = int(data.get('start_from', 0))
        repo_name = data.get('repo')

        if not all([commit_hash, steps, repo_name]):
            return jsonify({'error': 'Missing required parameters'}), 400

        repo_path = get_repo_path(repo_name)
        repo = git.Repo(repo_path)

        new_branch_name = f"derived_branch_execution_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        current_branch = repo.active_branch.name
        repo.git.checkout(commit_hash, b=new_branch_name)
        app.logger.info(f"Created new branch: {new_branch_name}")

        vm = VM(repo_path)
        vm.load_state(commit_hash)
        
        plan_length = len(vm.state['current_plan'])
        
        if start_from >= plan_length:
            app.logger.info(f"Start index {start_from} is beyond the current plan length {plan_length}")
            return jsonify({
                'error': 'Start index is beyond the current plan length',
                'start_from': start_from,
                'plan_length': plan_length
            }), 400
        
        # Adjust steps if it would exceed the plan length
        steps_to_execute = min(steps, plan_length - start_from)
        
        vm.state['program_counter'] = start_from

        app.logger.info(f"Executing {steps_to_execute} steps from index {start_from}")
        steps_executed = 0
        for _ in range(steps_to_execute):
            if vm.step():
                steps_executed += 1
            else:
                app.logger.info("Reached end of current plan")
                break

        new_state = vm.get_current_state()
        app.logger.info(f"Execution completed, executed {steps_executed} steps. New state: {new_state}")

        new_state_json = json.dumps(new_state, indent=2)
        with open(os.path.join(repo_path, 'vm_state.json'), 'w') as f:
            f.write(new_state_json)
        repo.index.add(['vm_state.json'])
        repo.index.commit(f"Updated VM state after executing {steps_executed} steps from index {start_from}")

        return jsonify({
            'new_state': new_state, 
            'new_branch': new_branch_name, 
            'steps_executed': steps_executed,
            'plan_length': plan_length
        })
    except Exception as e:
        app.logger.error(f"Error in execute_vm: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/vm_state_details/<commit_hash>')
def vm_state_details(commit_hash):
    repo_name = request.args.get('repo')
    repo_path = get_repo_path(repo_name)
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
    new_repo_path = os.path.join(GIT_REPO_PATH, repo_name)
    if os.path.isdir(new_repo_path):
        git_manager = GitManager(new_repo_path)
        return jsonify({'success': True, 'message': f'Repository set to {repo_name}'})
    else:
        return jsonify({'success': False, 'message': 'Invalid repository path'}), 400

@app.route('/get_branches')
def get_branches():
    repo_name = request.args.get('repo')
    repo_path = get_repo_path(repo_name)
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
    repo_name = request.args.get('repo')
    repo_path = get_repo_path(repo_name)
    try:
        repo = Repo(repo_path)
        repo.git.checkout(branch_name)
        return jsonify({'success': True, 'message': f'Switched to branch {branch_name}'})
    except GitCommandError as e:
        return jsonify({'error': str(e)}), 400

def get_repo_path(repo_name=None):
    return os.path.join(GIT_REPO_PATH, repo_name) if repo_name else GIT_REPO_PATH

if __name__ == "__main__":
    if not vm_available:
        print("Warning: VM module is missing. Some features will not be available.")
    app.run(debug=True)