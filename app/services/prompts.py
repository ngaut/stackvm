import json
import datetime
from typing import Dict, List


def get_plan_update_prompt(
    vm, vm_spec_content, tools_instruction_content, suggestion, key_factors=None
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
    goal,
    vm_spec_content,
    tools_instruction_content,
    plan_example_content,
    plan_approach,
):
    """
    Get the prompt for generating a plan.
    """

    return f"""Today is {datetime.date.today().strftime("%Y-%m-%d")}
Your task is to generate a detailed action plan to achieve the following goal:
Goal: {goal}

**MUST follow the Specification**:
{vm_spec_content}

## 9. Available Tools for `calling` instruction
{tools_instruction_content}

## 10. Example: Here are an example how to handle a similar task.

### The approach

{plan_approach}

###  Plan Example

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
   - For calling instruction, Only select tools listed in the “Available Tools” section. Using tools outside this list will cause the plan to fail.
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


def get_label_classification_prompt(task_goal: str, labels_tree: List[Dict]) -> str:
    """
    Generates an enhanced prompt for the LLM to classify the task goal into a label path with descriptions.

    Args:
        task_goal (str): The goal of the task.
        labels_tree (dict): The current labels tree with label descriptions.

    Returns:
        str: The generated prompt.
    """

    # Convert the labels tree to a JSON string with indentation for readability
    labels_tree_json = json.dumps(labels_tree, indent=4, ensure_ascii=False)

    # Construct the prompt
    prompt = f"""Your task is to create a tree-structured tagging system for classifying user tasks. The system starts from the root node and refines layer by layer; concepts closer to the root node are more abstract and higher-level. This design allows the system to be highly flexible and scalable, capable of continuous expansion and maintenance as data increases.

## Current Labels Tree

```json
{labels_tree_json}
```

## Instructions

1. Category Matching Priority:
   - Always prioritize matching with existing feature/topic specific categories first
   - Match with existing leaf nodes before considering parent nodes
   - Only consider task complexity-based categories (like "Complex Task Planning") when the task is truly about planning or analysis, not when it's about specific features
   - Use label descriptions to better understand the scope and intent of each category

2. Intent Analysis:
   - Identify key technical terms and concepts in the task
   - Determine if it's about:
     * Specific feature/component (e.g., TiCDC, TiKV, etc.)
     * Usage guidance
     * Troubleshooting
     * Research/Analysis
     * Development planning
   - For feature-specific questions, map to corresponding feature category regardless of complexity
   - Compare task intent with label descriptions for better matching

3. Classification Process:
   - Start from root node
   - At each level, select the most specific category that matches the task content
   - Consider both label names and their descriptions when making decisions
   - If multiple categories seem applicable:
     * Prioritize feature/component specific categories over general categories
     * Choose the category that matches the main subject matter, not the format or complexity
     * Use descriptions to break ties between similar categories

4. Validation Rules:
   - Does the selected path lead to the most specific applicable category?
   - Is the classification based on what the task is about rather than how complex it is?
   - For feature-specific tasks, is it classified under the corresponding feature category?
   - Do the selected labels' descriptions align well with the task content?

5. Examples:

Good Classification:

Task: "How does TiCDC handle Resolved TS?"
Correct Path: [
    {{
        "label": "Basic Knowledge",
        "description": "Fundamental concepts and knowledge about database features and components"
    }},
    {{
        "label": "Feature Support",
        "description": "Specific database features and their functionalities"
    }},
    {{
        "label": "TiCDC Resolved TS",
        "description": "Understanding and implementation of Resolved Timestamp in TiCDC"
    }}
]
Reason: Directly about TiCDC Resolved TS feature, descriptions match the task intent

Bad Classification:

Task: "How does TiCDC handle Resolved TS?"
Wrong Path: [
    {{
        "label": "Complex Task Planning",
        "description": "Planning and coordination of complex technical tasks"
    }},
    {{
        "label": "Research & Analysis",
        "description": "In-depth research and technical analysis of problems"
    }}
]
Reason: Though technical in nature, it's primarily about a specific feature (TiCDC Resolved TS)


## Task Goal

"{task_goal}"

Response Format:
Return the label path as a JSON array of objects containing both label names and descriptions, for example:

```json
[
    {{
        "label": "Label 1",
        "description": "Description of Label 1"
    }},
    {{
        "label": "Label 2",
        "description": "Description of Label 2"
    }}
]
```

"""

    return prompt


def get_label_classification_prompt_wo_description(
    task_goal: str, labels_tree: List[Dict], tasks: List[Dict]
) -> str:
    """
    Generates an enhanced prompt for the LLM to classify the task goal into a label path without descriptions.

    Args:
        task_goal (str): The goal of the task.
        labels_tree (dict): The current labels tree with label descriptions.

    Returns:
        str: The generated prompt.
    """

    # Convert the labels tree to a JSON string with indentation for readability
    labels_tree_json = json.dumps(labels_tree, indent=4, ensure_ascii=False)
    tasks_json = json.dumps(tasks, indent=4, ensure_ascii=False)

    # Construct the prompt
    prompt = f"""Your task is to create a tree-structured tagging system for classifying user tasks. The system starts from the root node and refines layer by layer; concepts closer to the root node are more abstract and higher-level. This design allows the system to be highly flexible and scalable, capable of continuous expansion and maintenance as data increases.

