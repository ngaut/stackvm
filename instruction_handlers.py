from typing import Any, Dict, Optional, List
from utils import interpolate_variables  # Add this import

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

        result = f"Simulated knowledge graph data for query '{query}'"
        self.vm.set_variable(output_var, result)
        return True

    def retrieve_knowledge_embedded_chunks_handler(self, params: Dict[str, Any]) -> bool:
        """Handle retrieval of embedded chunks."""
        embedding_query = self.vm.resolve_parameter(params.get('embedding_query'))
        output_var = params.get('output_var')
        top_k = params.get('top_k', 5)

        if not isinstance(embedding_query, str) or not isinstance(output_var, str):
            return self._handle_error("Invalid parameters for 'retrieve_knowledge_embedded_chunks'.")

        result = self.vm.retrieve_knowledge_embedded_chunks(embedding_query, top_k)
        if result is not None:
            self.vm.set_variable(output_var, result)
            return True
        return self._handle_error(f"Failed to retrieve embedded chunks for query '{embedding_query}'.")

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
        condition = self.vm.resolve_parameter(params.get('condition'))
        if_true = params.get('if_true', [])
        if_false = params.get('if_false', [])

        if not isinstance(condition, str):
            return self._handle_error("Invalid condition for 'condition' instruction.")

        result = self.vm.llm_interface.evaluate_condition(condition)
        if result == 'true':
            return self.vm.execute_subplan(if_true)
        elif result == 'false':
            return self.vm.execute_subplan(if_false)
        return self._handle_error(f"Invalid condition result: {result}")

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
        explanation = params.get('explanation')
        dependency_analysis = params.get('dependency_analysis')

        if not isinstance(explanation, str) or not isinstance(dependency_analysis, str):
            return self._handle_error("Invalid parameters for 'reasoning'.")

        self.vm.logger.info("Reasoning step:Explanation: {explanation}\n{dependency_analysis}")
        
        self.vm.state['msgs'].append({
            'explanation': explanation,
            'dependency_analysis': dependency_analysis
        })
        return True
