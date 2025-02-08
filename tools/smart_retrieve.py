import logging
import requests
import time
import json
import os
from typing import List, Optional, Dict, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps

from app.utils import extract_json
from app.config.settings import REASON_LLM_PROVIDER, REASON_LLM_MODEL, EVALUATION_LLM_PROVIDER, EVALUATION_LLM_MODEL
from app.llm.interface import LLMInterface
from app.instructions.tools import tool

logger = logging.getLogger(__name__)


AUTOFLOW_BASE_URL = os.environ.get("AUTOFLOW_BASE_URL", "https://tidb.ai")

KB_ID = os.environ.get("KB_ID", 30001)

# Define retry strategy
retry_strategy = Retry(
    total=5,  # Total number of retry attempts
    backoff_factor=1,  # Exponential backoff factor
    status_forcelist=[429, 500, 502, 503, 504],  # HTTP status codes to retry on
    allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
    raise_on_status=False,
)


def with_retry(max_retries=3, backoff_factor=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:  # Last attempt
                        logger.error(
                            f"Max retries exceeded for {func.__name__}: {str(e)}"
                        )
                        raise

                    wait_time = backoff_factor**attempt
                    logger.warning(
                        f"{func.__name__} failed, retrying in {wait_time}s. Error: {str(e)}"
                    )
                    time.sleep(wait_time)
            return None

        return wrapper

    return decorator


class KnowledgeGraphClient:
    def __init__(self, base_url: str, kb_id: int):
        self.base_url = base_url.rstrip("/")
        self.kb_id = kb_id

        # Create session with retry strategy
        self.session = requests.Session()
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def retrieve_knowledge(
        self, query: str, top_k: int = 10, similarity_threshold: float = 0.5
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Retrieve knowledge graph data based on a query.
        """
        url = f"{self.base_url}/admin/knowledge_bases/{self.kb_id}/graph/knowledge"
        payload = {
            "query": query,
            "top_k": top_k,
            "similarity_threshold": similarity_threshold,
        }
        logger.info("retrieve_knowledge with argument: %s", query)

        try:
            response = self.session.post(url, json=payload, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RetryError as e:
            logger.error("Max retries exceeded for retrieve_knowledge: %s", str(e))
            raise
        except requests.exceptions.RequestException as e:
            logger.error("Request to retrieve_knowledge failed: %s", str(e))
            raise
        except ValueError as e:
            logger.error(
                "Invalid JSON response received from retrieve_knowledge: %s", str(e)
            )
            raise

    def retrieve_neighbors(
        self,
        entities_ids: List[int],
        query: str,
        max_depth: int = 1,
        max_neighbors: int = 10,
        similarity_threshold: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Retrieve neighbor nodes for given entity IDs.
        """
        url = f"{self.base_url}/admin/knowledge_bases/{self.kb_id}/graph/knowledge/neighbors"
        payload = {
            "entities_ids": entities_ids,
            "query": query,
            "max_depth": max_depth,
            "max_neighbors": max_neighbors,
            "similarity_threshold": similarity_threshold,
        }

        logger.info("retrieve_neighbors with arguments: %s, %s", entities_ids, query)

        try:
            response = self.session.post(url, json=payload, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RetryError as e:
            logger.error("Max retries exceeded for retrieve_neighbors: %s", str(e))
            raise
        except requests.exceptions.RequestException as e:
            if e.response is not None:
                logger.error(
                    "Request to retrieve_neighbors failed with status code %s, response content: %s",
                    e.response.status_code,
                    e.response.text,
                )
            else:
                logger.error(
                    "Request to retrieve_neighbors encountered an error: %s. No response object available.",
                    str(e),
                )
            raise
        except ValueError as e:
            logger.error(
                "Invalid JSON response received from retrieve_neighbors: %s", str(e)
            )
            raise

    def retrieve_chunks(self, relationships_ids: List[int]):
        """
        Retrieve chunks associated with given relationship IDs.
        """
        url = (
            f"{self.base_url}/admin/knowledge_bases/{self.kb_id}/graph/knowledge/chunks"
        )
        payload = {"relationships_ids": relationships_ids}

        try:
            response = self.session.post(url, json=payload, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RetryError as e:
            logger.error("Max retries exceeded for retrieve_chunks: %s", str(e))
            raise
        except requests.exceptions.RequestException as e:
            if e.response is not None:
                logger.error(
                    "Request to retrieve_chunks failed with status code %s, response content: %s",
                    e.response.status_code,
                    e.response.text,
                )
            else:
                logger.error(
                    "Request to retrieve_chunks encountered an error: %s. No response object available.",
                    str(e),
                )
            raise
        except ValueError as e:
            logger.error(
                "Invalid JSON response received from retrieve_chunks: %s", str(e)
            )
            raise


knowledge_client = KnowledgeGraphClient(f"{AUTOFLOW_BASE_URL}/api/v1", KB_ID)
llm_client = LLMInterface(REASON_LLM_PROVIDER, REASON_LLM_MODEL)
logger.info(f"Using {REASON_LLM_MODEL} Reasoning LLM")
evaluation_client = LLMInterface(EVALUATION_LLM_PROVIDER, EVALUATION_LLM_MODEL)
logger.info(f"Using {EVALUATION_LLM_MODEL} Evaluation LLM")

class MetaGraph:
    def __init__(self, llm_client, query):
        self.llm_client = llm_client
        self.entities = {}
        self.relationships = []
        self.initial_queries = []
        self._generate_meta_graph(query)

    @with_retry()
    def _generate_meta_graph(self, query: str):
        """
        Generates a Meta-Graph based on user query using LLM.

        Args:
            query: The user query string
            llm_client: LLM client for generating graph components

        Returns:
            MetaGraph object containing entities and relationships
        """
        # Prompt template for LLM to analyze the query and generate graph components
        prompt = f"""
        Task: Generate a comprehensive meta-graph representation of the given query. The meta-graph should fully capture the query's semantic meaning and intent using entities and their relationships.

        Requirements:
        1. The meta-graph should be semantically equivalent to the query, meaning it can be used to reconstruct the original query intent.
        2. Entities should represent the main subjects/objects that the query is about.
        3. Relationships should capture the intended actions, comparisons, or connections between entities.
        4. Then, Generate 2-4 search queries to collect the information used to answer the Query.

        Please analyze this query and return a meta-graph representation in the following JSON format:
        ```json
        {{
            "entities": [
                {{
                    "name": "entity_name",
                    "description": "string",
                }}
            ],
            "relationships": [
                {{
                    "source_entity": "entity_name",
                    "target_entity": "entity_name",
                    "relationship": "string, describe their relationship",
                }}
            ],
            "initial_queries": [
                "string, describe the initial query to search relevant information to answer the query",
            ]
        }}
        ```

        Query to analyze: "{query}"
        
        Important:
        - Ensure all entities and relationships together can reconstruct the original query intent
        - Use precise and specific relationship descriptions
        - Include only relevant entities that contribute to the query's meaning
        - Maintain a logically consistent, clear, and concise graph structure.
        """

        # Generate graph components using LLM
        response = self.llm_client.generate(prompt)
        graph_components = json.loads(extract_json(response))

        for entity in graph_components["entities"]:
            self.add_entity(entity)

        # Add relationships
        for rel in graph_components["relationships"]:
            self.add_relationship(rel)

        self.initial_queries = graph_components["initial_queries"]

    def add_entity(self, entity):
        self.entities[entity["name"]] = entity

    def add_relationship(self, relationship):
        self.relationships.append(relationship)

    def to_dict(self):
        return {
            "entities": self.entities,
            "relationships": self.relationships,
            "initial_queries": self.initial_queries,
        }


class ExplorationGraph:
    def __init__(self):
        self.entities = {}
        self.relationships = {}
        self.chunks = []

    def add_entity(self, entity):
        self.entities[entity["id"]] = entity

    def add_relationship(self, relationship):
        self.relationships[relationship["id"]] = relationship

    def retrieve_chunks(self):
        relationships_ids = [rel["id"] for rel in self.relationships.values()]
        if not relationships_ids:
            return
        self.chunks = knowledge_client.retrieve_chunks(relationships_ids)

    def to_dict(self):
        return {
            "entities": [entity for entity in self.entities.values()],
            "relationships": [rel for rel in self.relationships.values()],
            "chunks": self.chunks,
        }

    def to_dict_public(self):
        # remove the id field
        entities = [
            {
                "name": entity["name"],
                "description": entity["description"],
            }
            for entity in self.entities.values()
        ]

        relationships = [
            {
                "source_entity": rel["source_entity"]["name"],
                "target_entity": rel["target_entity"]["name"],
                "relationship": rel["relationship"],
            }
            for rel in self.relationships.values()
        ]

        return {
            "entities": entities,
            "relationships": relationships,
            "chunks": self.chunks,
        }


@with_retry()
def evaluation_retrieval_results(
    llm_client,
    query,
    actions_history: list,
    retrieval_results: dict,
    exploration_graph: ExplorationGraph,
    meta_graph: MetaGraph,
) -> tuple:
    """
    Confirms the usefulness of retrieved information using the LLM.

    Args:
        llm_client: The LLM interface client.
        retrieval_results: The retrieved entities and relationships.
        exploration_graph: The current exploration graph.
        meta_graph: The meta graph representation of the query and the search strategy.
    """

    prompt = f"""
    Analyze the following search results for their usefulness in answering the query.

    Meta-Graph:
    {json.dumps(meta_graph.to_dict(), indent=2)}

    Current exploration graph:
    {json.dumps(exploration_graph.to_dict(), indent=2)}

    Actions History:
    {actions_history}

    New Retrieved Information:

    - New Retrieved Entities: {json.dumps(retrieval_results.get('entities', []), indent=2)}
    
    - New Retrieved Relationships: {json.dumps(retrieval_results.get('relationships', []), indent=2)}
    
    Query to answer: "{query}"

    Let's think in Step-by-step, use meta-graph and query to performance the following tasks:
    1. Filter out the entities and relationships that are not helpful in answering the query.
    2. Identify the useful (and only useful) entities and relationships in answering the query:
      - Only include entities and relationships that are relevant to answering the query
      - Skip any entities or relationships that are already present in the exploration graph
      - Focus on new, unique and helpful information that adds value to the exploration graph

    3. Determine if there are missing information that prevents giving a correct answer to the query:
      - Compare the meta-graph's entities and relationships with what's currently in the exploration graph.
        - Check if all key points from the query are covered in the exploration graph.
        - Verify if the relationships between entities in the exploration graph match what's needed in the meta-graph.
      - If the retrieved information are already sufficient to answer the query, it should contain enough information to answer each key question in the query.
      - If any information are missing:
        * Identify which entities or relationships from meta-graph are not yet in exploration graph
        * Generate next actions to collect the missing information using the available tools. Choosing a Tool for Next Actions:
          - For new information not in the graph, use retrieve_knowledge.
          - For expanding based on existing entities, use retrieve_neighbors.
          - Consider using different tools or query formulations than what was already tried (in Actions History).

    Respond in JSON format as follows:
    ```json
    {{
        "useful_entity_ids": [id1, id2, ...], # Choose from New Retrieved Entities which are useful and not already in the exploration graph
        "useful_relationship_ids": [id1, id2, ...], # Choose from New Retrieved Relationships which are useful and not already in the exploration graph
        "is_sufficient": true/false, # whether the retrieved information is sufficient to answer the query
        "missing_information": [miss key point description, miss key point description],
        "next_actions": [
            {{
                "tool": "retrieve_knowledge",
                "query": "string, the query to retrieve new information not in the graph.."
            }}
            {{
                "tool": "retrieve_neighbors",
                "entities_ids": [id1, id2, ...], # A list of entity IDs already in the exploration graph.
                "query": "string, the query to narrow down which neighbors to retrieve."
            }}
        ]
    }}
    ```
    """
    response = llm_client.generate(prompt)
    res_str = extract_json(response)
    if res_str is None:
        logger.error("Error extracting JSON from LLM response: %s", response)
        return None

    try:
        analysis = json.loads(res_str)
    except Exception as e:
        logger.error("Error processing evaluation result decoding %s:%s, %s", e, res_str, response, exc_info=True)
        raise e

    return analysis


def _process_action(action, knowledge_client):
    """
    Process a single action and return its results
    """
    try:
        if action.get("tool") == "retrieve_knowledge":
            return knowledge_client.retrieve_knowledge(action.get("query"), top_k=10)
        elif action.get("tool") == "retrieve_neighbors":
            return knowledge_client.retrieve_neighbors(
                action.get("entities_ids"), action.get("query")
            )
    except Exception as e:
        logger.error("Error processing action %s: %s", action, e, exc_info=True)
        return {"entities": [], "relationships": []}


def smart_retrieve(
    query: str,
    max_iterations: int = 3,
):
    """
    Performs an intelligent search using LLM to guide the search process based on the designed search strategy.

    Args:
        client: The client object with retrieve_knowledge and retrieve_neighbors methods
        query: Initial search query
        max_iterations: Maximum number of search iterations

    Returns:
        A dictionary containing the final answer and any clarification questions.
    """

    # Step 1: Receive User Query
    logger.info("Starting search with query: %s", query)
    start_time = time.time()
    # Initialize Meta-Graph and Exploration Graph
    meta_graph = MetaGraph(llm_client, query)
    exploration_graph = ExplorationGraph()
    logger.debug(
        f"Meta-Graph generation completed in {time.time() - start_time:.2f} seconds."
    )

    # Step 2: Initial Retrieval
    entities = {}
    relationships = {}
    actions_history = meta_graph.initial_queries or []

    # Prepare all query tasks
    tasks = meta_graph.initial_queries

    start_time = time.time()
    # Use ThreadPoolExecutor to execute retrieve_knowledge queries concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Create a mapping of Future objects to their corresponding queries
        future_to_query = {
            executor.submit(knowledge_client.retrieve_knowledge, q, top_k=10): q
            for q in tasks
        }

        # Process completed futures as they finish
        for future in as_completed(future_to_query):
            initial_query = future_to_query[future]
            try:
                retrieval_results = future.result()
            except Exception as e:
                logger.error(
                    "Error retrieving knowledge for query %s: %s", initial_query, e
                )
                continue

            # Merge entities and relationships from results
            for entity in retrieval_results.get("entities", []):
                entities[entity["id"]] = entity
            for relationship in retrieval_results.get("relationships", []):
                relationships[relationship["id"]] = relationship

    logger.info(
        f"Initial retrieval completed in {time.time() - start_time:.2f} seconds."
    )

    # Iterative Search Process
    for iteration in range(1, max_iterations + 1):
        logger.info(f"--- Iteration {iteration}: {query} ---")

        # Step 3: evaluate the retrieval results
        start_time = time.time()
        analysis = evaluation_retrieval_results(
            evaluation_client,
            query,
            actions_history,
            {"entities": entities, "relationships": relationships},
            exploration_graph,
            meta_graph,
        )
        logger.info(f"Analysis completed in {time.time() - start_time:.2f} seconds.")

        logger.debug("evaluation result: %s", analysis)

        if analysis is None:
            continue

        for id in analysis.get("useful_entity_ids", []):
            if id in entities:
                exploration_graph.add_entity(entities[id])
                del entities[id]

        for id in analysis.get("useful_relationship_ids", []):
            if id in relationships:
                exploration_graph.add_relationship(relationships[id])
                del relationships[id]

        if analysis.get("is_sufficient", []):
            logger.info("Sufficient information retrieved for query: %s", query)
            break

        start_time = time.time()
        # Process next actions concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            # Create a mapping of Future objects to their corresponding actions
            future_to_action = {
                executor.submit(_process_action, action, knowledge_client): action
                for action in analysis.get("next_actions", [])
            }

            # Process completed futures as they finish
            for future in as_completed(future_to_action):
                action = future_to_action[future]
                try:
                    retrieval_results = future.result()
                    # Merge entities and relationships from results
                    for entity in retrieval_results.get("entities", []):
                        entities[entity["id"]] = entity
                    for relationship in retrieval_results.get("relationships", []):
                        relationships[relationship["id"]] = relationship
                except Exception as e:
                    logger.error("Error processing action %s: %s", action, e)
                    continue
        logger.info(
            f"Iteration {iteration} completed in {time.time() - start_time:.2f} seconds."
        )

        actions_history.extend(analysis.get("next_actions", []))

    # Step 4: retrieve the relevant chunks
    exploration_graph.retrieve_chunks()

    return exploration_graph.to_dict_public()


@tool
def retrieve_knowledge_graph(query):
    """
    Retrieves TiDB related information from a knowledge graph based on a query, returning nodes and relationships between those nodes.

    Arguments:
    - `query`: The query string. Can be a direct string or a variable reference.

    Output:
    - Returns a single value representing the retrieved knowledge graph data.


    Best practices:
    - Focus on Structured Knowledge: Use the retrieve_knowledge_graph tool to retrieve structured and relational knowledge that is relevant to the query. This tool excels in identifying fine-grained knowledge points and understanding their connections.
    - Combine with LLM for Refinement:
        - Knowledge Graph Search may return extensive data, including numerous nodes and complex relationships.
        - Always follow up with an LLM generation tool to refine and summarize the results. This ensures the output is concise, precise, and tailored to the user's question.

    Strict Restriction:
    - Avoid User-Specific Queries: Do not use this tool to retrieve data that is specific to a user's environment, such as configurations, current versions, or private data. This tool is designed to handle general, shared knowledge within the graph.
    """

    return smart_retrieve(query)