## Current Labels Tree

```json
{labels_tree_json}
```

## Instructions

1. Category Matching Priority:
   - Specific Over General: Always prioritize matching with existing feature/topic-specific categories first.
   - Leaf Nodes First: Match with existing leaf nodes before considering parent nodes.
   - Task Complexity: Only consider task complexity-based categories (like "Complex Task Planning") when the task is truly about planning or analysis, not when it's about specific features
   - Use Descriptions: Utilize label descriptions to better understand the scope and intent of each category.
    - Ambiguous Queries: Assign to “Other Topics” for tasks that are ambiguous, or do not fit into specific categories.

2. Intent Analysis:
   - Identify key technical terms and concepts in the task
   - Determine if it's about:
     * Specific feature/component (e.g., TiCDC, TiKV, etc.)
     * Usage guidance
     * Troubleshooting
     * Research/Analysis
     * Development planning
     * ambiguous inquiries
   - For feature-specific questions, map to corresponding feature category regardless of complexity
   - Compare task intent with label descriptions for better matching

3. Classification Process:
   - Start from root node
   - At each level, select the most specific category that matches the task content
   - Consider both label names and their descriptions when making decisions
   - If multiple categories seem applicable:
     * Prioritize feature/component specific categories over general categories
     * Use descriptions to break ties between similar categories

4. Validation Rules:
   - Does the selected path lead to the most specific applicable category?
   - Is the classification based on what the task is about rather than how complex it is?
   - For feature-specific tasks, is it classified under the corresponding feature category?
   - Do the selected labels' descriptions align well with the task content?

5. Examples:

Good Classification:

Task: "How does TiCDC handle Resolved TS?"
Correct Path: ["Basic Knowledge", "Feature Support", "TiCDC Resolved TS"]
Reason: This question can be directly answered using the feature introduction document for TiCDC Resolved TS.

Bad Classification:

Task: "How does TiCDC handle Resolved TS?"
Wrong Path: ["Complex Task Planning", "Research & Analysis", "Technical Design"]
Reason: This question does not require complex research or involve multiple aspects. It is specific to understanding a single feature, making the “Complex Task Planning” category unnecessary.

Task: "What is this for?"
Wrong Path: ["Basic Knowledge", "Feature Support"]
Reason: The task is too ambiguous to be classified under a specific feature or category. Assign it to “Other Topics” instead.

## Task Related to Labels

{tasks_json}

## Task Goal

{task_goal}

Response Format:
Return the label path as a JSON array of labels, for example:

```json
[
    "Label 1",
    "Label 2"
]
```

"""

    return prompt


def get_best_pratices_prompt(
    label_path: str,
    formatted_task_plan: str,
) -> str:

    return f"""Background:

    You are provided with a series of task plans related to the topic: {label_path}. Each task plan outlines a method for addressing specific user tasks within this topic. Your goal is to analyze these plans to extract the underlying best practices and planning schemas that can be applied to similar tasks.

    Your Task:

    - Analyze the following task plans to identify common patterns, strategies, and methodologies used to solve tasks in the {label_path} category.
    - Summarize the best practices for planning and executing these tasks, focusing on efficiency and effectiveness.
    - Identify the meta-thinking and planning schemas that are unique to this type of task.
    - Provide a clear and concise analysis that can guide others in approaching and solving similar tasks.

    Instructions:

    1. Review Each Task Plan Carefully:
    - Examine the sequence of steps (seq_no) and the types of actions taken (type), such as reasoning, calling tools, conditional jumps, and assignments.
    - Note the tools used (e.g., retrieve_knowledge_graph, vector_search, llm_generate) and their purposes.

    2. Identify Common Patterns and Best Practices:
    - Look for recurring strategies in how the tasks are approached and solved.
    - Pay attention to how information is gathered, processed, and synthesized.

    3. Extract Meta-Thinking and Planning Schemas:
    - Determine the underlying principles that guide the planning of these tasks.
    - Understand how decisions are made regarding tool selection, conditional logic, and information synthesis.

    4. Focus on Efficiency and Effectiveness:
    - Highlight methods that streamline the task-solving process.
    - Emphasize practices that lead to accurate and comprehensive answers with minimal steps.

    5. Provide a Concise Summary:
    - Articulate the key best practices and planning schemas.
    - Ensure the summary is clear, actionable, and applicable to similar tasks.

    Expected Output:

    A clear and concise analysis that summarizes the best practices, meta-thinking, and planning schemas for tasks in the {label_path} category. The analysis should help others understand how to efficiently and effectively plan and execute similar tasks.


    Task Plans:

    {formatted_task_plan}

    """