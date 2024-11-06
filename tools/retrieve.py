import os
import requests
import logging

from app.instructions.tools import tool

logger = logging.getLogger(__name__)

API_KEY = os.environ.get("TIDB_AI_API_KEY")
if not API_KEY:
    logger.error("TIDB_AI_API_KEY not found in environment variables")


@tool
def retrieve_knowledge_graph(query):
    """
    Retrieves information from a knowledge graph based on a query, returning nodes and relationships between those nodes.

    Arguments:
    - `query`: The query string. Can be a direct string or a variable reference.

    Output:
    - Returns a single value representing the retrieved knowledge graph data.

    Example to call this tool:
    **Example:**
    ```json
    {
        "seq_no": 2,
        "type": "calling",
        "parameters": {
            "tool_name": "retrieve_knowledge_graph",
            "tool_params": {
                "query": "TiDB latest stable version"
            },
            "output_vars": ["tidb_version_graph"]
        }
    }

    Best practices:
    - Leverage the Knowledge Graph Search tool for tasks that require retrieving fine-grained knowledge points and understanding the relationships or connections between these entities. This tool excels in exploring structured and relational data, making it ideal for identifying specific concepts and their interdependencies.
    - To maximize its effectiveness, integrate the Knowledge Graph Search with an LLM (Large Language Model) generation tool. First, use the Knowledge Graph Search to pinpoint relevant knowledge and their intricate relationships. Then, pass this structured data to the LLM generation tool to extract and organize the precise information needed by the user.
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
        logger.error("Request to search_graph failed: %s", str(e))
        return {"error": f"Failed to perform search_graph request: {str(e)}"}
    except ValueError:
        logger.error("Invalid JSON response received from search_graph: %s", str(e))
        return {"error": f"Invalid response format: {str(e)}"}


@tool
def vector_search(query, top_k=5):
    """
    Retrieves the most relevant data chunks based on embedding similarity to the query.

    Arguments:
    - `query`: The query string. It should be a clear and simple statement or question, focusing on a single objective.
    - `top_k`: The number of top chunks to retrieve. Can be a direct integer or a variable reference.

    Output:
    - Returns a single value containing the concatenated top `k` document chunks, stored in a unique variable. It does not return a JSON or dictionary object.

    Example to call this tool:

    **Example:**
    ```json
    {
        "seq_no": 3,
        "type": "calling",
        "parameters": {
            "tool_name": "vector_search",
            "tool_params": {
                "query": "Information about ...",
                "top_k": 3
            },
            "output_vars": ["embedded_chunks"]
        }
    }
    ```

    Best practices:
    - Use the Vector Search tool to retrieve data that is most similar to your query based on embedding distance. This tool excels at finding relevant document snippets that provide rich context and detailed information.
    - **Ensure your query is clear and focused on a single objective or aspect.** Avoid queries with multiple purposes to achieve the most accurate and relevant results.
    """

    url = "https://tidb.ai/api/v1/admin/embedding_retrieve"
    params = {"question": query, "chat_engine": "default", "top_k": top_k}
    headers = {"accept": "application/json", "Authorization": f"Bearer {API_KEY}"}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()  # Raises HTTPError for bad responses
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error("Request to retrieve_embedding failed: %s", str(e))
        return {"error": f"Failed to perform retrieve_embedding request: {str(e)}"}
    except ValueError:
        logger.error("Invalid JSON response received from retrieve_embedding: %s", str(e))
        return {"error": f"Invalid response format: {str(e)}"}
