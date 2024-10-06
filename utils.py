import json
from typing import Any, Dict, List, Optional
import os
import git
import logging

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
        start = plan_response.find('[')
        end = plan_response.rfind(']')
        
        if start != -1 and end != -1 and start < end:
            json_str = plan_response[start:end+1]
            plan = json.loads(json_str)
        else:
            raise ValueError("No valid JSON array found in the response")
        
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
        logging.info(f"State loaded from commit {commit_hash}")
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
            json.dump(state, f, indent=2, default=str)
        logging.info(f"State saved to {state_file}")
    except Exception as e:
        logging.error(f"Error saving state: {str(e)}")

# Add any other utility functions here