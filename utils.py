import json
from typing import Any, Dict, List, Optional

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