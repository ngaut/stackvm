import json
import datetime


def get_whole_plan_update_prompt(
    goal,
    plan,
    suggestion,
    user_instructions,
    VM_SPEC_CONTENT,
    allowed_tools,
):
    return f"""Today is {datetime.date.today().strftime("%Y-%m-%d")}

Here are the inputs:

## Goal Input
{goal}

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
{allowed_tools}

-------------------------------

Now, let's update the plan.

**Output**:
1. Provide the complete updated plan in JSON format, ensuring it adheres to the VM specification.
2. Provide a summary of the changes made to the plan, including a diff with the previous plan.

You should response in the following format:

<think>...</think>
<answer>
```json
[
  {{
    "seq_no": 0,
    ...
  }},
  ...
]
```
</answer>

where <think> is your detailed reasoning process in text format and the JSON array inside the answer is a valid plan."""


def get_plan_update_prompt(
    goal,
    vm_program_counter,
    vm_spec_content,
    tools_instruction_content,
    plan,
    reasoning,
    suggestion,
    key_factors=None,
):
    """
    Get the prompt for updating the plan.
    """
    prompt = f"""Today is {datetime.date.today().strftime("%Y-%m-%d")}
Analyze the current VM execution state and update the plan based on suggestions and the current execution results.

Goal Input:
{goal}

Reasoning for the current plan:
{reasoning}

Current Plan:
{json.dumps(plan, indent=2)}

Current Program Counter: {vm_program_counter}

Last Executed Step: {json.dumps(plan[vm_program_counter - 1], indent=2) if vm_program_counter > 0 else "No steps executed yet"}

**Suggestion for plan update**: {suggestion}
"""

    if key_factors and len(key_factors) > 0:
        prompt += f"\nKey factors influencing the update:\n{json.dumps(key_factors, indent=2)}\n"

    prompt += f"""

**Instructions**:
1. **Analyze Suggestions and Current Execution**:
    - Review the suggestions in detail.
    - Assess how the suggestions align with the current execution results and overall goal.

2. **Identify and Prioritize Changes**:
    - Determine which suggestions directly contribute to achieving the goal.
    - Prioritize changes based on their potential impact and feasibility.

3. **Propose Solutions**:
    - Suggest modifications to existing steps to incorporate suggestions.
    - Introduce new steps or action types if necessary to align with suggestions.
    - Ensure that each modification or addition directly contributes to achieving the goal.

4. **Evaluate Critical Aspects**:
    - **Goal Alignment**: Ensure the updated plan remains focused on the primary objective.
    - **Efficiency**: Optimize the plan for better performance and resource utilization.
    - **Potential Obstacles**: Identify and mitigate foreseeable challenges.
    - **Adaptability**: Ensure the plan can handle unexpected changes.

5. **Maintain Referential Integrity**:
    - Do not reference output variables from already executed steps if those variables are not present in Current Variables, as they have been garbage collected.

6. **Merge with Original Plan**:
    - Integrate proposed changes seamlessly into the original plan starting from the current program counter.
    - Preserve all steps prior to the current program counter without alteration.

7. **Adhere to VM Specification**:
    - Ensure that the revised plan complies with the provided VM specification in format and structure.

8. **Avoid Redundancy**:
    - Do not generate an identical plan. Ensure that the updated plan includes at least some meaningful changes to improve upon the original.

**MUST follow VM Specification**:
{vm_spec_content}

## 9. Available Tools for `calling` instruction
{tools_instruction_content}

IMPORTANT: For calling instruction, Only select tools listed in the "Available Tools" section. Using tools outside this list will cause the plan to fail.

-------------------------------

Now, let's update the plan.

**Output**:

You should response your reasoning and the updated plan (a valid json array) in the following format:

<think>...</think>
<answer>
```json
[
  {{
    "seq_no": 0,
    ...
  }},
  ...
]
```
</answer>

where <think> is your detailed reasoning process in text format and the JSON array inside the answer is a valid plan."""

    return prompt


def get_step_update_prompt(
    plan, vm_variables, seq_no, vm_spec_content, tools_instruction_content, suggestion
):
    """
    Get the prompt for updating a step.
    """
    current_step = plan[seq_no]
    current_variables = json.dumps(vm_variables, indent=2)

    return f"""Today is {datetime.date.today().strftime("%Y-%m-%d")}
You are tasked with updating a specific step in the VM execution plan.

Current Step (seq_no: {seq_no}):
{json.dumps(current_step, indent=2)}

Current VM Variables:
{current_variables}

Suggestion for Improvement:
{suggestion}

**MUST follow the Specification**:
{vm_spec_content}

## 8. Available Tools for `calling` instruction
{tools_instruction_content}

-------------------------------

Now, let's update the step.
1. Analyze the current step, the provided suggestion, and the current VM variables.
2. Modify the step to incorporate the suggestion while ensuring it aligns with the overall goal and plan structure.
3. Ensure the updated step is consistent with the VM's current state and does not introduce redundancy.

**Output**:
Provide only the updated step in JSON format. For example:
```json
{{
    "seq_no": 2,
    "type": "calling",
    ...
}}
```
"""
