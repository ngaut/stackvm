import logging
import enum
import openai
import requests
import json
import os
import datetime
from pydantic import BaseModel, Field
from typing import Generator, Any, List, Dict, Optional
from dataclasses import dataclass

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

stackvm_host = os.getenv("STACKVM_HOST", None)
assert stackvm_host is not None, "STACKVM_HOST environment variable is not set."

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", None)
assert OPENAI_API_KEY is not None, "OPENAI_API_KEY environment variable is not set."

fc_llm = openai.OpenAI(api_key=OPENAI_API_KEY)


def get_task_answer(task_id: str, branch_name: str) -> dict:
    """
    Retrieves the answer detail for a specific task and branch using the API.

    Args:
        task_id: The ID of the task.
        branch_name: The name of the branch.
        base_url: The base URL of the API.

    Returns:
        A dictionary containing the API response, or None if an error occurred.
    """
    url = f"{stackvm_host}/api/tasks/{task_id}/branches/{branch_name}/answer_detail"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        detail = response.json()
        state = (
            detail.get("vm_state").get("vm_state")
            if detail.get("vm_state") is not None
            else None
        )
        if state is not None:
            plan = state.get("current_plan", None)
            goal_completed = state.get("goal_completed", False)
            goal = state.get("goal", None)
            final_answer = None
            if state.get("variables", None) is not None:
                final_answer = state["variables"].get("final_answer", None)

            return {
                "goal": goal,
                "plan": plan,
                "goal_completed": goal_completed,
                "final_answer": final_answer,
                "metadata": detail.get("metadata"),
            }
    except requests.exceptions.RequestException as e:
        logger.error(f"Error during request: {e}", exc_info=True)
        raise e
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON response: {e}", exc_info=True)
        raise e


def execute_task_using_new_plan(task_id: str, new_plan: List[Dict[str, Any]]) -> dict:
    """
    Updates a task with a new suggestion and sets the task to be re-run from scratch.
    """
    url = f"{stackvm_host}/api/tasks/{task_id}/re_execute"

    if isinstance(new_plan, str):
        new_plan = json.loads(new_plan)

    payload = {
        "plan": new_plan,
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        if response.status_code == 400:
            raise ValueError("Missing required parameters")
        elif response.status_code == 404:
            raise ValueError(f"Task with ID {task_id} not found")
        elif response.status_code == 500:
            raise ValueError("Failed to re_execute task")
        else:
            raise e


def evaulate_task_answer(goal: str, metadata: dict, final_answer: str, plan: str):
    evaluation_prompt = f"""You are tasked with evaluating and improving the effectiveness of a problem-solving workflow. Below is a description of a Goal, a Plan used to address it, and the Final Answer generated. Your task is to evaluate the quality of the answer and diagnose whether the Plan sufficiently aligns with the Goal.

------------------------------------
KEY POINTS TO CONSIDER IN YOUR EVALUATION:
1. Deep Analysis of the User's Problem:
  - Does the Plan demonstrate a sufficient understanding of the user's overall background, constraints, and specific questions?
  - Has the Plan identified the critical context that shapes the user's goal (e.g., large data volumes, performance constraints, GC usage, version details, etc.)?

2. Instructions Context & Coverage:
  - For each instruction in the Plan (including steps like searching for relevant data or generating partial solutions), verify whether it explicitly or implicitly incorporates the "specific problem background + user's question."
  - Do the instructions effectively handle the sub-questions or concerns raised by the user? Are any key points missing or glossed over?

3. Verification of Problem Decomposition and Factual Information Retrieval for TiDB-Related Goals
  - Problem Decomposition - If the Goal is TiDB-related, verify whether the Plan has effectively broken down the Goal into distinct sub-questions.
  - Individual Retrieval Methods for Each Sub-Question - For each sub-question, verify wheter the plan has applied the following retrieval methods independently:
    - retrieve_knowledge_graph + vector_search: to fetch background knowledge or technical details relevant to TiDB.
    - llm_generate: after obtaining the above retrieval information, use it as the basis for reasoning and extracting the most relevant information.
  - Ensuring Relevance and Separation:
    - Confirm that each sub-question is handled separately, ensuring that the retrieval process targets the most relevant data for that specific sub-question.
    - Ensure that retrieval operations for different sub-questions are not combined, preventing the mixing of data across sub-questions.

4. Completeness of the Plan:
   • Does the Plan address all major aspects of the user's problem or goal?
   • Are there any unanswered questions or issues that the user might still have after following the Plan?

5. Cohesion of Plan Steps:
   • Assess whether the Plan's instructions flow logically from one step to the next, and whether they form a coherent end-to-end workflow.
   • Consider whether the Plan's approach to searching for data, filtering out irrelevant information, and eventually generating a final integrated solution is clearly articulated and consistent with the user's context.

When providing your evaluation, reference these points and also consider the following general guidelines:

- Direct Problem Resolution: The Plan and Final Answer should yield a clear, actionable solution or next step.
- Clarification of User Intent: If the Goal is unclear or missing details, verify if the Plan seeks clarification properly, clarification is enough for this kind of goa, no other process is needed.
- Unrelated to TiDB: If the Goal is not TiDB-related, ensure the Plan provides a polite response indicating the capability to assist with TiDB-related queries only.
- Providing Relevant Information: Ensure the solution or Plan steps remain focused on the user's needs, without extraneous or off-topic content.
- Maintaining Conversational Flow: The explanation or solution should guide the user logically from their question to the solution, smoothly transitioning between steps.

------------------------------------
YOUR OUTPUT FORMAT:
You must return a JSON object with the following keys:
1. "accept": Boolean value (true or false) indicating whether the Final Answer effectively resolves the Goal.
2. "answer_quality_assessment_explanation": A detailed explanation justifying why the final answer does or does not meet the goal, referencing any guidelines or key points above.
3. "plan_adjustment_suggestion": If "accept" is false, provide a comprehensive analysis of how the Plan could be improved to fully address the user's context and questions. Propose modifications or additional steps in detail.
4. "goal_classification": (Optional) A categorization of the goal type based on the guidelines (e.g., "Direct Problem Resolution", "Clarification Needed").

------------------------------------
EXAMPLE OUTPUT:
{{
  "accept": false,
  "answer_quality_assessment_explanation": "...",
  "plan_adjustment_suggestion": "...",
  "goal_classification": "Direct Problem Resolution"
}}

Below are the inputs for your evaluation:

## Goal
{goal}

## Supplementary goal information
{metadata.get('response_format')}

## Final Answer
{final_answer}

## Plan
{plan}

Now Let's think step by step! Do you best on this evaluation task!
"""

    response = fc_llm.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": evaluation_prompt},
        ],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


