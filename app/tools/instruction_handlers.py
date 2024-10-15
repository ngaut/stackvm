import os
import requests
from typing import Any, Dict, Optional
from app.utils import find_first_json_object

# Add these imports at the top of the file
import logging
import json

# Set up logging
logger = logging.getLogger(__name__)

# Read the API key from environment variables
API_KEY = os.environ.get("TIDB_AI_API_KEY")
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
    url = "https://tidb.ai/api/v1/admin/embedding_retrieve"
    params = {"question": query, "chat_engine": "default", "top_k": top_k}
    headers = {"accept": "application/json", "Authorization": f"Bearer {API_KEY}"}
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

    def _handle_error(
        self,
        message: str,
        instruction: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> bool:
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
            "program_counter": self.vm.state.get("program_counter"),
        }

        self.vm.logger.error(f"Error occurred: {json.dumps(error_context, indent=2)}")
        self.vm.state["errors"].append(error_context)
        return False

    def _set_output_vars(
        self,
        instruction_output: Any,
        output_vars: Dict[str, str],
        response_format: str = "text",
    ) -> bool:
        """
        Sets multiple output variables based on the instruction's output and the output_vars mapping.

        Args:
            instruction_output (Any): The raw output from the instruction.
            output_vars (Dict[str, str]): Mapping of variable names to expressions referencing the instruction's output.
            response_format (str): The format of the instruction's output ('json' or 'text').

        Returns:
            bool: True if all variables are set successfully, False otherwise.
        """
        if not output_vars:
            return True  # No output_vars to set

        print(f"output_vars: {output_vars}")
        print(f"instruction_output: {instruction_output}")
        print(f"response_format: {response_format}")

        try:
            if response_format == "json":
                if isinstance(instruction_output, str):
                    # Attempt to parse JSON string
                    instruction_output = json.loads(instruction_output)
                for var_name, var_expr in output_vars.items():
                    # Extract the key from the expression, e.g., "${llm_json_response.summary}" -> "summary"
                    key = var_expr.strip("${}").split(".")[-1]
                    var_value = instruction_output.get(key)
                    self.vm.set_variable(var_name, var_value)
            elif response_format == "text":
                if len(output_vars) != 1:
                    self.vm.logger.error(
                        "For 'text' response_format, 'output_vars' must contain exactly one key."
                    )
                    return False
                var_name, _ = next(iter(output_vars.items()))
                self.vm.set_variable(var_name, instruction_output)
            else:
                self.vm.logger.error(f"Unsupported response_format: {response_format}")
                return False
            return True
        except Exception as e:
            self.vm.logger.error(f"Failed to set output_vars: {e}")
            return False

    def retrieve_knowledge_graph_handler(
        self, params: Dict[str, Any], output_vars: Optional[Dict[str, str]] = None
    ) -> bool:
        """Handle retrieval from knowledge graph."""
        query = params.get("query")

        if not query or not output_vars:
            return self._handle_error(
                "Missing 'query' in in parameters or 'output_var' is not defined.",
                "retrieve_knowledge_graph",
                params,
            )

        result = search_graph(query)

        success = self._set_output_vars(result, output_vars)
        return success

    def vector_search_handler(
        self, params: Dict[str, Any], output_vars: Optional[Dict[str, str]] = None
    ) -> bool:
        """Handle retrieval of embedded chunks."""
        query = self.vm.resolve_parameter(params.get("query"))
        top_k = params.get("top_k", 5)

        if not isinstance(query, str) or not output_vars:
            return self._handle_error(
                "Invalid parameters for 'vector_search'.", "vector_search", params
            )

        result = embedding_retrieve(query, top_k)
        if result is not None:
            success = self._set_output_vars(result, output_vars)
            return success
        return self._handle_error(
            f"Failed to retrieve embedded chunks for query '{query}'.",
            "vector_search",
            params,
        )

    def llm_generate_handler(
        self, params: Dict[str, Any], output_vars: Optional[Dict[str, str]] = None
    ) -> bool:
        """Handle LLM generation."""
        prompt = params.get("prompt")
        response_format = params.get("response_format", "text")

        if not prompt or not output_vars:
            return self._handle_error("Missing 'prompt' or 'output_var' in parameters.")

        # Construct response format example from output_vars
        response_format_example = (
            self._construct_response_format_example(output_vars)
            if response_format == "json"
            else None
        )

        interpolated_prompt = self.vm.resolve_parameter(prompt)
        interpolated_context = self.vm.resolve_parameter(params.get("context"))
        response = self.vm.llm_interface.generate(
            interpolated_prompt, interpolated_context, response_format_example
        )

        if response:
            try:
                success = self._set_output_vars(response, output_vars, response_format)
                return success
            except json.JSONDecodeError:
                return self._handle_error(
                    f"Failed to parse JSON response from LLM: {response}."
                )

        return self._handle_error("LLM failed to generate a response.")

    def _construct_response_format_example(
        self, output_vars: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """Construct a response format example based on output variables."""
        # Extract keys from output_vars and create a JSON-like structure
        if not output_vars:
            return None

        example_structure = {}
        for key, value in output_vars.items():
            # Extract the JSON path from the value, assuming format "${llm_json_response.key}"
            json_key = value.split(".")[-1].strip("}")
            example_structure[json_key] = f"<{json_key}_example>"

        return json.dumps(example_structure, indent=2)

    def jmp_handler(
        self, params: Dict[str, Any], output_vars: Optional[Dict[str, str]] = None
    ) -> bool:
        """Handle both conditional and unconditional jumps."""
        condition_prompt = self.vm.resolve_parameter(params.get("condition_prompt"))
        context = self.vm.resolve_parameter(params.get("context"))
        jump_if_true = params.get("jump_if_true")
        jump_if_false = params.get("jump_if_false")
        target_seq = params.get("target_seq")

        if output_vars:
            self.vm.logger.info(
                f"Not allowed to use output variables in jmp instruction : {output_vars}"
            )

        if condition_prompt:
            # Conditional jump
            if jump_if_true is None or jump_if_false is None:
                return self._handle_error(
                    "Missing 'condition_prompt', 'jump_if_true', or 'jump_if_false' in parameters.",
                    instruction="jmp_if",
                    params=params,
                )

            response = self.vm.llm_interface.generate(condition_prompt, context)

            try:
                json_object = find_first_json_object(response)
                if json_object is None:
                    raise ValueError(
                        f"No JSON object found in the response: {response}."
                    )
                parsed_response = json.loads(json_object)
                condition_result = parsed_response.get("result")
                explanation = parsed_response.get("explanation", "")

                if not isinstance(condition_result, bool):
                    return self._handle_error(
                        f"Invalid condition result type: {type(condition_result)} in response {json_object}. Expected boolean.",
                        instruction="jmp",
                        params=params,
                    )

                if condition_result:
                    target_seq = jump_if_true
                else:
                    target_seq = jump_if_false

                self.vm.logger.info(
                    f"Jumping to seq_no {target_seq} based on condition result: {condition_result}. "
                    f"Explanation: {explanation}"
                )
            except json.JSONDecodeError:
                return self._handle_error(
                    "Failed to parse JSON response from LLM.",
                    instruction="jmp",
                    params=params,
                )
            except Exception as e:
                return self._handle_error(
                    f"Unexpected error in jmp_handler: {str(e)}",
                    instruction="jmp",
                    params=params,
                )
        elif target_seq is None:
            return self._handle_error(
                "Missing 'target_seq' for unconditional jump.", "jmp", params
            )

        try:
            target_index = self.vm.find_step_index(target_seq)
            if target_index is None:
                return self._handle_error(
                    f"Target sequence number {target_seq} not found in the plan.",
                    "jmp",
                    params,
                )

            self.vm.state["program_counter"] = target_index
            self.vm.logger.info(f"Jumped to seq_no {target_seq}")
            return True
        except Exception as e:
            return self._handle_error(
                f"Unexpected error in jmp_handler: {str(e)}", "jmp", params
            )

    def assign_handler(
        self, params: Dict[str, Any], output_vars: Optional[Dict[str, str]] = None
    ) -> bool:
        """Handle variable assignment."""
        for var_name, value in params.items():
            value_resolved = self.vm.resolve_parameter(value)
            self.vm.set_variable(var_name, value_resolved)
        if output_vars:
            self.vm.logger.info(
                f"Not allowed to use output variables in assign instruction : {output_vars}"
            )
        return True

    def reasoning_handler(
        self, params: Dict[str, Any], output_vars: Optional[Dict[str, str]] = None
    ) -> bool:
        """Handle reasoning steps."""
        chain_of_thoughts = params.get("chain_of_thoughts")
        dependency_analysis = params.get("dependency_analysis")

        if not isinstance(chain_of_thoughts, str) or not isinstance(
            dependency_analysis, str
        ):
            return self._handle_error("Invalid parameters for 'reasoning'.")

        self.vm.logger.info(
            f"Reasoning step:chain_of_thoughts: {chain_of_thoughts}\n{dependency_analysis}"
        )

        if output_vars:
            self.vm.logger.info(
                f"Not allowed to use output variables in reasoning instruction : {output_vars}"
            )

        self.vm.state["msgs"].append(
            {
                "chain_of_thoughts": chain_of_thoughts,
                "dependency_analysis": dependency_analysis,
            }
        )
        return True
