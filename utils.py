import json
import os
import logging
import re
from typing import Any, Dict, List, Optional
from enum import Enum
import git

class StepType(Enum):
    GENERATE_PLAN = "Generate Plan"
    STEP_EXECUTION = "StepExecution"
    PLAN_UPDATE = "PlanUpdate"

def parse_plan(plan_response: str) -> Optional[List[Dict[str, Any]]]:
    """Parse the plan response to extract a list of steps."""
    try:
        json_str = extract_json(plan_response)

        plan = json.loads(json_str)

        if not isinstance(plan, list):
            raise ValueError("Parsed plan is not a list.")
        
        # Modify specific steps if necessary
        for step in plan:
            if (step.get('type') == 'assign' and
                    step.get('parameters', {}).get('var_name') == 'final_summary'):
                step['parameters']['var_name'] = 'result'
        
        return plan
    except (json.JSONDecodeError, ValueError) as e:
        logging.error(f"Failed to parse plan: {e}")
        return None

def extract_json(plan_response: str) -> str:
    """Extract JSON from the plan response."""
    json_code_block_pattern = re.compile(r'```json\s*(\[\s*{.*?}\s*\])\s*```', re.DOTALL)
    match = json_code_block_pattern.search(plan_response)
    if match:
        return match.group(1)
    
    json_str = find_first_json_array(plan_response)
    if not json_str:
        raise ValueError("No valid JSON array found in the response.")
    
    return json_str

def load_state(commit_hash: str, repo_path: str) -> Optional[Dict[str, Any]]:
    """Load the state from a file based on the specific commit point."""
    try:
        repo = git.Repo(repo_path)
        state_content = repo.git.show(f'{commit_hash}:vm_state.json')
        return json.loads(state_content)
    except (git.exc.GitCommandError, json.JSONDecodeError) as e:
        logging.error(f"Error loading state from commit {commit_hash}: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error loading state from commit {commit_hash}: {str(e)}")
    return None

def save_state(state: Dict[str, Any], repo_path: str) -> None:
    """Save the state to a file in the repository."""
    try:
        state_file = os.path.join(repo_path, 'vm_state.json')
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2, default=str, sort_keys=True)
    except Exception as e:
        logging.error(f"Error saving state: {str(e)}")

def get_commit_message_schema(step_type: str, seq_no: str, description: str, input_parameters: Dict[str, Any], output_variables: Dict[str, Any]) -> str:
    """Generate a commit message schema in JSON format."""
    commit_info = {
        "type": step_type,
        "seq_no": seq_no,
        "description": description,
        "input_parameters": input_parameters,
        "output_variables": output_variables
    }
    return json.dumps(commit_info)

def parse_commit_message(message: str) -> tuple:
    """Parse a commit message and return its components."""
    seq_no = "Unknown"
    try:
        commit_info = json.loads(message)
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
    """Find the first JSON array in the given text."""
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
    """Find the first JSON object in the given text."""
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