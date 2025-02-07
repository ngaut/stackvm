import json
from enum import Enum


class CommitType(Enum):
    """
    Enum representing different types of steps in the process.
    """

    GENERATE_PLAN = "Generate Plan"
    STEP_EXECUTION = "StepExecution"
    PLAN_UPDATE = "PlanUpdate"
    STEP_OPTIMIZATION = "StepOptimization"


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
