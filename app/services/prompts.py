import json
import datetime


def get_plan_update_prompt(
    vm, vm_spec_content, tools_instruction_content, suggestion=None, key_factors=None
):
    """
    Get the prompt for updating the plan.
    """
    prompt = f"""Today is {datetime.date.today().strftime("%Y-%m-%d")}
Analyze the current VM execution state and update the plan based on suggestions and the current execution results.

Goal:
{vm.state['goal']}

Current Plan:
{json.dumps(vm.state['current_plan'], indent=2)}

Current Program Counter: {vm.state['program_counter']}
Last Executed Step: {json.dumps(vm.state['current_plan'][vm.state['program_counter'] - 1], indent=2) if vm.state['program_counter'] > 0 else "No steps executed yet"}
"""

    if suggestion:
        prompt += f"\nSuggestion for plan update: {suggestion}\n"

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

## 8. Available Tools for `calling` instruction
{tools_instruction_content}

-------------------------------

Now, let's update the plan.

**Output**:
1. Provide the complete updated plan in JSON format, ensuring it adheres to the VM specification.
2. Provide a summary of the changes made to the plan, including a diff with the previous plan.
    """

    return prompt


def get_should_update_plan_prompt(vm, suggestion):
    """
    Get the prompt for determining if the plan should be updated.
    """

    json_format = """
    {{
        "should_update": boolean,
        "explanation": string,
        "key_factors": [
            {{
                "factor": string,
                "impact": string
            }}
        ]
    }}
    """

    return f"""Today is {datetime.date.today().strftime("%Y-%m-%d")}
Analyze the current VM execution state and determine if the plan needs to be updated.

Goal:
{vm.state['goal']}

User Suggestion for plan update:
{suggestion}

Current Plan:
{json.dumps(vm.state['current_plan'], indent=2)}

Current Program Counter:
{vm.state['program_counter']}

Last Executed Step:
{json.dumps(vm.state['current_plan'][vm.state['program_counter'] - 1], indent=2) if vm.state['program_counter'] > 0 else "No steps executed yet"}

Current Variables:
{json.dumps(vm.get_all_variables(), indent=2)}

Evaluate the following aspects:
1. Goal Alignment: Is the current plan still effectively working towards the goal?
2. New Information: Have any variables changed in a way that affects the plan's validity?
3. Efficiency: Based on the current state, is there a more optimal approach to achieve the goal?
4. Potential Obstacles: Are there any foreseeable issues in the upcoming steps?
5. Completeness: Does the plan address all necessary aspects of the goal?
6. Adaptability: Can the current plan handle any new circumstances that have arisen?

MUST Provide your analysis in JSON format:
{json_format}

Set "should_update" to true if the plan requires modification, false otherwise.
In the "explanation", provide a concise rationale for your decision.
List the most significant factors influencing your decision in "key_factors",
including how each factor impacts the need for a plan update.

Ensure your response is thorough yet concise, focusing on the most critical aspects of the decision.
"""


def get_generate_plan_prompt(
    goal, vm_spec_content, tools_instruction_content, plan_example_content
):
    """
    Get the prompt for generating a plan.
    """
    return f"""Today is {datetime.date.today().strftime("%Y-%m-%d")}
Your task is to generate a detailed action plan to achieve the following goal:
Goal: {goal}

**MUST follow the Specification**:
{vm_spec_content}

## 8. Available Tools for `calling` instruction
{tools_instruction_content}

## 9. Example Plan
{plan_example_content}

-------------------------------

Now, let's generate the plan.

1. **Analyze the Request**:
   - Determine the primary intent behind the goal.
   - Identify any implicit requirements or necessary prerequisites.

2. **Break Down the Goal**:
   - Decompose the goal into smaller, manageable sub-goals or tasks.
   - Ensure each sub-goal is specific, actionable, and can be addressed with existing tools or data sources.
   - Identify dependencies between sub-goals to establish the correct execution order.

3. **Generate an Action Plan**:
   - For each sub-goal, create a corresponding action step to achieve it.
   - Ensure the plan follows the VM Specification.
   - Include a 'reasoning' step at the beginning of the plan that outlines the chain of thought and dependency analysis of the steps.
   - IMPORTANT: Always use tools within "calling" instructions. Never use tool functions directly in the plan.

4. **Tool Usage Guidelines**:
   - When using a tool, always wrap it in a "calling" instruction.
   - The "calling" instruction should have the following structure:
     ```json
     {{
       "seq_no": <unique_sequential_number>,
       "type": "calling",
       "parameters": {{
         "tool_name": "<tool_name>",
         "tool_params": {{
           <tool-specific parameters>
         }},
         "output_vars": [<list_of_output_variable_names>]
       }}
     }}
     ```
   - Ensure that the "tool_params" object contains all necessary parameters for the specific tool being called.

The final step of the plan must be assign the final output result to the 'final_answer' variable.
Please provide only the JSON array for the action plan without any additional text, explanations, or markdown. 
Ensure the JSON is properly formatted and encapsulated within a ```json code block.

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
    ```
"""


def get_step_update_prompt(
    vm, seq_no, vm_spec_content, tools_instruction_content, suggestion
):
    """
    Get the prompt for updating a step.
    """
    current_step = vm.state["current_plan"][seq_no]
    current_variables = json.dumps(vm.get_all_variables(), indent=2)

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
