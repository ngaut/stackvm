"""
Visualization module for the VM execution and Git repository management.
"""

import logging
from app.config.settings import VM_SPEC_CONTENT, PLAN_EXAMPLE_CONTENT
from app.core.plan.utils import parse_plan
from app.core.plan.prompts import get_generate_plan_prompt
from app.instructions import global_tools_hub
from app.llm.interface import LLMInterface

logger = logging.getLogger(__name__)


class PlanUnavailableError(ValueError):
    """Custom error raised when plan generation or parsing fails."""

    pass


def generate_plan(
    llm_interface: LLMInterface,
    goal,
    custom_prompt=None,
    example=None,
    best_practices=None,
    allowed_tools=None,
):
    if not goal:
        logger.error("No goal is set.")
        return []

    prompt = custom_prompt or get_generate_plan_prompt(
        goal,
        VM_SPEC_CONTENT,
        global_tools_hub.get_tools_description(allowed_tools),
        example or PLAN_EXAMPLE_CONTENT,
        best_practices or "Refer the best practices and example",
    )

    plan_response = llm_interface.generate(prompt)

    if not plan_response:
        logger.error(f"LLM failed to generate a response: {plan_response}")
        raise ValueError(
            f"LLM failed to generate a response for your question: {plan_response}. Please try again later."
        )

    plan_data = parse_plan(plan_response)

    if plan_data:
        return plan_data

    logger.error(
        f"Failed to parse the generated plan: {plan_response} for goal: {goal}"
    )
    raise PlanUnavailableError(plan_response)
