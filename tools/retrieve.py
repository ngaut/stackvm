import os
import requests
import logging

from . import tool

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
            "tool": "retrieve_knowledge_graph",
                "params": {
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
        return {"error": "Failed to perform search_graph request."}
    except ValueError:
        logger.error("Invalid JSON response received from search_graph.")
        return {"error": "Invalid response format."}


@tool
def vector_search(query, top_k=5):
    """
    Retrieves embedded knowledge chunks based on an embedding query.

    Arguments:
    - `query`: The query string. Can be a direct string or a variable reference.
    - `top_k`: The number of top chunks to retrieve. Can be a direct integer or a variable reference.

    Output:
    - Returns a single value containing the concatenated top k document chunks.

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
            "output_vars": ["embedded_chunks"]
        }
    }
    ```

    Best practices:
    - Utilize the Vector Search tool when you need to retrieve detailed and comprehensive information from large volumes of unstructured or semi-structured data. This tool is adept at returning relevant document snippets that provide rich context and in-depth insights, rather than just simple descriptions of knowledge points.
    - To optimize its use, combine multiple Vector Search calls (different queries) with an LLM generation tool to enhance the depth and clarity of the responses. Start by employing the Vector Search to gather extensive and context-rich document fragments related to the query. Then, feed these detailed snippets into the LLM generation tool to synthesize and generate comprehensive answers.
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
        return {"error": "Failed to perform retrieve_embedding request."}
    except ValueError:
        logger.error("Invalid JSON response received from retrieve_embedding.")
        return {"error": "Invalid response format."}
