import json
from typing import Dict, List


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
