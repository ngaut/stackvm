import os
import logging
from flask import Flask
import argparse
from datetime import datetime
from typing import Optional

from app.controller.api_routes import api_blueprint
from app.controller.engine import run_vm_with_goal
from app.config.settings import GIT_REPO_PATH, LLM_PROVIDER, LLM_MODEL, OPENAI_API_KEY, OLLAMA_BASE_URL
from app.services import PlanExecutionVM
from app.services import LLMInterface
from app.instructions import global_tools_hub, tool

# Initialize Flask app
app = Flask(__name__)
app.register_blueprint(api_blueprint)

# Setup logging
def setup_logging(app):
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    )
    app.logger.setLevel(logging.INFO)
    for handler in app.logger.handlers:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
            )
        )

setup_logging(app)
logger = logging.getLogger(__name__)

llm_client = LLMInterface(LLM_PROVIDER, LLM_MODEL)

@tool
def llm_generate(
    prompt: str, context: Optional[str] = None
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
                "prompt": "Analyze the sales data and provide summary and insights, response a json object including 'summary' and 'insights'.",
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

    response = llm_client.generate(prompt, context)
    return response

# Register the tool after its definition
global_tools_hub.register_tool(llm_generate)
global_tools_hub.load_tools("tools")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the VM with a specified goal or start the visualization server."
    )
    parser.add_argument("--goal", help="Set a goal for the VM to achieve")
    parser.add_argument(
        "--server", action="store_true", help="Start the visualization server"
    )
    parser.add_argument(
        "--port", type=int, default=5000, help="Port to run the visualization server on"
    )

    args = parser.parse_args()

    if args.goal:
        repo_path = os.path.join(GIT_REPO_PATH, datetime.now().strftime("%Y%m%d%H%M%S"))
        vm = PlanExecutionVM(repo_path, llm_client)
        run_vm_with_goal(vm, args.goal)
        logger.info("VM execution completed")
    elif args.server:
        logger.info("Starting visualization server...")
        app.run(debug=True, port=args.port)
    else:
        logger.info(
            "Please specify --goal to run the VM with a goal or --server to start the visualization server"
        )
