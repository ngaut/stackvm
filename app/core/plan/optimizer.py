"""
Visualization module for the VM execution and Git repository management.
"""

import json
import logging
from app.core.plan.utils import find_first_json_object
from app.core.plan.prompts import get_should_update_plan_prompt
from app.llm.interface import LLMInterface

logger = logging.getLogger(__name__)


def should_update_plan(
    llm_interface: LLMInterface,
    goal,
    vm_program_counter,
    plan,
    vm_variables,
    suggestion: str,
):
    prompt = get_should_update_plan_prompt(
        goal, vm_program_counter, plan, vm_variables, suggestion
    )
    response = llm_interface.generate(prompt)

    json_response = find_first_json_object(response)
    if json_response:
        analysis = json.loads(json_response)
    else:
        logger.error("No valid JSON object found in the response.")
        return False, "No valid JSON object found.", []

    should_update = analysis.get("should_update", False)
    explanation = analysis.get("explanation", "")
    key_factors = analysis.get("key_factors", [])

    if should_update:
        logger.info("LLM suggests updating the plan: %s", explanation)
        for factor in key_factors:
            logger.info("Factor: %s, Impact: %s", factor["factor"], factor["impact"])
    else:
        logger.info("LLM suggests keeping the current plan: %s", explanation)

    return should_update, explanation, key_factors
