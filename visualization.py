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
    
    app.logger.info(f"Total commits found in branch {branch_name}: {len(commits)}")
    
    for commit in commits:
        commit_time = datetime.fromtimestamp(commit.committed_date)
        title, details = parse_commit_message(commit.message)  # Updated to match new parse_commit_message
        
        app.logger.info(f"Processing commit: {commit.hexsha}")
        app.logger.info(f"Commit message: {commit.message}")
        
        # Try to load VM state from the commit
        try:
            vm_state_content = repo.git.show(f'{commit.hexsha}:vm_state.json')
            vm_state = json.loads(vm_state_content)
            app.logger.info(f"VM state found for commit {commit.hexsha}")
        except GitCommandError as e:
            app.logger.info(f"No VM state found for commit {commit.hexsha}")
            vm_state = None
        
        vm_states.append({
            'time': commit_time.isoformat(),
            'title': title,
            'details': details,
            'commit_hash': commit.hexsha,
            'vm_state': vm_state
            # Removed 'step' field
        })

    app.logger.info(f"Extracted VM states: {vm_states}")
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
    
    app.logger.info(f"Extracted VM states for branch {branch} in repo {repo}: {vm_states}")
    
    return jsonify(vm_states)

@app.route('/vm_state/<commit_hash>')
def get_vm_state(commit_hash):
    if not vm_available:
        return jsonify({'error': 'VM module not available'}), 500

    repo_name = request.args.get('repo')
    repo_path = os.path.join(GIT_REPO_PATH, repo_name) if repo_name else GIT_REPO_PATH
    app.logger.info(f"Using repository path: {repo_path}")
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
    repo_path = os.path.join(GIT_REPO_PATH, repo_name) if repo_name else GIT_REPO_PATH
    app.logger.info(f"Using repository path: {repo_path}")
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
    repo_path = os.path.join(GIT_REPO_PATH, repo_name) if repo_name else GIT_REPO_PATH
    app.logger.info(f"Using repository path: {repo_path}")
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
    if not vm_available:
        return jsonify({'error': 'VM module not available'}), 500

    data = request.json
    commit_hash = data.get('commit_hash')
    steps = data.get('steps', 1)
    start_from = data.get('start_from', 0)
    repo_name = data.get('repo')
    repo_path = os.path.join(GIT_REPO_PATH, repo_name) if repo_name else GIT_REPO_PATH
    app.logger.info(f"Using repository path: {repo_path}")
    repo = git.Repo(repo_path)
    try:
        commit = repo.commit(commit_hash)
        vm_state_content = repo.git.show(f'{commit.hexsha}:vm_state.json')
        vm_state = json.loads(vm_state_content)

        vm = VM()
        vm.load_state(vm_state)

        # Set the program counter to the specified starting point
        if hasattr(vm, 'state'):
            vm.state['program_counter'] = start_from
        elif hasattr(vm, 'variables'):
            vm.variables['program_counter'] = start_from
        else:
            return jsonify({'error': 'Unable to set program counter'}), 400

        for _ in range(steps):
            vm.step()

        return jsonify(vm.get_state())
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/vm_state_details/<commit_hash>')
def vm_state_details(commit_hash):
    repo_name = request.args.get('repo')
    repo_path = os.path.join(GIT_REPO_PATH, repo_name) if repo_name else GIT_REPO_PATH
    app.logger.info(f"Using repository path: {repo_path}")
    repo = git.Repo(repo_path)
    try:
        commit = repo.commit(commit_hash)
        try:
            # Attempt to retrieve vm_state.json from the commit
            vm_state_content = repo.git.show(f'{commit.hexsha}:vm_state.json')
            vm_state = json.loads(vm_state_content)
            
            # Extract variables and parameters
            variables = vm_state.get('variables', {})
            parameters = vm_state.get('parameters', {})
            
            # **Removed check that returns 404 when both are empty**
            # Now, even if variables and parameters are empty, we return them
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
    repo_path = os.path.join(GIT_REPO_PATH, repo_name) if repo_name else GIT_REPO_PATH
    try:
        repo = Repo(repo_path)
        app.logger.info(f"Git repository path: {repo_path}")
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
        # Sort branches: active branch first, then by last commit date
        branch_data.sort(key=lambda x: (-x['is_active'], x['last_commit_date']), reverse=True)
        return jsonify(branch_data)
    except GitCommandError as e:
        return jsonify({'error': str(e)}), 500

@app.route('/set_branch/<branch_name>')
def set_branch(branch_name):
    repo_name = request.args.get('repo')
    repo_path = os.path.join(GIT_REPO_PATH, repo_name) if repo_name else GIT_REPO_PATH
    try:
        repo = Repo(repo_path)
        repo.git.checkout(branch_name)
        return jsonify({'success': True, 'message': f'Switched to branch {branch_name}'})
    except GitCommandError as e:
        return jsonify({'error': str(e)}), 400

if __name__ == "__main__":
    if not vm_available:
        print("Warning: VM module is missing. Some features will not be available.")
    app.run(debug=True)