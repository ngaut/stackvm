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

    def _handle_error(self, message: str, instruction: Optional[str] = None, params: Optional[Dict[str, Any]] = None) -> bool:
        """
        Common error handling method with enhanced context for reflection.
        
        Args:
            message (str): The error message.
            instruction (Optional[str]): The instruction that caused the error.
            params (Optional[Dict[str, Any]]): The parameters of the instruction.
        
        Returns:
            bool: Always returns False to indicate an error occurred.
        """
        error_context = {
            "error_message": message,
            "instruction": instruction,
            "params": params,
            "current_step": self.vm.state.get('current_step'),
            "program_counter": self.vm.state.get('program_counter'),
        }
        
        self.vm.logger.error(f"Error occurred: {json.dumps(error_context, indent=2)}")
        self.vm.state['errors'].append(error_context)
        return False

    def retrieve_knowledge_graph_handler(self, params: Dict[str, Any]) -> bool:
        """Handle retrieval from knowledge graph."""
        query = params.get('query')
        output_var = params.get('output_var')
        
        if not query or not output_var:
            return self._handle_error("Missing 'query' or 'output_var' in parameters.", "retrieve_knowledge_graph", params)

        result = search_graph(query)
        self.vm.set_variable(output_var, result)
        return True

    def vector_search_handler(self, params: Dict[str, Any]) -> bool:  # Updated method name
        """Handle retrieval of embedded chunks."""  # Updated docstring
        vector_search = self.vm.resolve_parameter(params.get('vector_search'))
        output_var = params.get('output_var')
        top_k = params.get('top_k', 5)

        if not isinstance(vector_search, str) or not isinstance(output_var, str):
            return self._handle_error("Invalid parameters for 'vector_search'.", "vector_search", params)

        result = embedding_retrieve(vector_search, top_k)
        if result is not None:
            self.vm.set_variable(output_var, result)
            return True
        return self._handle_error(f"Failed to retrieve embedded chunks for query '{vector_search}'.", "vector_search", params)

    def llm_generate_handler(self, params: Dict[str, Any]) -> bool:
        """Handle LLM generation."""
        prompt = params.get('prompt')
        output_var = params.get('output_var')
        
        if not prompt or not output_var:
            return self._handle_error("Missing 'prompt' or 'output_var' in parameters.")

        interpolated_prompt = interpolate_variables(prompt, self.vm.state['variables'])
        interpolated_context = self.vm.resolve_parameter(params.get('context'))
        response = self.vm.llm_interface.generate(interpolated_prompt, interpolated_context)
        
        if response:
            self.vm.set_variable(output_var, response)
            return True
        return self._handle_error("LLM failed to generate a response.")

    def jmp_if_handler(self, params: Dict[str, Any]) -> bool:
        """Handle conditional jumps based on LLM evaluation."""
        condition_prompt = self.vm.resolve_parameter(params.get('condition_prompt'))
        context = self.vm.resolve_parameter(params.get('context'))
        jump_if_true = params.get('jump_if_true')
        jump_if_false = params.get('jump_if_false')
    
        if not condition_prompt or jump_if_true is None or jump_if_false is None:
            return self._handle_error("Missing 'condition_prompt', 'jump_if_true', or 'jump_if_false' in parameters.")
    
        response = self.vm.llm_interface.generate(condition_prompt, context)
    
        try:
            parsed_response = json.loads(find_first_json_object(response))
            condition_result = parsed_response.get('result')
            explanation = parsed_response.get('explanation', '')
    
            if not isinstance(condition_result, bool):
                return self._handle_error(f"Invalid condition result type: {type(condition_result)}. Expected boolean.")
    
            if condition_result:
                target_seq = jump_if_true
            else:
                target_seq = jump_if_false
    
            self.vm.logger.info(f"Jumping to seq_no {target_seq} based on condition result: {condition_result}. Explanation: {explanation}")
            self.vm.state['program_counter'] = self.vm.find_step_index(target_seq)
            return True
        except json.JSONDecodeError:
            return self._handle_error("Failed to parse JSON response from LLM.")
        except Exception as e:
            return self._handle_error(f"Unexpected error in jmp_if_handler: {str(e)}")

    def jmp_handler(self, params: Dict[str, Any]) -> bool:
        """Handle unconditional jumps to a specified sequence number."""
        target_seq = params.get('target_seq')
        if target_seq is None:
            return self._handle_error("Missing 'target_seq' in parameters.", "jmp", params)

        try:
            target_index = self.vm.find_step_index(target_seq)
            if target_index is None:
                return self._handle_error(f"Target sequence number {target_seq} not found in the plan.", "jmp", params)

            self.vm.logger.info(f"Unconditionally jumping to seq_no {target_seq}.")
            self.vm.state['program_counter'] = target_index
            return True
        except Exception as e:
            return self._handle_error(f"Unexpected error in jmp_handler: {str(e)}", "jmp", params)

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