import json
import datetime


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

**Note**: Examples are to provide the ideas and examples for solving similar problems. Please do not use tools that appear in the example but do not appear in Available Tools for `calling` instruction. You can find more suitable tools in Available Tools for `calling` instruction to achieve the goal.

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
   - For calling instruction, Only select tools listed in the "Available Tools" section. Using tools outside this list will cause the plan to fail.
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

where <think> is your detailed reasoning process in text format and the JSON array inside the answer is a valid plan.
"""
