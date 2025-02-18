import datetime
import json
import logging
from typing import Dict

from app.config.settings import VM_SPEC_CONTENT
from app.core.plan.prompts import get_plan_update_prompt, get_generate_plan_prompt
from app.llm.interface import LLMInterface
from app.utils import extract_json
from app.instructions import global_tools_hub
from app.core.plan.utils import parse_plan


logger = logging.getLogger(__name__)


def optimize_whole_plan(
    llm_client: LLMInterface,
    goal: str,
    metadata: dict,
    plan: str,
    suggestion: str | Dict,
    user_instructions: str,
    allowed_tools=None,
):
    """
    Get the prompt for updating the plan.
    """

    updated_prompt = f"""Today is {datetime.date.today().strftime("%Y-%m-%d")}

Here are the inputs:

## Goal
{goal}

The supplementary information for Goal:
{metadata.get('response_format')}

## Previous Plan:
{plan}

## **Evaluation Feedback**:
{suggestion}

------------------------------------

As the evaluating feedback said, the previous plan has been rejected or found insufficient in fully addressing the goal. Please revise the previous plan based on these guidelines and the evaluation feedback.

{user_instructions}

------------------------------------
Make sure the updated plan adheres to the Executable Plan Specifications:

{VM_SPEC_CONTENT}

------------------------------------

Make sure only use these available tools in `calling` instruction:
{global_tools_hub.get_tools_description(allowed_tools)}

-------------------------------

Now, let's update the plan.

**Output**:
1. Provide the complete updated plan in JSON format, ensuring it adheres to the VM specification.
2. Provide a summary of the changes made to the plan, including a diff with the previous plan.

Ensure the plan is a valid JSON and is properly formatted and encapsulated within a ```json code block.

```json
[
    {{
    "seq_no": 0,
    "type": "reasoning",
    "parameters": {{
        "chain_of_thoughts": "...",
        "dependency_analysis": "..."
    }}
    }},
    ...
]
```"""

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
    metadata,
    vm_program_counter,
    plan,
    reasoning,
    suggestion: str | Dict,
    allowed_tools=None,
):
    prompt = get_plan_update_prompt(
        goal,
        metadata,
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
