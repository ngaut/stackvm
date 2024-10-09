import os
import requests
from typing import Any, Dict, Optional, List
from utils import interpolate_variables, find_first_json_object

# Add these imports at the top of the file
import logging
import json

# Set up logging
logger = logging.getLogger(__name__)

# Read the API key from environment variables
API_KEY = os.environ.get('TIDB_AI_API_KEY')
if not API_KEY:
    logger.error("TIDB_AI_API_KEY not found in environment variables")

def search_graph(query):
    """
    Searches the graph based on the provided query.
    Args:
        query (str): The search query.
    Returns:
        dict: JSON response from the API or an error message.
    """
    url = 'https://tidb.ai/api/v1/admin/graph/search'
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {API_KEY}"
    }
    data = {
        'query': query,
        'include_meta': False,
        'depth': 2,
        'with_degree': False
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()  # Raises HTTPError for bad responses
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Request to search_graph failed: {e}")
        return {"error": "Failed to perform search_graph request."}
    except ValueError:
        logger.error("Invalid JSON response received from search_graph.")
        return {"error": "Invalid response format."}

def embedding_retrieve(query, top_k=5):
    """
    Retrieves embeddings based on the provided query.
    Args:
        query (str): The input question for embedding retrieval.
        top_k (int): Number of top results to retrieve.
    Returns:
        dict: JSON response from the API or an error message.
    """
    url = 'https://tidb.ai/api/v1/admin/embedding_retrieve'
    params = {
        'question': query,
        'chat_engine': 'default',
        'top_k': top_k
    }
    headers = {
        'accept': 'application/json',
        'Authorization': f"Bearer {API_KEY}"
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()  # Raises HTTPError for bad responses
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Request to retrieve_embedding failed: {e}")
        return {"error": "Failed to perform retrieve_embedding request."}
    except ValueError:
        logger.error("Invalid JSON response received from retrieve_embedding.")
        return {"error": "Invalid response format."}

class InstructionHandlers:
    def __init__(self, vm):
        self.vm = vm

    def _handle_error(self, message: str) -> bool:
        """Common error handling method."""
        self.vm.logger.error(message)
        self.vm.state['errors'].append(message)
        return False

    def retrieve_knowledge_graph_handler(self, params: Dict[str, Any]) -> bool:
        """Handle retrieval from knowledge graph."""
        query = params.get('query')
        output_var = params.get('output_var')
        
        if not query or not output_var:
            return self._handle_error("Missing 'query' or 'output_var' in parameters.")

        result = search_graph(query)
        self.vm.set_variable(output_var, result)
        return True

    def vector_search_handler(self, params: Dict[str, Any]) -> bool:  # Updated method name
        """Handle retrieval of embedded chunks."""  # Updated docstring
        vector_search = self.vm.resolve_parameter(params.get('vector_search'))
        output_var = params.get('output_var')
        top_k = params.get('top_k', 5)

        if not isinstance(vector_search, str) or not isinstance(output_var, str):
            return self._handle_error("Invalid parameters for 'vector_search'.")  # Updated error message

        result = embedding_retrieve(vector_search, top_k)
        if result is not None:
            self.vm.set_variable(output_var, result)
            return True
        return self._handle_error(f"Failed to retrieve embedded chunks for query '{vector_search}'.")

    def llm_generate_handler(self, params: Dict[str, Any]) -> bool:
        """Handle LLM generation."""
        prompt = params.get('prompt')
        output_var = params.get('output_var')
        
        if not prompt or not output_var:
            return self._handle_error("Missing 'prompt' or 'output_var' in parameters.")

        interpolated_prompt = interpolate_variables(prompt, self.vm.state['variables'])
        response = self.vm.llm_interface.generate(interpolated_prompt)
        
        if response:
            self.vm.set_variable(output_var, response)
            return True
        return self._handle_error("LLM failed to generate a response.")

    def condition_handler(self, params: Dict[str, Any]) -> bool:
        """Handle conditional execution."""
        prompt = self.vm.resolve_parameter(params.get('prompt'))
        context = self.vm.resolve_parameter(params.get('context'))
        if_true = params.get('true_branch', [])
        if_false = params.get('false_branch', [])

        if not isinstance(prompt, str):
            return self._handle_error("Invalid prompt for 'condition' instruction.")

        result = self.vm.llm_interface.evaluate_condition(prompt, context)
        self.vm.logger.info(f"Condition result: {result}")
        
        try:
            parsed_result = json.loads(find_first_json_object(result))
            condition_result = parsed_result['result']
            explanation = parsed_result['explanation']
            
            self.vm.logger.info(f"Condition result: {condition_result}. Explanation: {explanation}")
            
            if isinstance(condition_result, bool):
                if condition_result:
                    success, steps_executed = self.vm.execute_subplan(if_true)
                    total_steps = len(if_true) + len(if_false)
                else:
                    success, steps_executed = self.vm.execute_subplan(if_false)
                    total_steps = len(if_false) + len(if_true)
                
                if success:
                    self.vm.state['program_counter'] += total_steps
                
                return success
            else:
                return self._handle_error(f"Invalid condition result type: {type(condition_result)}. Expected boolean.")
        except Exception as e:
            return self._handle_error(f"Unexpected error in condition handling: {str(e)}")

    def assign_handler(self, params: Dict[str, Any]) -> bool:
        """Handle variable assignment."""
        value = params.get('value')
        var_name = params.get('var_name')
        
        if not var_name:
            return self._handle_error("Missing 'var_name' in parameters.")

        value_resolved = self.vm.resolve_parameter(value)
        self.vm.set_variable(var_name, value_resolved)
        return True

    def reasoning_handler(self, params: Dict[str, Any]) -> bool:
        """Handle reasoning steps."""
        chain_of_thoughts = params.get('chain_of_thoughts')
        dependency_analysis = params.get('dependency_analysis')

        if not isinstance(chain_of_thoughts, str) or not isinstance(dependency_analysis, str):
            return self._handle_error("Invalid parameters for 'reasoning'.")

        self.vm.logger.info("Reasoning step:chain_of_thoughts: {chain_of_thoughts}\n{dependency_analysis}")
        
        self.vm.state['msgs'].append({
            'chain_of_thoughts': chain_of_thoughts,
            'dependency_analysis': dependency_analysis
        })
        return True
