import datetime
import json
import logging
from typing import Dict

from app.config.settings import VM_SPEC_CONTENT
from app.core.plan.prompts import get_plan_update_prompt, get_whole_plan_update_prompt
from app.llm.interface import LLMInterface
from app.utils import extract_json
from app.instructions import global_tools_hub
from app.core.plan.utils import parse_plan


logger = logging.getLogger(__name__)


def optimize_whole_plan(
    llm_client: LLMInterface,
    goal: str,
    plan: str,
    suggestion: str | Dict,
    user_instructions: str,
    allowed_tools=None,
):
    """
    Get the prompt for updating the plan.
    """

    updated_prompt = get_whole_plan_update_prompt(
        goal,
        plan,
        suggestion,
        user_instructions,
        VM_SPEC_CONTENT,
        global_tools_hub.get_tools_description(allowed_tools),
    )

    try:
        plan_response = llm_client.generate(updated_prompt)
        plan_data = parse_plan(plan_response)
        if plan_data:
            return plan_data

        raise ValueError(
            f"Failed to parse the updated plan: {plan_response} for goal: {goal}"
        )
    except Exception as e:
        logger.error(f"Error optimizing plan: {e}")
        return None


def optimize_partial_plan(
    llm_interface: LLMInterface,
    goal,
    vm_program_counter,
    plan,
    reasoning,
    suggestion: str | Dict,
    allowed_tools=None,
):
    prompt = get_plan_update_prompt(
        goal,
        vm_program_counter,
        VM_SPEC_CONTENT,
        global_tools_hub.get_tools_description(allowed_tools),
        plan,
        reasoning,
        suggestion,
    )

    plan_response = None
    try:
        plan_response = llm_interface.generate(prompt)
        if not plan_response:
            logger.error("LLM failed to update the plan: %s", plan_response)
            raise ValueError("LLM failed to update the plan. Please try again later.")

        plan = parse_plan(plan_response)
        if plan:
            return plan

        raise ValueError(
            f"Failed to parse the updated plan: {plan_response} for goal: {goal}"
        )
    except Exception as e:
        logger.error(
            "Error optimizing partial plan: %s. Response: %s", e, plan_response
        )
        raise e
