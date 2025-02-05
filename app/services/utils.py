import json
import os
import logging
import re
from typing import Any, Dict, List, Optional
from enum import Enum
import git

from app.utils import find_first_json_object, extract_json

logger = logging.getLogger(__name__)


class StepType(Enum):
    """
    Enum representing different types of steps in the process.
    """

    GENERATE_PLAN = "Generate Plan"
    STEP_EXECUTION = "StepExecution"
    PLAN_UPDATE = "PlanUpdate"
    STEP_OPTIMIZATION = "StepOptimization"


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
        logger.error("Failed to parse plan: %s", e)
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


def parse_commit_message(message) -> tuple:
    """Parse a commit message and return its components."""
    seq_no = "Unknown"
    try:
        if isinstance(message, dict):
            commit_info = message
        else:
            commit_info = json.loads(message)
        title = commit_info.get("description", "No description")
        details = {
            "input_parameters": commit_info.get("input_parameters", {}),
            "output_variables": commit_info.get("output_variables", {}),
        }
        commit_type = commit_info.get("type", "General")
        seq_no = commit_info.get("seq_no", "Unknown")
    except json.JSONDecodeError:
        title = message
        details = {}
        commit_type = "General"

    return seq_no, title, details, commit_type
