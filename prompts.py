import json

def get_plan_update_prompt(vm_state, vm_spec_content):
    return f"""Given the following goal, current state, execution point, and VM specification, generate an updated plan that forked from the current execution point.

Goal: {vm_state['goal']}
Current Variables: {json.dumps(vm_state['variables'], indent=2)}
Current Program Counter: {vm_state['program_counter']}
Current Plan: {json.dumps(vm_state['current_plan'], indent=2)}

Please provide a revised plan that:
1. Incorporates the current state and variables
2. Continues from the current program counter (step {vm_state['program_counter']}), only the new steps are generated.
3. Addresses any errors or issues in the current execution
4. Aims to complete the original goal
5. Follows the format specified in the VM specification

This is a forked plan, starting from the current execution point. Ensure the new plan seamlessly continues from where the current plan left off.

The VM specification is as follows:

{vm_spec_content}

Make sure the updated plan adheres to this specification.
"""

def get_should_update_plan_prompt(vm_state):
    return f"""
    Analyze the current VM execution state and determine if the plan needs to be updated.

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

    Provide your analysis in JSON format:
    {
        "should_update": boolean,
        "explanation": string,
        "key_factors": [
            {
                "factor": string,
                "impact": string
            }
        ]
    }

    Set "should_update" to true if the plan requires modification, false otherwise.
    In the "explanation", provide a concise rationale for your decision.
    List the most significant factors influencing your decision in "key_factors", 
    including how each factor impacts the need for a plan update.

    Ensure your response is thorough yet concise, focusing on the most critical aspects of the decision.
    """
def get_generate_plan_prompt(goal, vm_spec_content):
    return f"""You are an intelligent assistant designed to analyze user queries and retrieve information from a knowledge graph and a vector database multiple times. 
For the following goal, please:

1. Analyze the requester's intent and the requester's query:
   - Analyze and list the prerequisites of the query.
   - Analyze and list the assumptions of the query. 
   
2. Break Down query into sub-queries:
   - Each sub-query must be smaller, specific, retrievable with existing tools, and no further reasoning is required to achieve it.
   - Identify dependencies between sub-queries

3. Generate an Action Plan:
   - For each sub-query (Assumptions included), create a corresponding action step to achieve it.
   - Ensure the plan follows the format specified in the spec.md file.
   - Include a 'reasoning' step at the beginning of the plan that explains the chain of thoughts and provides a dependency analysis of the steps.

Goal: {goal}

The final step should assign the result to the 'result' variable.

the content of spec.md is:

{vm_spec_content}
"""
