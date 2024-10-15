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
from app.tools import global_tools_hub
from .plan_repo import commit_vm_changes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
)

def generate_plan(llm_interface: LLMInterface, goal, custom_prompt=None):
    if not goal:
        logging.error("No goal is set.")
        return []

    prompt = custom_prompt or get_generate_plan_prompt(
        goal, VM_SPEC_CONTENT, global_tools_hub.get_tools_description(), PLAN_EXAMPLE_CONTENT
    )
    plan_response = llm_interface.generate(prompt)

    logging.info(f"Generating plan using LLM: {plan_response}")

    if not plan_response:
        logging.logger.error(f"LLM failed to generate a response: {plan_response}")
        return []

    plan = parse_plan(plan_response)

    if plan:
        return plan
    else:
        logging.logger.error(f"Failed to parse the generated plan: {plan_response}")
        return []


def generate_updated_plan(vm: PlanExecutionVM, explanation: str, key_factors: list):
    prompt = get_plan_update_prompt(
        vm, VM_SPEC_CONTENT, global_tools_hub.get_tools_description(), explanation, key_factors
    )
    new_plan = generate_plan(vm.llm_interface, vm.state["goal"], custom_prompt=prompt)
    return new_plan


def should_update_plan(vm: PlanExecutionVM):
    if vm.state.get("errors"):
        logging.info("Plan update triggered due to errors.")
        return (
            True,
            "Errors detected in VM state",
            [{"factor": "VM errors", "impact": "Critical"}],
        )

    prompt = get_should_update_plan_prompt(vm)
    response = vm.llm_interface.generate(prompt)

    json_response = find_first_json_object(response)
    if json_response:
        analysis = json.loads(json_response)
    else:
        logging.error("No valid JSON object found in the response.")
        return False, "No valid JSON object found.", []

    should_update = analysis.get("should_update", False)
    explanation = analysis.get("explanation", "")
    key_factors = analysis.get("key_factors", [])

    if should_update:
        logging.info(f"LLM suggests updating the plan: {explanation}")
        for factor in key_factors:
            logging.info(f"Factor: {factor['factor']}, Impact: {factor['impact']}")
    else:
        logging.info(f"LLM suggests keeping the current plan: {explanation}")

    return should_update, explanation, key_factors


def run_vm_with_goal(vm, goal):
    vm.set_goal(goal)
    plan = generate_plan(vm.llm_interface, goal)
    if plan:
        logging.info("Generated Plan:")
        vm.state["current_plan"] = plan

        while True:
            success = vm.step()
            commit_vm_changes(vm)
            if not success:
                break

            if vm.state.get("goal_completed"):
                logging.info("Goal completed during plan execution.")
                break

        if vm.state.get("goal_completed"):
            final_answer = vm.get_variable("final_answer")
            if final_answer:
                logging.info(f"\nfinal_answer: {final_answer}")
            else:
                logging.info("\nNo result was generated.")
        else:
            logging.warning("Plan execution failed or did not complete.")
            logging.error(vm.state.get("errors"))
    else:
        logging.error("Failed to generate plan.")
