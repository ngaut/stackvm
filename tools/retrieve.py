import os
import requests
import logging
import tiktoken
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.instructions.tools import tool

logger = logging.getLogger(__name__)

API_KEY = os.environ.get("AUTOFLOW_API_KEY")
if not API_KEY:
    logger.error("AUTOFLOW_API_KEY not found in environment variables")

KNOWLEDGE_ENGINE = os.environ.get("KNOWLEDGE_ENGINE", "default")

AUTOFLOW_BASE_URL = os.environ.get("AUTOFLOW_BASE_URL", "https://tidb.ai")

LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4")

KB_ID = os.environ.get("KB_ID", 30001)

MAX_TOP_K = 10
MAX_CHUNK_TOKENS = 10240


# Define retry strategy
retry_strategy = Retry(
    total=5,  # Total number of retry attempts
    backoff_factor=1,  # Exponential backoff factor (e.g., 1, 2, 4, 8, ...)
    status_forcelist=[429, 500, 502, 503, 504],  # HTTP status codes to retry on
    allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],  # HTTP methods to retry
    raise_on_status=False,  # Do not raise exceptions for status codes
)

# Create an HTTPAdapter with the retry strategy
adapter = HTTPAdapter(max_retries=retry_strategy)

# Create a session and mount the adapter
session = requests.Session()
session.mount("https://", adapter)
session.mount("http://", adapter)

def retrieve_knowledge_graph(query):
    """
    Retrieves TiDB related information from a knowledge graph based on a query, returning nodes and relationships between those nodes.

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

    # hardcode to improve
    url = f"{AUTOFLOW_BASE_URL}/api/v1/admin/knowledge_bases/{KB_ID}/graph/search"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    data = {"query": query, "include_meta": False, "depth": 2, "with_degree": False}
    try:
        response = session.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()  # Raises HTTPError for bad responses
        return response.json()
    except requests.exceptions.RetryError as e:
        logger.error("Max retries exceeded for retrieve_knowledge_graph: %s", str(e))
        raise
    except requests.exceptions.RequestException as e:
        logger.error("Request to search_graph failed: %s", str(e))
        raise
    except ValueError as e:
        logger.error("Invalid JSON response received from search_graph: %s", str(e))
        raise


def get_chunk_content(chunk):
    if isinstance(chunk, dict):
        if "content" in chunk:
            return chunk["content"]
        elif "node" in chunk:
            node = chunk["node"]
            return node.get("text", None)

    logger.warning("Chunk is malformed or missing 'content' field.")
    return None

@tool
def vector_search(query, top_k=10):
    """
    Retrieves the most relevant snippets of TiDB documentation based on embedding similarity to your query.

    This tool leverages vector embeddings to find document fragments from TiDB documentation that are most semantically similar to your query. It excels at finding relevant document snippets that provide rich context and detailed information.

    Arguments:
      - `query`: The query string. It should be a clear and simple statement or question, focusing on a single objective for best results.
      - `top_k`: The number of top document snippets to retrieve. Must be an integer or a variable referencing an integer.

    Output:
      - Returns a list of dictionaries (`List[Dict]`). Each dictionary represents a retrieved document chunk and contains information about the chunk (e.g., content, source). **Important:** The raw output of this tool, a list of dictionaries, is **not intended for direct use in the final answer.** The document chunks are returned as individual fragments and require further processing to form a coherent response.


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
                "top_k": 10
            },
            "output_vars": ["embedded_chunks"]
        }
    }
    ```

    Best practices:
      - **Process Output with `llm_generate`:**  The `vector_search` tool returns a list of document chunks. **Always** process this raw output using the `llm_generate` tool to summarize, synthesize, and refine the information into a coherent answer before using it in the final response.  Do **not** directly use the raw `vector_search` output in the `final_answer`.
      - **Use Clear, Focused Queries:** For the best search results, ensure your query is clear, concise, and focuses on a **single**, specific question or objective. Avoid multi-part or ambiguous queries.
    """

    # Initialize the tokenizer for the specified model at module level
    try:
        encoding = tiktoken.encoding_for_model(
            LLM_MODEL
            # "gpt-4"
        )  # Automatically selects the appropriate encoding
    except Exception as e:
        logger.warning("Failed to initialize the token encoder: %s", str(e))
        encoding = tiktoken.encoding_for_model(
            "gpt-4o"
        )

    url = f"{AUTOFLOW_BASE_URL}/api/v1/admin/embedding_retrieve"
    json_payload = {
        "query": query,
        "chat_engine": KNOWLEDGE_ENGINE,
        "top_k": top_k
    }
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    try:
        response = session.post(url, headers=headers, json=json_payload, timeout=60)
        response.raise_for_status()  # Raises HTTPError for bad responses
        data = response.json()

        # Verify that the response is a list of chunks
        if not isinstance(data, list):
            return data

        total_token_count = 0
        for chunk in data:
            chunk_content = get_chunk_content(chunk)
            if chunk_content is not None:
                tokens = encoding.encode(chunk_content)
                token_count = len(tokens)
                total_token_count += token_count

        if total_token_count <= MAX_CHUNK_TOKENS:
            return data

        logger.info(
            f"Total token count ({total_token_count}) exceeds MAX_CHUNK_TOKENS ({MAX_CHUNK_TOKENS}). Initiating truncation process."
        )
        # Sort chunks by score descending (highest score first)
        sorted_chunks_with_indices = sorted(
            enumerate(data), key=lambda x: x[1].get("score", 0), reverse=True
        )

        choosen_chunks = []
        choosen_chunks_count = 0
        for idx, chunk in sorted_chunks_with_indices:
            text = get_chunk_content(chunk)
            if text is None:
                logger.warning(
                    "Chunk is missing 'content' field. Skipping truncation for this chunk."
                )
                continue

            # Update choosen_chunks_count
            choosen_chunks_count += len(encoding.encode(text))
            logger.debug(f"Remaining total token count: {choosen_chunks_count}")

            # Check if the choosen token count is now within the limit
            choosen_chunks.append(chunk)
            if choosen_chunks_count >= MAX_CHUNK_TOKENS:
                logger.info(
                    f"Total token count {choosen_chunks_count} will exceed {MAX_CHUNK_TOKENS}. Return now"
                )
                return choosen_chunks

        return choosen_chunks

    except requests.exceptions.RetryError as e:
        logger.error("Max retries exceeded for vector_search: %s", str(e))
        raise
    except requests.exceptions.RequestException as e:
        logger.error("Request to retrieve_embedding failed: %s", str(e))
        raise
    except ValueError as e:
        logger.error(
            "Invalid JSON response received from retrieve_embedding: %s", str(e)
        )
        raise
    except Exception as e:
        logger.error("An unexpected error occurred in vector_search: %s", str(e))
        raise
