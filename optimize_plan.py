import logging
import enum
import openai
import requests
import json
import os
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


def get_task_branch_answer_detail(task_id: str, branch_name: str) -> dict:
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
        state = detail.get("vm_state")
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
            }
    except requests.exceptions.RequestException as e:
        logger.error(f"Error during request: {e}", exc_info=True)
        raise e
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON response: {e}", exc_info=True)
        raise e


def re_execute_task(task_id: str, new_plan: List[Dict[str, Any]]) -> dict:
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


class MessageRole(str, enum.Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    additional_kwargs: dict[str, Any] = {}


class get_task_answer(BaseModel):
    """
    Retrieves the answer tail for a specific task and branch.

    Args:
        task_id: The ID of the task.
        branch_name: The name of the branch.

    Returns a JSON object with keys.
        goal: The goal of the task.
        plan: The plan for the task.
        goal_completed: Whether the goal is completed.
        final_answer: The final answer for the task.
    """

    task_id: str = Field(description=("The ID of the task."))
    branch_name: str = Field(
        description=("The specific of the branch, default to main.")
    )


class execute_task_using_new_plan(BaseModel):
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
   - Ask the user for the `task_id` and `branch_main` of the task they wish to evaluate.

2. **Retrieve and Analyze Task Answer**
   - Use the `get_task_answer` tool to fetch the task details
   - Focus on two key elements:
     - The original goal: What problem needs to be solved?
     - The final answer: Does it actually solve this problem?
     - The plan: What parts of the plan need to be modified to improve the final answer?

3. **Evaluate Solution Effectiveness**
   - Your primary evaluation should answer: "Does the final answer solve the problem stated in the goal?"
   - Consider:
     - Completeness: Does it address all aspects of the goal?
     - Correctness: Is the solution accurate and valid?
     - Relevance: Does it directly address the goal without unnecessary elements?
   
   Your evaluation should result in one of two outcomes:
   - **If the Solution is Effective**: 
     - Confirm that the final answer solves the goal
     - No plan modifications needed
   
   - **If the Solution is Ineffective**:
     - Clearly explain why the final answer fails to solve the goal
     - Identify specific missing elements or incorrect solutions
     - Suggest focused plan modifications that directly target these gaps

4. **Plan Modification and User Confirmation**
   - If the solution is ineffective:
     - Create a new plan that specifically targets the identified gaps
     - Present the new plan to the user and wait for their confirmation
     - Only proceed with execution after receiving explicit user approval
     - If the user rejects the plan, ask for their feedback and create a revised plan
   - The new plan requirements:
     - The new plan should be with modifications to address the identified gaps.
     - The new plan should be a JSON object with the same structure as the original plan.
     - The new plan should start with a reasoning step at seq_no 0 to explain the whole new plan.

5. **Execute and Verify (Only After User Confirmation)**
   - Use `execute_task_using_new_plan` to implement the approved plan
   - Evaluate the new final answer with the same focus on solution effectiveness

Remember:
- Always prioritize practical problem-solving over plan complexity
- Focus on whether the final answer works, not just whether it looks good
- Never execute a new plan without explicit user confirmation
- Be ready to revise the plan based on user feedback
"""


class PlanOptimizationService:
    def __init__(self):
        self.tools = [
            openai.pydantic_function_tool(get_task_answer),
            openai.pydantic_function_tool(execute_task_using_new_plan),
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
                model="gpt-4",
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
                    if tool_call.function.name == "get_task_answer":
                        args = json.loads(tool_call.function.arguments)
                        tool_call_result = get_task_branch_answer_detail(**args)
                        self._message_history = self._message_history[
                            -10:
                        ]  # Keep only the last 10 messages
                    elif tool_call.function.name == "execute_task_using_new_plan":
                        args = json.loads(tool_call.function.arguments)
                        tool_call_result = re_execute_task(**args)
                    else:
                        raise ValueError(
                            f"Unknown tool call: {tool_call.function.name}"
                        )

                    tool_call_result_message = {
                        "role": "tool",
                        "content": json.dumps(tool_call_result),
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
