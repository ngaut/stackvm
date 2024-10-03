import os
import json
from datetime import datetime
from flask import Flask, render_template, jsonify, request, abort
from config import GIT_REPO_PATH
from git_manager import GitManager

# Conditional imports to handle potential missing packages
try:
    import git
except ImportError:
    print("GitPython is not installed. Please install it using: pip install GitPython")
    git = None

try:
    from vm import VM
except ImportError:
    print("VM module not found. Make sure vm.py is in the same directory and exports a VM class.")
    VM = None

app = Flask(__name__)
git_manager = GitManager(GIT_REPO_PATH)

def parse_commit_message(message):
    lines = message.split('\n')
    title = lines[0]
    details = {}
    
    for line in lines[1:]:
        if ':' in line:
            key, value = line.split(':', 1)
            details[key.strip()] = value.strip()
    
    return title, details

def extract_vm_info():
    repo = git.Repo(GIT_REPO_PATH)
    commits = list(repo.iter_commits('main'))
    
    vm_states = []
    
    for commit in commits:
        commit_time = datetime.fromtimestamp(commit.committed_date)
        title, details = parse_commit_message(commit.message)
        
        # Try to load VM state from the commit
        try:
            vm_state_content = repo.git.show(f'{commit.hexsha}:vm_state.json')
            vm_state = json.loads(vm_state_content)
        except git.exc.GitCommandError:
            vm_state = None
        
        # Extract step information
        step_info = None
        if '[' in title and ']' in title:
            step_type = title.split('[')[1].split(']')[0]
            step_info = {
                'type': step_type,
                'details': details
            }
        
        vm_states.append({
            'time': commit_time.isoformat(),
            'title': title,
            'details': details,
            'vm_state': vm_state,
            'step': step_info
        })
    
    return vm_states

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/vm_data')
def vm_data():
    vm_states = extract_vm_info()
    return jsonify(vm_states)

@app.route('/vm_state/<commit_hash>')
def vm_state(commit_hash):
    repo = git.Repo(GIT_REPO_PATH)
    try:
        commit = repo.commit(commit_hash)
        vm_state_content = repo.git.show(f'{commit.hexsha}:vm_state.json')
        vm_state = json.loads(vm_state_content)
        return jsonify(vm_state)
    except Exception as e:
        abort(404, description=str(e))

@app.route('/code_diff/<commit_hash>')
def code_diff(commit_hash):
    repo = git.Repo(GIT_REPO_PATH)
    try:
        commit = repo.commit(commit_hash)
        parent = commit.parents[0] if commit.parents else None
        diff = repo.git.diff(parent, commit, '--unified=3')
        return jsonify({'diff': diff})
    except Exception as e:
        abort(404, description=str(e))

@app.route('/commit_details/<commit_hash>')
def commit_details(commit_hash):
    repo = git.Repo(GIT_REPO_PATH)
    try:
        commit = repo.commit(commit_hash)
        details = {
            'hash': commit.hexsha,
            'author': commit.author.name,
            'date': commit.committed_datetime.isoformat(),
            'message': commit.message,
            'files_changed': [item.a_path for item in commit.diff(commit.parents[0])]
        }
        return jsonify(details)
    except Exception as e:
        return jsonify({'error': str(e)}), 404

@app.route('/execute_vm', methods=['POST'])
def execute_vm():
    if VM is None:
        return jsonify({'error': 'VM module not available'}), 500

    data = request.json
    commit_hash = data.get('commit_hash')
    steps = data.get('steps', 1)
    start_from = data.get('start_from', 0)
    
    repo = git.Repo(GIT_REPO_PATH)
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

@app.route('/memory_dump/<commit_hash>')
def memory_dump(commit_hash):
    repo = git.Repo(GIT_REPO_PATH)
    try:
        commit = repo.commit(commit_hash)
        vm_state_content = repo.git.show(f'{commit.hexsha}:vm_state.json')
        vm_state = json.loads(vm_state_content)
        
        memory = vm_state.get('memory', [])
        if not memory:
            return jsonify({'error': 'No memory data available'}), 404
        
        formatted_memory = [f"{i:04X}: {value:02X}" for i, value in enumerate(memory)]
        
        return jsonify({'memory': formatted_memory})
    except Exception as e:
        return jsonify({'error': str(e)}), 404

if __name__ == "__main__":
    if git is None or VM is None:
        print("Warning: Some required modules are missing. The application may not function correctly.")
    app.run(debug=True)