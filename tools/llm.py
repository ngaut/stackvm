import logging
from typing import Optional
from queue import Queue
from datetime import datetime

from app.instructions.tools import tool
from app.config.settings import LLM_PROVIDER, FAST_LLM_MODEL
from app.services import LLMInterface

logger = logging.getLogger(__name__)


llm_client = LLMInterface(LLM_PROVIDER, FAST_LLM_MODEL)


@tool
def llm_generate(
    prompt: str,
    context: Optional[str] = None,
    response_format: Optional[str] = None,
    stream_queue: Optional[Queue] = None,
):
    """
    Generates a response using the Language Model (LLM).

    This tool must be used within a "calling" instruction in the plan.

    Arguments:
    - `prompt`: The prompt to provide to the LLM. Can be a direct string or a variable reference.
        - **Language Matching**: Write the prompt in the same language as the goal.
        - **Language Confirmation**: Append a sentence to confirm the desired language of the generated text:
            - *For English goals*: "Please ensure that the generated text uses English."
            - *For Chinese goals*: "请确保生成的文本使用中文。"
            - *For Japanese goals*: "Please ensure that the generated text uses Japanese."
    - `context` (optional): Additional context for the LLM. Can be a direct string or a variable reference.

    Output: The output format (text or JSON) depends on your instructions.
    - Text Response: If you ask for a text answer, let output_vars be an array containing one variable name. The entire text response will be stored under this variable.
    - JSON Response: If you instruct the LLM to respond in JSON format, let output_vars be an array containing variable names that match the keys in the JSON response. Each variable name corresponds to a key in the JSON object, and the value associated with each key is stored under the corresponding variable name.

    Example usage in a plan:
    ```json
    {
        "seq_no": 1,
        "type": "calling",
        "parameters": {
            "tool_name": "llm_generate",
            "tool_params": {
                "prompt": "Analyze the sales data and provide summary and insights, response a json object including keys ['summary', 'insights'].",
                "context": "${sales_data}"
            },
            "output_vars": ["summary", "insights"]
        }
    }
    ```

    Best practices:
    - Always use llm_generate within a "calling" instruction in your plan.
    - Use variable references (${variable_name}) when you need to include dynamic content from previous steps.
    """
    # Add current time to the prompt
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prompt = f"Current time: {current_time}\n\n{prompt}"

    if response_format:
        prompt += f"\n\n{response_format}"
    elif context is not None:
        prompt += """\n\nSome additional hints:
1. **Internal Data Usage**: Graph entities and relationships are internal data and should not be directly included in your response. You can use the information from graph entities and relationships to generate your answers, but do not mention them explicitly (e.g., avoid phrases like "entity xx" or "relationship yy").
2. **Referencing Sources**:
   - **Condition**: Only reference specific information if a source url is available.
   - **Action**: When referencing, include the corresponding `source_uri` link(s) clearly in your answer.
   - **Avoid**: Do not create or include any fabricated `source_uri` links.
   - **Formatting**: Ensure that all reference links are properly formatted to enable direct indexing to the original sources for further details.
"""

    if stream_queue:
        final_answer = ""
        response = llm_client.generate_stream(prompt, context)
        for chunk in response:
            final_answer += chunk
            stream_queue.put(chunk)
        return final_answer

    response = llm_client.generate(prompt, context)
    return response
