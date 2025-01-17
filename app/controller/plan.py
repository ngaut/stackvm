"""
Visualization module for the VM execution and Git repository management.
"""

import json
import logging

from app.config.settings import VM_SPEC_CONTENT, PLAN_EXAMPLE_CONTENT
from app.services import (
    find_first_json_object,
    parse_plan,
)
from app.services import PlanExecutionVM
from app.services import (
    LLMInterface,
    get_plan_update_prompt,
    get_should_update_plan_prompt,
    get_generate_plan_prompt,
)
from app.instructions import global_tools_hub

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
        logger.error("LLM failed to generate a response: %s", plan_response)
        raise ValueError(
            "LLM failed to generate a response for your question. Please try again later."
        )

    plan = parse_plan(plan_response)

    if plan:
        return plan
    else:
        logger.error(
            "Failed to parse the generated plan: %s for goal: %s", plan_response, goal
        )
        raise PlanUnavailableError(plan_response)


def generate_updated_plan(
    vm: PlanExecutionVM, explanation: str, key_factors: list, allowed_tools=None
):
    prompt = get_plan_update_prompt(
        vm,
        VM_SPEC_CONTENT,
        global_tools_hub.get_tools_description(allowed_tools),
        explanation,
        key_factors,
    )
    new_plan = generate_plan(
        vm.llm_interface,
        vm.state["goal"],
        custom_prompt=prompt,
        allowed_tools=allowed_tools,
    )
    return new_plan


def should_update_plan(vm: PlanExecutionVM, suggestion: str):
    if vm.state.get("errors"):
        logger.info("Plan update triggered due to errors.")
        return (
            True,
            "Errors detected in VM state",
            [{"factor": "VM errors", "impact": "Critical"}],
        )

    prompt = get_should_update_plan_prompt(vm, suggestion)
    response = vm.llm_interface.generate(prompt)

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
