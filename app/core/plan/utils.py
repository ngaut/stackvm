import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.utils import find_first_json_object, extract_json

logger = logging.getLogger(__name__)


def parse_plan(plan_response: str) -> Optional[List[Dict[str, Any]]]:
    """Parse the plan response to extract a list of steps."""
    try:
        json_str = extract_json(plan_response)

        plan = json.loads(json_str)

        if not isinstance(plan, list):
            raise ValueError("Parsed plan is not a list.")

        # Modify specific steps if necessary
        for step in plan:
            if (
                step.get("type") == "assign"
                and step.get("parameters", {}).get("var_name") == "final_summary"
            ):
                step["parameters"]["var_name"] = "result"

        return plan
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse plan: %s. Data %s", e, plan_response)
        return None


def parse_step(step_response: str) -> Optional[Dict[str, Any]]:
    """Parse the step response to extract a single step."""
    try:
        json_code_block_pattern = re.compile(r"```json\s*({.*?})\s*```", re.DOTALL)
        match = json_code_block_pattern.search(step_response)
        if match:
            json_str = match.group(1)
        else:
            json_str = find_first_json_object(step_response)

        if not json_str:
            raise ValueError("No valid JSON array found in the response.")

        step = json.loads(json_str)

        if not isinstance(step, dict):
            raise ValueError("Parsed step is not a dictionary.")

        return step
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse step: %s", e)
        return None