def update_plan(goal: str, metadata: dict, plan: str, suggestion: str | Dict):
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

Important Requirements for Revising the Plan:

1. Deeply Understand the User Context:
  - Revisit the user's specific problem background, constraints, and sub-questions.
  - Ensure the Plan explicitly incorporates these elements (e.g., large-scale backup, performance constraints, etc.).

2. Align with the Evaluation Feedback:
  - Identify all the key issues from the feedback (e.g., missing details, insufficient handling of user constraints, lack of clarity in sub-problems).
  - Adjust or add instructions to address these issues, ensuring each sub-problem or concern is resolved.

3. Proper Use of Tools for Searching and Information Filtering:
  - Include instructions that create precise queries reflecting the user's unique background + question.
  - If the Goal is TiDB-related, the Goal must be broken down in plan, and for each sub-question, used the following retrieval methods:
    - retrieve_knowledge_graph + vector_search: to fetch background knowledge or technical details relevant to TiDB.
    - llm_generate: after obtaining the above retrieval information, use it as the basis for reasoning and extracting the most relevant information.

4. Comprehensive Coverage of All User Questions:
  - Confirm that each instruction in the Plan contributes to solving one or more of the user's sub-questions.
  - Avoid repeating the same general statements; instead, detail how each step practically helps address the user's goal.

5. Cohesion and Executability:
  - Check that the sequence of instructions (seq_no) flows logically and forms a coherent, end-to-end solution.
  - Pay attention to the final assignment to “final_answer”, ensuring it incorporates all relevant information from the prior steps.

------------------------------------
As the evaluating feedback said, the previous plan has been rejected or found insufficient in fully addressing the goal. Please revise the previous plan based on these guidelines and the evaluation feedback.

Make sure the updated plan adheres to the Executable Plan Specifications:

