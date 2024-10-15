import json
import datetime


def get_plan_update_prompt(vm, vm_spec_content, tools_instruction_content, explanation=None, key_factors=None):
    prompt = f"""Today is {datetime.date.today().strftime("%Y-%m-%d")}
Analyze the current VM execution state and update the plan.

    Goal: {vm.state['goal']}
    Current Variables: {json.dumps(vm.get_all_variables(), indent=2)}
    Current Program Counter: {vm.state['program_counter']}
    Current Plan: {json.dumps(vm.state['current_plan'], indent=2)}
    Last Executed Step: {json.dumps(vm.state['current_plan'][vm.state['program_counter'] - 1], indent=2) if vm.state['program_counter'] > 0 else "No steps executed yet"}
    """

    if explanation:
        prompt += f"\n    Reason for plan update: {explanation}\n"

    if key_factors:
        prompt += f"\n    Key factors influencing the update:\n    {json.dumps(key_factors, indent=2)}\n"

    prompt += f"""
    Evaluate the following aspects:
    1. Goal Alignment: Is the current plan still effectively working towards the goal?
    2. New Information: Have any variables changed in a way that affects the plan's validity?
    3. Efficiency: Based on the current state, is there a more optimal approach to achieve the goal?
    4. Potential Obstacles: Are there any foreseeable issues in the upcoming steps?
    5. Completeness: Does the plan address all necessary aspects of the goal?
    6. Adaptability: Can the current plan handle any new circumstances that have arisen?

**Instructions**:
1. **Analyze and Identify Issues**:
   - Review the current state and the last executed step.
   - Identify any errors, obstacles, or inefficiencies that are hindering progress towards the goal.

2. **Propose Solutions**:
   - Suggest modifications to existing steps to resolve identified issues.
   - Introduce new steps or action types if necessary to overcome obstacles.
   - Ensure that each modification or addition directly contributes to achieving the goal.

3. **Merge with Original Plan**:
   - Integrate proposed changes seamlessly into the original plan starting from the current program counter.
   - Preserve all steps prior to the current program counter without alteration.

4. **Adhere to VM Specification**:
   - Ensure that the revised plan complies with the provided VM specification in format and structure.

5. **Avoid Redundancy**:
   - Do not generate an identical plan. Ensure that the updated plan includes at least some meaningful changes to improve upon the original.

**Guidelines for the Updated Plan**:
- **Consistency**: The format and structure of the plan should remain consistent with the original, as specified in the VM specification.
- **Completeness**: Provide a complete merged plan that includes all necessary steps from the beginning to the end.
- **Clarity**: Ensure that each step is clearly defined and actionable.

**VM Specification**:
{vm_spec_content}

**Tools Instruction**:
{tools_instruction_content}

**Output**:
Provide the complete updated plan in JSON format, ensuring it adheres to the VM specification. The updated plan should effectively address any identified issues and continue execution towards the goal without introducing redundancy.
After the updated plan, provide a summary of the changes made to the plan and the diff with the previous plan.
    """

    return prompt


def get_should_update_plan_prompt(vm):
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

    Goal: {vm.state['goal']}
    Current Variables: {json.dumps(vm.get_all_variables(), indent=2)}
    Current Program Counter: {vm.state['program_counter']}
    Current Plan: {json.dumps(vm.state['current_plan'], indent=2)}
    Last Executed Step: {json.dumps(vm.state['current_plan'][vm.state['program_counter'] - 1], indent=2) if vm.state['program_counter'] > 0 else "No steps executed yet"}

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


def get_generate_plan_prompt(goal, vm_spec_content, tools_instruction_content, plan_example_content):
    return f"""Today is {datetime.date.today().strftime("%Y-%m-%d")}
Your task is to generate a detailed action plan to achieve the following goal:
Goal: {goal}

**VM Specification**:
{vm_spec_content}

**Tools Instruction**:
{tools_instruction_content}

**Plan Example**:
{plan_example_content}

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


def get_step_update_prompt(vm, seq_no, suggestion):
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

**Instructions**:
1. Analyze the current step, the provided suggestion, and the current VM variables.
2. Modify the step to incorporate the suggestion while ensuring it aligns with the overall goal and plan structure.
3. Ensure the updated step is consistent with the VM's current state and does not introduce redundancy.

**Output**:
Provide only the updated step in JSON format.
"""
