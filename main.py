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
    Searches the graph based on the provided query.
    Args:
        query (str): The search query.
    Returns:
        dict: JSON response from the API or an error message.
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
    Retrieves embeddings based on the provided query.
    Args:
        query (str): The input question for embedding retrieval.
        top_k (int): Number of top results to retrieve.
    Returns:
        dict: JSON response from the API or an error message.
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
) -> bool:
    """Handle LLM generation."""
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