```

1. Overview

- Functionality: Executes plans composed of sequential instructions, each performing specific operations and interacting with a variable store.
-	Key Features:
  - Variable Store: A key-value store for storing and accessing variables by name.
  - Instruction Execution: Executes instructions in order based on seq_no, with support for conditional jumps.

2. Instruction Format

Each instruction is a JSON object with:
- seq_no: Unique, auto-increment integer starting from 0.
- type: Instruction type (assign, jmp, calling, reasoning).
- parameters: Object containing necessary parameters for the instruction.

3. Supported Instructions

3.1 assign
- Purpose: Assign values to variables.
- Parameters: Key-value pairs where keys are variable names and values are direct values or variable references.

3.2 jmp
- Purpose: Conditional or unconditional jump to a specified seq_no.
- Parameters:
  - Conditional Jump:
    - condition_prompt (optional): Prompt to evaluate condition.
    - jump_if_true: seq_no to jump if condition is true.
    - jump_if_false (optional): seq_no to jump if condition is false.
  - Unconditional Jump:
    - target_seq: seq_no to jump to.

3.3 calling
- Purpose: Invoke a tool or function.
- Parameters:
  - tool_name: Name of the tool to call.
	- tool_params: Arguments for the tool, can include variable references.
	- output_vars (optional): Variables to store the tool's output.

3.4 reasoning
- Purpose: Provide detailed reasoning and analysis.
- Parameters:
  - chain_of_thoughts: Detailed reasoning process.
  - dependency_analysis: Description of dependencies between steps.

4. Parameters and Variable References
- Variable Reference Format: Dynamic values based on previous steps, format: ${{variable_name}}
- Direct Values: Fixed, known values.

5. Plan Structure
  - Sequential Execution: Instructions execute in order based on seq_no.
  - Control Flow: Use jmp for conditional jumps and loops.

6. Supported Tools for Calling Instructions (other tool is unavailble)
  - llm_generate: Generates text content based on prompts and context.
  - vector_search: Performs vector-based searches to retrieve relevant information.
  - retrieve_knowledge_graph: Retrieves structured data from a knowledge graph.

7. Best Practices
  -	Sequence Numbering: Ensure seq_no values are unique and sequential.
  - Variable Naming: Use descriptive names for clarity and maintainability.
  - Final Answer: The last instruction must assign to the variable final_answer.
	- Language Consistency:
    - All instructions contributing to final_answer must be in the same language as the goal.
    - Ensure variable content matches the target language.
  - For each query, use both retrieve_knowledge_graph and vector_search to search information, then use llm_generate to summarize the relevant information for the query.
```

-------------------------------

Now, let's think step by step, and revise the plan.
1. Incorporate the Evaluation Feedback by mapping each identified issue to a concrete fix in your instructions.
2. Ensure your revised Plan has all instructions needed to search, filter, and integrate relevant data before generating the final, comprehensive answer.

