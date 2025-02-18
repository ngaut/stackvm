import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.utils import find_first_json_object, extract_json

logger = logging.getLogger(__name__)


def extract_reasoning_and_plan(
    plan_response: str,
) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
    """Extract reasoning and plan from the response.

    The response format is:
    <think>reasoning content</think>
    <answer>
    ```json
    [
      {
        "seq_no": 0,
        ...
      },
      ...
    ]
    ```
    </answer>
    """
    try:
        # Extract reasoning
        think_match = re.search(r"<think>(.*?)</think>", plan_response, re.DOTALL)
        reasoning_content = None
        if think_match:
            reasoning_content = think_match.group(1).strip()

        # Extract plan
        answer_match = re.search(r"<answer>(.*?)</answer>", plan_response, re.DOTALL)
        if not answer_match:
            # If no answer is found, return the reasoning content and the original response
            return reasoning_content, plan_response

        answer_content = answer_match.group(1).strip()
        return reasoning_content, answer_content
    except (json.JSONDecodeError, ValueError) as e:
        # If the response is not in the expected format, return the original response
        logger.error(f"Failed to extract reasoning and plan: {e}. Data {plan_response}")
        return None, plan_response


def parse_plan(response: str) -> Dict:
    """Parse the plan response to extract a list of steps."""
    try:
        reasoning_content, plan_content = extract_reasoning_and_plan(response)
        json_str = extract_json(plan_content)

        try:
            plan = json.loads(json_str)
        except json.JSONDecodeError:
            json_str = re.sub(
                r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), json_str
            )
            plan = json.loads(json_str)

        if not isinstance(plan, list):
            raise ValueError("Parsed plan is not a list.")

        return {
            "reasoning": reasoning_content,
            "plan": plan,
        }
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Failed to parse plan: {e}. Data {response}")


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
