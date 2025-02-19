import json
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def extract_json(plan_response: str) -> str:
    """Extract JSON from the plan response.

    Args:
        plan_response (str): The response string that may contain JSON.

    Returns:
        str: The extracted JSON string.

    Raises:
        ValueError: If no valid JSON content is found.
    """
    # First try to match JSON block with complete markdown code fence
    json_code_block_pattern = re.compile(r"```json\s*([\s\S]*?)\s*```", re.DOTALL)
    match = json_code_block_pattern.search(plan_response)
    if match:
        json_str = match.group(1).strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse JSON use default pattern: %s, %s", json_str, e
            )

    # Then try to match JSON block between first ```json and last ```
    first_marker = plan_response.find("```json")
    last_marker = plan_response.rfind("```")

    if first_marker != -1 and last_marker != -1 and first_marker < last_marker:
        json_str = plan_response[first_marker + 7 : last_marker].strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse JSON between markers: %s, %s", json_str, e)

    # Then try to match JSON block with only opening markdown fence
    start_pattern = re.compile(r"```json\s*([\s\S]*)", re.DOTALL)
    match = start_pattern.search(plan_response)
    if match:
        content = match.group(1).strip()
        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning(
                    "Failed to parse JSON use start pattern: %s, %s", content, e
                )

    # Finally try to parse the content as raw JSON
    content = plan_response.strip()
    if not content:
        raise ValueError("Empty content")

    # Determine JSON type by first character and extract accordingly
    if content.startswith("{"):
        json_str = find_first_json_object(content)
    elif content.startswith("["):
        json_str = find_first_json_array(content)
    else:
        raise ValueError("Content must start with '{' or '['")

    if json_str:
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse JSON use content pattern: %s, %s", content, e
            )

    raise ValueError("No valid JSON content found in the response.")


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
