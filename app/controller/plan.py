"""
Visualization module for the VM execution and Git repository management.
"""

import json
import logging

from app.config.settings import (
    VM_SPEC_CONTENT,
    PLAN_EXAMPLE_CONTENT,
)
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


def generate_plan(llm_interface: LLMInterface, goal, custom_prompt=None):
    if not goal:
        logger.error("No goal is set.")
        return []

    prompt = custom_prompt or get_generate_plan_prompt(
        goal,
        VM_SPEC_CONTENT,
        global_tools_hub.get_tools_description(),
        PLAN_EXAMPLE_CONTENT,
    )
    plan_response = llm_interface.generate(prompt)

    if not plan_response:
        logger.error("LLM failed to generate a response: %s", plan_response)
        return []

    plan = parse_plan(plan_response)

    if plan:
        return plan
    else:
        logger.error("Failed to parse the generated plan: %s", plan_response)
        return []


def generate_updated_plan(vm: PlanExecutionVM, explanation: str, key_factors: list):
    prompt = get_plan_update_prompt(
        vm,
        VM_SPEC_CONTENT,
        global_tools_hub.get_tools_description(),
        explanation,
        key_factors,
    )
    new_plan = generate_plan(vm.llm_interface, vm.state["goal"], custom_prompt=prompt)
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
