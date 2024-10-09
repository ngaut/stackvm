import json
from typing import Any, Dict, List, Optional
import os
import git
import logging
from enum import Enum

class StepType(Enum):
    GENERATE_PLAN = "Generate Plan"
    STEP_EXECUTION = "StepExecution"
    PLAN_UPDATE = "PlanUpdate"

def interpolate_variables(text: Any, variables: Dict[str, Any]) -> Any:
    if not isinstance(text, str):
        return text
    for var, value in variables.items():
        if f"{{{{{var}}}}}" in text:
            text = text.replace(f"{{{{{var}}}}}", str(value))
    return text

def parse_plan(plan_response: str) -> Optional[List[Dict[str, Any]]]:
    try:
        print(f"Parsing plan: {plan_response}")
        json_str = find_first_json_array(plan_response)
        
        if json_str is None:
            raise ValueError("No valid JSON array found in the response")
        
        plan = json.loads(json_str)
        
        if not isinstance(plan, list):
            raise ValueError("Parsed plan is not a list")
        
        for step in plan:
            if (step.get('type') == 'assign' and
                    step.get('parameters', {}).get('var_name') == 'final_summary'):
                step['parameters']['var_name'] = 'result'
        
        return plan
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Failed to parse plan: {e}")
        return None

def load_state(commit_hash, repo_path):
    """
    Load the state from a file based on the specific commit point.
    """
    try:
        repo = git.Repo(repo_path)
        state_content = repo.git.show(f'{commit_hash}:vm_state.json')
        loaded_state = json.loads(state_content)
        return loaded_state
    except git.exc.GitCommandError as e:
        logging.error(f"Error loading state from commit {commit_hash}: {str(e)}")
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing state JSON from commit {commit_hash}: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error loading state from commit {commit_hash}: {str(e)}")
    return None

def save_state(state, repo_path):
    """
    Save the state to a file in the repository.
    """
    try:
        state_file = os.path.join(repo_path, 'vm_state.json')
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2, default=str, sort_keys=True)
    except Exception as e:
        logging.error(f"Error saving state: {str(e)}")

def get_commit_message_schema(step_type: str, seq_no: str, description: str, input_parameters: Dict[str, Any], output_variables: Dict[str, Any]) -> str:
    commit_info = {
        "type": step_type,
        "seq_no": seq_no,
        "description": description,
        "input_parameters": input_parameters,
        "output_variables": output_variables
    }
    return json.dumps(commit_info)  # Convert to JSON format

def parse_commit_message(message):
    seq_no = "Unknown"

    try:
        commit_info = json.loads(message)  # Parse JSON formatted message
        title = commit_info.get("description", "No description")
        details = {
            "input_parameters": commit_info.get("input_parameters", {}),
            "output_variables": commit_info.get("output_variables", {})
        }
        commit_type = commit_info.get("type", "General")
        seq_no = commit_info.get("seq_no", "Unknown")
    except json.JSONDecodeError:
        title = "Invalid commit message"
        details = {}
        commit_type = "General"

    return seq_no, title, details, commit_type

def find_first_json_array(text: str) -> Optional[str]:
    stack = []
    start = -1
    for i, char in enumerate(text):
        if char == '[':
            if not stack:
                start = i
            stack.append(i)
        elif char == ']':
            if stack:
                stack.pop()
                if not stack:
                    return text[start:i+1]
    return None

def find_first_json_object(text: str) -> Optional[str]:
    stack = []
    start = -1
    for i, char in enumerate(text):
        if char == '{':
            if not stack:
                start = i
            stack.append(i)
        elif char == '}':
            if stack:
                stack.pop()
                if not stack:
                    return text[start:i+1]
    return None
