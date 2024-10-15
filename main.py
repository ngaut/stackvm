import os
import requests
import logging
from flask import Flask
import argparse
from datetime import datetime
from typing import Optional

from app.controller.api_routes import api_blueprint
from app.controller.engine import run_vm_with_goal
from app.config.settings import GIT_REPO_PATH
from app.services import PlanExecutionVM
from app.services import LLMInterface
from app.config.settings import LLM_MODEL
from app.tools import global_tools_hub

# Initialize Flask app
app = Flask(__name__)
app.register_blueprint(api_blueprint)


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


# Setup logging
setup_logging(app)

# Read the API key from environment variables
API_KEY = os.environ.get("TIDB_AI_API_KEY")
if not API_KEY:
    app.logger.error("TIDB_AI_API_KEY not found in environment variables")

llm_client = LLMInterface(LLM_MODEL)


def retrieve_knowledge_graph(query):
    """
    Retrieves information from a knowledge graph based on a query, returning nodes and relationships between those nodes.

    Arguments:
    - `query`: The query string. Can be a direct string or a variable reference.

    Example to call this tool:
    **Example:**
    ```json
    {
        "seq_no": 2,
        "type": "calling",
        "parameters": {
            "tool": "retrieve_knowledge_graph",
                "params": {
                "query": "TiDB latest stable version"
            },
            "output_vars": "tidb_version_graph"
        }
    }
    """

    url = "https://tidb.ai/api/v1/admin/graph/search"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    data = {"query": query, "include_meta": False, "depth": 2, "with_degree": False}
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()  # Raises HTTPError for bad responses
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Request to search_graph failed: {e}")
        return {"error": "Failed to perform search_graph request."}
    except ValueError:
        logging.error("Invalid JSON response received from search_graph.")
        return {"error": "Invalid response format."}


def vector_search(query, top_k=5):
    """
    Retrieves embedded knowledge chunks based on an embedding query.

    Arguments:
    - `query`: The query string. Can be a direct string or a variable reference.
    - `top_k`: The number of top chunks to retrieve. Can be a direct integer or a variable reference.

    Example to call this tool:

    **Example:**
    ```json
    {
        "seq_no": 3,
        "type": "calling",
        "parameters": {
            "tool": "vector_search",
            "params": {
                "query": "Information about Mount Everest",
                "top_k": 3
            },
            "output_vars": "embedded_chunks"
        }
    }
    ```
    """

    url = "https://tidb.ai/api/v1/admin/embedding_retrieve"
    params = {"question": query, "chat_engine": "default", "top_k": top_k}
    headers = {"accept": "application/json", "Authorization": f"Bearer {API_KEY}"}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()  # Raises HTTPError for bad responses
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Request to retrieve_embedding failed: {e}")
        return {"error": "Failed to perform retrieve_embedding request."}
    except ValueError:
        logging.error("Invalid JSON response received from retrieve_embedding.")
        return {"error": "Invalid response format."}


def llm_generate(
    prompt: str, context: Optional[str] = None, response_format: Optional[str] = None
):
    """
    Generates a response using the Language Model (LLM).

    Arguments:
    - `prompt`: The prompt to provide to the LLM. Can be a direct string or a variable reference.
    - `context` (optional): Additional context for the LLM. Can be a direct string or a variable reference.

    Example to call this tool:
    **Example:**
    ```json
    {
        "seq_no": 1,
        "type": "calling",
        "parameters": {
            "tool": "llm_generate",
            "params": {
                "prompt": "Simulate the step-by-step execution of the following Python code to count the occurrences of the character 'r' in the word 'strawberry'. Provide a detailed explanation of each step and the final numerical result.\n\nword = 'strawberry'\ncount = 0\nfor char in word:\n    if char == 'r':\n        count += 1\nprint(count)\n\n Example output:To count the occurrences of the character 'r' in the word 'strawberry' using the provided pseudo Python code, we can break it down step by step:\n\n1. Initialization:\n   - Set word = 'strawberry' and char_to_count = 'r'.\n\n2. Convert to Lowercase:\n   - Both word and char_to_count are already in lowercase:\n     word = 'strawberry'\n     char_to_count = 'r'\n\n3. Count Occurrences:\n   We iterate through each character c in word and check if c is equal to char_to_count ('r'):\n   - 's' → not 'r' (count = 0)\n   - 't' → not 'r' (count = 0)\n   - 'r' → is 'r' (count = 1)\n   - 'a' → not 'r' (count = 1)\n   - 'w' → not 'r' (count = 1)\n   - 'b' → not 'r' (count = 1)\n   - 'e' → not 'r' (count = 1)\n   - 'r' → is 'r' (count = 2)\n   - 'r' → is 'r' (count = 3)\n   - 'y' → not 'r' (count = 3)\n\n4. Final Count:\n   The total count of 'r' in 'strawberry' is 3.\n\nThus, the numerical result is 3.",
                "context": null
            },
            "output_vars": "r_count_by_pseudo_python_simulation"
        }
    }
    ```

    Example with json response:
    ```json
    {
        "seq_no": 1,
        "type": "calling",
        "parameters": {
            "tool": "llm_generate",
            "params": {
                "prompt": "Analyze the sales data and provide summary and insights.",
                "context": "${sales_data}",
            },
            "output_vars": ["summary", "insights"]
        }
    }
    ```
    """

    if response_format:
        prompt = prompt + "\n" + response_format

    response = llm_client.generate(prompt, context)
    return response


global_tools_hub.register_tool(llm_generate)
global_tools_hub.register_tool(retrieve_knowledge_graph)
global_tools_hub.register_tool(vector_search)

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
        logging.info("VM execution completed")
    elif args.server:
        logging.info("Starting visualization server...")
        app.run(debug=True, port=args.port)
    else:
        logging.info(
            "Please specify --goal to run the VM with a goal or --server to start the visualization server"
        )
