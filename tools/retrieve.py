import os
import requests
import logging
import tiktoken

from app.instructions.tools import tool

logger = logging.getLogger(__name__)

API_KEY = os.environ.get("TIDB_AI_API_KEY")
if not API_KEY:
    logger.error("TIDB_AI_API_KEY not found in environment variables")

MAX_TOP_K = 5
MAX_CHUNK_TOKENS = 3072


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
    - Focus on Structured Knowledge: Use the retrieve_knowledge_graph tool to retrieve structured and relational knowledge that is relevant to the query. This tool excels in identifying fine-grained knowledge points and understanding their connections.
    - Combine with LLM for Refinement:
        - Knowledge Graph Search may return extensive data, including numerous nodes and complex relationships.
        - Always follow up with an LLM generation tool to refine and summarize the results. This ensures the output is concise, precise, and tailored to the user's question.

    Strict Restriction:
    - Avoid User-Specific Queries: Do not use this tool to retrieve data that is specific to a user's environment, such as configurations, current versions, or private data. This tool is designed to handle general, shared knowledge within the graph.
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

    # Initialize the tokenizer for the specified model at module level
    try:
        encoding = tiktoken.encoding_for_model(
            "gpt-4"
        )  # Automatically selects the appropriate encoding
    except Exception as e:
        logger.error("Failed to initialize the token encoder: %s", str(e))
        encoding = tiktoken.get_encoding("cl100k_base")

    url = "https://tidb.ai/api/v1/admin/embedding_retrieve"
    params = {"question": query, "chat_engine": "default", "top_k": top_k}
    headers = {"accept": "application/json", "Authorization": f"Bearer {API_KEY}"}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()  # Raises HTTPError for bad responses
        data = response.json()

        # Verify that the response is a list of chunks
        if not isinstance(data, list):
            return data

        processed_chunks = []
        for idx, chunk in enumerate(data):
            if not isinstance(chunk, dict) or "content" not in chunk:
                logger.warning(
                    f"Chunk at index {idx} is malformed or missing 'text' field. Skipping."
                )
                continue

            text = chunk["content"]
            token_count = len(encoding.encode(text))
            if token_count > MAX_CHUNK_TOKENS:
                # Truncate the text to fit within the token limit
                truncated_tokens = encoding.encode(text)[:MAX_CHUNK_TOKENS]
                truncated_text = encoding.decode(truncated_tokens)
                logger.warning(
                    f"Chunk at index {idx} exceeds MAX_CHUNK_TOKENS={MAX_CHUNK_TOKENS}. "
                    f"Truncating from {token_count} tokens to {MAX_CHUNK_TOKENS} tokens."
                )
                chunk["content"] = truncated_text
                # If you prefer to ignore excessively large chunks instead of truncating, uncomment the next line:
                # continue

            processed_chunks.append(chunk)

        return processed_chunks
    except requests.exceptions.RequestException as e:
        logger.error("Request to retrieve_embedding failed: %s", str(e))
        return {"error": f"Failed to perform retrieve_embedding request: {str(e)}"}
    except ValueError as e:
        logger.error(
            "Invalid JSON response received from retrieve_embedding: %s", str(e)
        )
        return {"error": f"Invalid response format: {str(e)}"}
    except Exception as e:
        logger.error("An unexpected error occurred in vector_search: %s", str(e))
        return {"error": f"An unexpected error occurred: {str(e)}"}
