import json
import datetime


def get_plan_update_prompt(
    goal,
    metadata,
    vm_program_counter,
    vm_spec_content,
    tools_instruction_content,
    plan,
    suggestion,
    key_factors=None,
):
    """
    Get the prompt for updating the plan.
    """
    prompt = f"""Today is {datetime.date.today().strftime("%Y-%m-%d")}
Analyze the current VM execution state and update the plan based on suggestions and the current execution results.

Goal:
{goal}

The supplementary information for Goal:
{metadata.get('response_format')}

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
Provide only the updated step in JSON format.
"""
