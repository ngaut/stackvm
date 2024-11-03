import os
import logging
from flask import Flask, url_for
import argparse
from datetime import datetime
from typing import Optional

from app.controller.api_routes import api_blueprint, main_blueprint
from app.config.settings import (
    GIT_REPO_PATH,
    GENERATED_FILES_DIR,
    LLM_PROVIDER,
    LLM_MODEL,
)
from app.services import LLMInterface
from app.controller.task import TaskService
from app.instructions import global_tools_hub, tool
from app.database import SessionLocal

# Initialize Flask app
app = Flask(__name__)
app.register_blueprint(api_blueprint)
app.register_blueprint(main_blueprint)


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
def llm_generate(prompt: str, context: Optional[str] = None):
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

    response = llm_client.generate(prompt, context)
    return response


@tool
def generate_file_download_link(content: str):
    """
    Generates a download link for the given content. It usually used to generate a report for download.

    Arguments:
    - `content`: The content to be downloaded.

    Output: The download link for the content (report or other format).
    """
    try:
        # Generate a unique filename
        filename = f"generated_{datetime.now().strftime('%Y%m%d%H%M%S')}.md"
        file_path = os.path.join(GENERATED_FILES_DIR, filename)

        # Write the markdown content to a file
        with open(file_path, "w") as file:
            file.write(content)

        # Generate the full download link
        download_link = url_for("api.download_file", filename=filename, _external=True)
        return download_link
    except Exception as e:
        logger.error(f"Error generating file for download: {str(e)}", exc_info=True)
        return ValueError(f"Error generating file for download: {str(e)}")


# Register the tool after its definition
global_tools_hub.register_tool(llm_generate)
global_tools_hub.register_tool(generate_file_download_link)
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
        ts = TaskService()
        with SessionLocal() as session:
            task = ts.create_task(session, args.goal, repo_path)
        task.execute()
        logger.info("VM execution completed")
    elif args.server:
        logger.info("Starting visualization server...")
        app.run(debug=True, port=args.port)
    else:
        logger.info(
            "Please specify --goal to run the VM with a goal or --server to start the visualization server"
        )