**Output**:
1. **Provide the complete updated plan in JSON format**, ensuring it fully complies with the executable plan specification. **Within the ```json``` block, do not use any additional triple backticks (` ``` `) to prevent parsing issues.**
2. **Provide a summary of the changes made to the plan**, including a clear diff comparing the previous plan with the updated plan."""

    llm_response = fc_llm.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": updated_prompt},
        ],
        temperature=0,
    )

    plan = llm_response.choices[0].message.content.strip()

    return plan


class EventType(str, enum.Enum):
    LLM_CONTENT_STREAMING = "LLM_CONTENT_STREAMING"
    TOOL_CALL = "TOOL_CALL"
    TOOL_CALL_RESPONSE = "TOOL_CALL_RESPONSE"
    FINISHED = "FINISHED"
    ERROR = "ERROR"


@dataclass
class ChatEvent:
    event_type: EventType
    payload: str | dict | None = None

    def encode(self, charset) -> bytes:
        body = self.payload
        body = json.dumps(body, separators=(",", ":"))
        return f"{self.event_type.value}:{body}\n".encode(charset)


class evaulate_task_answer_object(BaseModel):
    """
    Evaluates the final answer and its plan for a specific task.

    Args:
        task_id: The ID of the task.
        branch_name: The name of the branch, default to 'main'.

    Returns a JSON object with keys.
        accept: False/True,
        answer_quality_assessment_explaination: ...,
        plan_adjustment_suggestion: ...
    """

    task_id: str = Field(description=("The ID of the task."))
    branch_name: str = Field(
        description=(
            "The name of the branch. The default is `main` if not specified by the user."
        )
    )


class execute_task_using_new_plan_object(BaseModel):
    """
    Retrieves the answer tail for a specific task and branch.

    Args:
        task_id: The ID of the task.
        new_plan: The new plan to execute, it must be a full and complete plan.

    Returns a JSON object with keys.
        completed: Whether the task is completed.
        final_answer: The final answer for the task after executing the new plan.
        branch_name: The name of the branch that was executed.
    """

    task_id: str = Field(description=("The ID of the task."))
    new_plan: str = Field(description=("The new plan to execute."))


system_instruction = """Your primary mission is to evaluate whether a task's final answer successfully solves the problem stated in the goal. You should focus on the practical effectiveness of the solution rather than the plan's structure.

Your workflow is as follows:

1. **Gather Task Information**
   - Ask the user for the `task_id` and `branch_name` of the task they wish to evaluate.

2. **Retrieve and Evaluate Task Answer**
   - Use the `evaulate_task_answer_object` tool to perform a systematic evaluation for a task with following functionalities:
     - Whether the final answer effectively resolves the goal
     - The quality of the current plan
     - Potential improvements needed

3. **Review Evaluation Results**
   - Based on the evaluation tool's output:
     - If accepted (accept: true):
       - Confirm to the user that the solution is effective
       - No further action needed

     - If not accepted (accept: false):
       - Share the detailed assessment explanation with the user
       - Review the suggested plan adjustments from the evaluation

4. **Review the revised plan and Get  User Confirmation**
   - If the solution is ineffective:
     - Present the suggested plan adjustments from the evaluation
     - Present the new plan to the user and wait for their confirmation
     - Only proceed with execution after receiving explicit user approval
     - If the user rejects the plan, ask for their feedback and create a revised plan
   - Requirements for the New Plan:
        - Modify only the necessary parts of the original plan.
        - Incorporate the suggestions from the evaluation feedback.
        - Ensure the revised plan is coherent and aligned with the goal.
        - **Information Retrieval Enhancement:** When performing information retrieval, use both retrieve_knowledge_graph and vector_search to ensure the richness of retrieved information. Note that knowledge graph search is a powerful retrieval function.
        - **Selective Plan Modification:** If parts of the original answer meet the expected outcomes, identify and retain the corresponding information retrieval steps from the original plan. This approach ensures that only necessary modifications are made, preventing unpredictable performance fluctuations in the revised plan.
        - Format the new plan as a JSON object with the same structure as the original
        - Ensure the new plan starts with a reasoning step at seq_no 0, and reasoning instruction can only be used in the first step of the plan.

5. **Execute and Verify (Only After User Confirmation)**
   - Before executing the new plan, ensure the user has approved the changes
   - Use `execute_task_using_new_plan` to implement the approved plan

Remember:
- Always use the evaluation tool for systematic assessment
- Never execute a new plan without explicit user confirmation
- Be ready to revise the plan based on user feedback
- The new plan must maintain the required JSON structure and include a reasoning step
"""


class PlanOptimizationService:
    def __init__(self):
        self.tools = [
            openai.pydantic_function_tool(execute_task_using_new_plan_object),
            openai.pydantic_function_tool(evaulate_task_answer_object),
        ]
        self._system_message = [{"role": "system", "content": system_instruction}]
        self._message_history = []  # Store all conversation history

    def chat(self, message: str) -> Generator[ChatEvent, None, None]:
        """
        Process a single message and maintain conversation history.
        Now accepts a string message instead of message list.
        """
        if not message:
            yield ChatEvent(event_type=EventType.ERROR, payload="No message provided")
            return

        # Create message object
        user_message = {"role": "user", "content": message}
        # Add user message to history
        self._message_history.append(user_message)

        while True:
            logger.debug("LLM request %s", self._message_history)
            response = fc_llm.chat.completions.create(
                model="gpt-4o",
                messages=(self._system_message + self._message_history),
                tools=self.tools,
            )

            if response.choices[0].message.tool_calls is None:
                assistant_message = {
                    "role": "assistant",
                    "content": response.choices[0].message.content,
                }
                self._message_history.append(assistant_message)
                yield ChatEvent(
                    event_type=EventType.FINISHED,
                    payload=assistant_message,
                )
                return

            try:
                tool_call = response.choices[0].message.tool_calls[0]
                tool_call_message = response.choices[0].message.model_dump()
                self._message_history.append(tool_call_message)
                yield ChatEvent(
                    event_type=EventType.TOOL_CALL, payload=tool_call_message
                )

                for tool_call in response.choices[0].message.tool_calls:
                    try:
                        if (
                            tool_call.function.name
                            == "execute_task_using_new_plan_object"
                        ):
                            args = json.loads(tool_call.function.arguments)
                            tool_call_result = execute_task_using_new_plan(**args)
                        elif tool_call.function.name == "evaulate_task_answer_object":
                            args = json.loads(tool_call.function.arguments)
                            answer_detail = get_task_answer(**args)
                            eval_res = evaulate_task_answer(
                                answer_detail["goal"],
                                answer_detail["metadata"],
                                answer_detail["final_answer"],
                                answer_detail["plan"],
                            )

                            # eval_res + answer_detail
                            tool_call_result = {
                                "evaluation_result": eval_res,
                                **answer_detail,
                            }
                            self._message_history = self._message_history[
                                -10:
                            ]  # Keep only the last 10 message
                        else:
                            raise ValueError(
                                f"Unknown tool call: {tool_call.function.name}"
                            )

                        tool_call_result_message = {
                            "role": "tool",
                            "content": json.dumps(tool_call_result),
                            "tool_call_id": tool_call.id,
                        }
                    except Exception as e:
                        logger.error("Error processing tool call: %s", e, exc_info=True)
                        tool_call_result_message = {
                            "role": "tool",
                            "content": f"An error occurred while processing the request: {e}",
                            "tool_call_id": tool_call.id,
                        }

                    self._message_history.append(tool_call_result_message)
                    yield ChatEvent(
                        event_type=EventType.TOOL_CALL_RESPONSE,
                        payload=tool_call_result_message,
                    )

            except Exception as e:
                logger.error("Error processing tool call: %s", e, exc_info=True)
                yield ChatEvent(
                    event_type=EventType.ERROR,
                    payload=f"An error occurred while processing the request: {e}",
                )


def format_json_output(obj, indent=2):
    """
    Format JSON output with proper handling of Unicode characters.

    Args:
        obj: The object to format (dict, list, or string)
        indent: Number of spaces for indentation

    Returns:
        str: Formatted string with proper Unicode rendering
    """
    if isinstance(obj, str):
        try:
            # Try to parse if it's a JSON string
            obj = json.loads(obj)
        except:
            # If it's not JSON, return as is
            return obj

    return json.dumps(obj, indent=indent, ensure_ascii=False)


async def main():
    """
    Main function to run the CLI interface for PlanOptimizationService.
    Provides an interactive chat experience with the service.
    """
    service = PlanOptimizationService()
    print("Welcome to Plan Optimization Chat System!")
    print("Type 'quit' or 'exit' to end the program\n")

    while True:
        # Get user input
        user_input = input("You: ").strip()

        # Check for exit command
        if user_input.lower() in ["quit", "exit"]:
            print("Goodbye!")
            break

        # Get service response
        try:
            for event in service.chat(user_input):
                if event.event_type == EventType.FINISHED:
                    print("\nAssistant: ", format_json_output(event.payload["content"]))
                elif event.event_type == EventType.TOOL_CALL:
                    print("\n[System] Calling tool...")
                    # The payload contains the full message including tool_calls
                    for tool_call in event.payload.get("tool_calls", []):
                        if isinstance(tool_call, dict):
                            name = tool_call.get("function", {}).get("name")
                            args = tool_call.get("function", {}).get("arguments")
                        else:
                            # If tool_call is an object
                            name = tool_call.function.name
                            args = tool_call.function.arguments
                        print(f"Tool name: {name}")
                        print(f"Arguments: {format_json_output(args)}\n")
                elif event.event_type == EventType.TOOL_CALL_RESPONSE:
                    print("[System] Tool call result:")
                    result = json.loads(event.payload["content"])
                    print(format_json_output(result))
                elif event.event_type == EventType.ERROR:
                    print("\n[Error]", format_json_output(event.payload))
                    break
        except Exception as e:
            print(f"\n[Error] An exception occurred: {str(e)}")
            import traceback

            traceback.print_exc()  # This will help debug issues
            raise e


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
