import re
from typing import Dict, Tuple, Any


def describe_goal(goal: str, metadata: Dict[str, Any]) -> str:
    """
    Describe the goal in a more detailed and structured way.

    Args:
        goal: The original task goal
        metadata: Task metadata containing response format, label path etc.

    Returns:
        A formatted string describing the complete goal context
    """
    description_parts = []

    # Add the main goal
    description_parts.append(f"Goal: {goal}")

    if metadata:
        response_format = metadata.get("response_format", {})

        if response_format is None:
            response_format = {}

        # Add background information if present
        background = response_format.get("Background") or response_format.get(
            "background"
        )
        if background:
            description_parts.append(f"Background: {background}")

        # Add annotations if present
        annotations = response_format.get("Annotations") or response_format.get(
            "annotations"
        )
        if annotations:
            description_parts.append(f"Annotations: {annotations}")

        # Add language information if present
        lang = response_format.get("Lang") or response_format.get("lang")
        if lang:
            description_parts.append(f"Response Language: {lang}")

        # Add format requirements if present
        format_req = response_format.get("Format") or response_format.get("format")
        if format_req:
            description_parts.append(f"Response Format: {format_req}")

        # Add label path if present
        label_path = metadata.get("label_path")
        if label_path:
            if isinstance(label_path, list):
                # Handle both string list and dict list formats
                path_str = " -> ".join(
                    item["label"] if isinstance(item, dict) else item
                    for item in label_path
                )
                description_parts.append(f"Labels: {path_str}")

    return "\n".join(description_parts)


def parse_goal_response_format(goal: str) -> Tuple[str, Dict[str, str]]:
    """
    Extracts the main goal and its requirements from the input string.

    Args:
        question_str (str): The input question string with optional requirements.

    Returns:
        Tuple[str, Dict[str, str]]: A tuple containing the main goal and a dictionary of requirements.
    """
    # Initialize
    clean_goal = goal.strip()
    response_format = None

    # Remove starting quote if present
    if clean_goal.startswith('"'):
        clean_goal = clean_goal[1:].strip()

    # Remove ending quote if present
    if clean_goal.endswith('"'):
        clean_goal = clean_goal[:-1].strip()

    # Function to find the last balanced parentheses by reverse traversal
    def extract_last_parentheses(s: str) -> Tuple[str, str]:
        """
        Extracts the last balanced parentheses content from the string by traversing from the end.

        Args:
            s (str): The input string.

        Returns:
            Tuple[str, str]: A tuple containing the string without the last parentheses
                             and the content within the last parentheses.
        """
        stack = []
        last_close = s.rfind(")")
        if last_close == -1:
            return s, ""  # No closing parenthesis found

        for i in range(last_close, -1, -1):
            if s[i] == ")":
                stack.append(i)
            elif s[i] == "(":
                if stack:
                    stack.pop()
                    if not stack:
                        # Found the matching opening parenthesis
                        return s[:i].strip(), s[i + 1 : last_close].strip()
        return s, ""  # No matching opening parenthesis found

    # Extract the last parentheses content
    clean_goal, req_str = extract_last_parentheses(clean_goal)

    if req_str:
        response_format = _parse_response_format(req_str)

    return clean_goal, response_format


def _parse_response_format(response_format_str: str) -> Dict[str, str]:
    """
    Parses the requirements string into a dictionary.

    Args:
        req_str (str): The requirements string.

    Returns:
        Dict[str, str]: A dictionary of parsed requirements.
    """
    requirements = {}
    parts = re.split(r",\s*(?=\w[\w\s]*:\s*[^,()]+)", response_format_str)
    for part in parts:
        if ":" in part:
            key, value = part.split(":", 1)
            requirements[key.strip()] = value.strip()
        else:
            requirements[part.strip()] = None
    return requirements
