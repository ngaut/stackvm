import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

import logging
import enum
import openai
import requests
import json
from pydantic import BaseModel, Field
from typing import Generator, Any, List, Dict
from dataclasses import dataclass
from app.llm.interface import LLMInterface
from app.config.settings import EVALUATION_LLM_PROVIDER, EVALUATION_LLM_MODEL
from app.core.plan.evaluator import evaulate_answer
from app.core.plan.optimizer import optimize_whole_plan

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

stackvm_host = os.getenv("STACKVM_HOST", None)
assert stackvm_host is not None, "STACKVM_HOST environment variable is not set."

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", None)
assert OPENAI_API_KEY is not None, "OPENAI_API_KEY environment variable is not set."

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

fc_llm = openai.OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
eval_llm = LLMInterface(EVALUATION_LLM_PROVIDER, EVALUATION_LLM_MODEL)


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


def update_plan(goal: str, metadata: dict, plan: str, suggestion: str | Dict):
    """
    Get the prompt for updating the plan.
    """
    user_instructions = f"""Important Requirements for Revising the Plan:

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
"""
    return optimize_whole_plan(
        eval_llm, goal, metadata, plan, suggestion, user_instructions
    )


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
                            eval_res = evaulate_answer(
                                eval_llm,
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
