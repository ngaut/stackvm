import logging
import requests
import json
from typing import List, Optional, Dict, Any

from app.utils import extract_json
from app.config.settings import LLM_PROVIDER, LLM_MODEL
from app.services import LLMInterface
from app.instructions.tools import tool

logger = logging.getLogger(__name__)

class KnowledgeGraphClient:
    def __init__(self, base_url: str, kb_id: int):
        self.base_url = base_url.rstrip("/")
        self.kb_id = kb_id

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

        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    def retrieve_neighbors(
        self,
        entities_ids: List[int],
        query: Optional[str] = None,
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

        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    def retrieve_chunks(self, relationships_ids: List[int]):
        """
        Retrieve chunks associated with given relationship IDs.
        """
        url = (
            f"{self.base_url}/admin/knowledge_bases/{self.kb_id}/graph/knowledge/chunks"
        )
        payload = {"relationships_ids": relationships_ids}

        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()


knowledge_client = KnowledgeGraphClient("https://tidb.ai/api/v1", 30001)
llm_client = LLMInterface(LLM_PROVIDER, LLM_MODEL)


class MetaGraph:
    def __init__(self, llm_client, query):
        self.llm_client = llm_client
        self.entities = {}
        self.relationships = []
        self.initial_queries = []
        self._generate_meta_graph(query)

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
        self.relationships = []
        self.chunks = []

    def add_entity(self, entity):
        self.entities[entity["id"]] = entity

    def add_relationship(self, relationship):
        self.relationships.append(relationship)

    def retrieve_chunks(self):
        relationships_ids = []
        for relationship in self.relationships:
            relationships_ids.append(relationship["id"])
        self.chunks = knowledge_client.retrieve_chunks(relationships_ids)

    def to_dict(self):
        return {"entities": self.entities, "relationships": self.relationships, "chunks": self.chunks}


def evaluation_retrieval_results(
    llm_client,
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

    Retrieved Entities:
    {json.dumps(retrieval_results.get('entities', []), indent=2)}
    
    Retrieved Relationships:
    {json.dumps(retrieval_results.get('relationships', []), indent=2)}

    Available tools:
    - retrieve_knowledge(query) -> dict: Retrieve knowledge from the knowledge base.
    - retrieve_neighbors(entities_ids: List[int], query) -> dict: Retrieve neighbors of the given entities.

    
    Your task is to
    1. Filter out the entities and relationships that are not helpful in answering the query
    2. Identify the entities and relationships (are not already in the exploration graph) that are (and only)useful in answering the query, which should be added to the exploration graph.
    3. Determine if there are missing information to give an correct answer to the query. If the retrieved information are already sufficient to answer the query, it should contain enough information to answer each key question in the query.
    4. If not, generate next actions to collect the missing information based on the meta-graph, the exploration graph, and the available tools.
    
    Respond in JSON format as follows:
    {{
        "useful_entity_ids": [id1, id2, ...],
        "useful_relationship_ids": [id1, id2, ...],
        "is_sufficient": true/false,
        "next_actions": [
            {{
                "tool": "retrieve_knowledge",
                "query": "string, the query to retrieve knowledge"
            }}
            {{
                "tool": "retrieve_neighbors",
                "entities_ids": [id1, id2, ...],
                "query": "string, the query to retrieve neighbors"
            }}
        ]
    }}
    """
    response = llm_client.generate(prompt)
    res_str = extract_json(response)
    analysis = json.loads(res_str)

    return analysis

@tool
def smart_retrieve(
    query: str,
    max_iterations: int = 5,
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
    logger.info(f"Starting search with query: {query}")
    # Initialize Meta-Graph and Exploration Graph
    meta_graph = MetaGraph(llm_client, query)
    exploration_graph = ExplorationGraph()

    # Step 2: Initial Retrieval
    entities = {}
    relationships = {}
    for query in meta_graph.initial_queries:
        logger.info(f"Initial query: {query}")
        retrieval_results = knowledge_client.retrieve_knowledge(query, top_k=10)
        for entity in retrieval_results.get("entities", []):
            entities[entity["id"]] = entity
        for relationship in retrieval_results.get("relationships", []):
            relationships[relationship["id"]] = relationship

    # Iterative Search Process
    for iteration in range(1, max_iterations + 1):
        logger.info(f"\n--- Iteration {iteration} ---")

        # Step 3: evaluate the retrieval results
        analysis = evaluation_retrieval_results(
            llm_client,
            {"entities": entities, "relationships": relationships},
            exploration_graph,
            meta_graph,
        )

        logger.debug("evaluation result", analysis)

        for id in analysis.get("useful_entity_ids", []):
            if id in entities:
                exploration_graph.add_entity(entities[id])
                del entities[id]

        for id in analysis.get("useful_relationship_ids", []):
            if id in relationships:
                exploration_graph.add_relationship(relationships[id])
                del relationships[id]

        if analysis.get("is_sufficient", []):
            logger.info("Sufficient information retrieved.")
            break

        for action in analysis.get("next_actions", []):
            if action.get("tool") == "retrieve_knowledge":
                retrieval_results = knowledge_client.retrieve_knowledge(
                    action.get("query"), top_k=10
                )
                for entity in retrieval_results.get("entities", []):
                    entities[entity["id"]] = entity
                for relationship in retrieval_results.get("relationships", []):
                    relationships[relationship["id"]] = relationship
            elif action.get("tool") == "retrieve_neighbors":
                retrieval_results = knowledge_client.retrieve_neighbors(
                    action.get("entities_ids"), action.get("query")
                )
                for relationship in retrieval_results.get("relationships", []):
                    relationships[relationship["id"]] = relationship

    # Step 4: retrieve the relevant chunks
    exploration_graph.retrieve_chunks()

    return exploration_graph
