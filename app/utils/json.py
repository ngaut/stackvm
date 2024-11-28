import re
from typing import Optional, Tuple, Dict


def extract_json(plan_response: str) -> str:
    """Extract JSON from the plan response."""
    json_code_block_pattern = re.compile(
        r"```json\s*(\[\s*{.*?}\s*\])\s*```", re.DOTALL
    )
    match = json_code_block_pattern.search(plan_response)
    if match:
        return match.group(1)

    json_str = find_first_json_array(plan_response)
    if not json_str:
        raise ValueError("No valid JSON array found in the response.")

    return json_str


def find_first_json_array(text: str) -> Optional[str]:
    """Find the first JSON array in the given text."""
    stack = []
    start = -1
    for i, char in enumerate(text):
        if char == "[":
            if not stack:
                start = i
            stack.append(i)
        elif char == "]":
            if stack:
                stack.pop()
                if not stack:
                    return text[start : i + 1]
    return None


def find_first_json_object(text: str) -> Optional[str]:
    """Find the first JSON object in the given text."""
    stack = []
    start = -1
    for i, char in enumerate(text):
        if char == "{":
            if not stack:
                start = i
            stack.append(i)
        elif char == "}":
            if stack:
                stack.pop()
                if not stack:
                    return text[start : i + 1]
    return None


def parse_goal_requirements(goal: str) -> Tuple[str, Dict[str, str]]:
    """
    Extracts the main goal and its requirements from the input string.

    Args:
        question_str (str): The input question string with optional requirements.

    Returns:
        Tuple[str, Dict[str, str]]: A tuple containing the main goal and a dictionary of requirements.
    """
    # Initialize
    clean_goal = goal.strip()
    requirements = {}

    # Remove starting quote if present
    if clean_goal.startswith('"'):
        clean_goal = clean_goal[1:].strip()

    # Remove ending quote if present
    if clean_goal.endswith('"'):
        clean_goal = clean_goal[:-1].strip()

    # Pattern to identify requirements in parentheses at the end
    pattern = r"\((.*?)\)\s*$"

    # Search for the pattern in the clean goal
    match = re.search(pattern, clean_goal, re.DOTALL)
    if match:
        req_str = match.group(1).strip()
        # Extract the main goal by removing the matched requirements
        clean_goal = clean_goal[: match.start()].strip()
        # Parse the requirements string into a dictionary
        requirements = _parse_requirements(req_str)

    return clean_goal, requirements


def _parse_requirements(req_str: str) -> Dict[str, str]:
    """
    Parses the requirements string into a dictionary.

    Args:
        req_str (str): The requirements string.

    Returns:
        Dict[str, str]: A dictionary of parsed requirements.
    """
    req_dict = {}
    others = []

    # Split the requirements by comma or newline
    parts = re.split(r",\s*|\n", req_str)

    for part in parts:
        part = part.strip().rstrip(".")  # Remove trailing periods
        if ":" in part:
            key, value = part.split(":", 1)
            key = key.strip()
            value = value.strip()
            req_dict[key] = value
        elif part:
            others.append(part)

    if others:
        req_dict["Others"] = ", ".join(others)

    return req_dict
