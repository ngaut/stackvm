import json

def get_plan_update_prompt(vm_state, vm_spec_content):
    return f"""Given the following goal, current state, execution point, and VM specification, generate an updated plan that integrates improvements and addresses any identified issues from the current execution point.

**Goal**: {vm_state['goal']}
**Current Variables**: {json.dumps(vm_state['variables'], indent=2)}
**Current Program Counter**: {vm_state['program_counter']}
**Current Plan**: {json.dumps(vm_state['current_plan'], indent=2)}

**Execution Context**:
- **Last Executed Step**: {json.dumps(vm_state['current_plan'][vm_state['program_counter'] - 1], indent=2) if vm_state['program_counter'] > 0 else "No steps executed yet"}
- **Current Errors/Issues**: {json.dumps(vm_state.get('errors', []), indent=2)}

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
   - Remove or adjust subsequent steps from the original plan only if they are rendered obsolete or suboptimal by the updates.
   - Make sure the updated plan is not the same as Current Plan.

4. **Adhere to VM Specification**:
   - Ensure that the revised plan complies with the provided VM specification in format and structure.

**Guidelines for the Updated Plan**:
- **Consistency**: The format and structure of the plan should remain consistent with the original, as specified in the VM specification.
- **Completeness**: Provide a complete merged plan that includes all necessary steps from the beginning to the end.
- **Clarity**: Ensure that each step is clearly defined and actionable.

**VM Specification**:
{vm_spec_content}

**Output**:
Provide the complete updated plan in JSON format, ensuring it adheres to the VM specification. The updated plan should effectively address any identified issues and continue execution towards the goal without introducing redundancy.

"""



def get_should_update_plan_prompt(vm_state):
    json_format = '''
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
    '''
    
    return f"""Analyze the current VM execution state and determine if the plan needs to be updated.

    Goal: {vm_state['goal']}
    Current Variables: {json.dumps(vm_state['variables'], indent=2)}
    Current Program Counter: {vm_state['program_counter']}
    Current Plan: {json.dumps(vm_state['current_plan'], indent=2)}
    Last Executed Step: {json.dumps(vm_state['current_plan'][vm_state['program_counter'] - 1], indent=2) if vm_state['program_counter'] > 0 else "No steps executed yet"}

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


def get_generate_plan_prompt(goal, vm_spec_content):
    return f"""You are an intelligent assistant designed to analyze user queries and retrieve information from a knowledge graph and a vector database multiple times. 
For the following goal, please:

1. **Analyze the Request**:
   - Determine the primary intent behind the goal.
   - Identify any implicit requirements or necessary prerequisites.

2. **Break Down the Goal**:
   - Decompose the goal into smaller, manageable sub-goals or tasks.
   - Ensure each sub-goal is specific, actionable, and can be addressed with existing tools or data sources.
   - Identify dependencies between sub-goals to establish the correct execution order.

3. **Generate an Action Plan**:
   - For each sub-goal, create a corresponding action step to achieve it.
   - Ensure the plan follows the format specified in the `spec.md` file.
   - Include a 'reasoning' step at the beginning of the plan that outlines the chain of thought and dependency analysis of the steps.

Goal: {goal}

The final step should assign the result to the 'result' variable.

The content of `spec.md` is:

{vm_spec_content}
"""

