from typing import Any, Dict, Optional, List
from utils import interpolate_variables  # Add this import

class InstructionHandlers:
    def __init__(self, vm):
        self.vm = vm

    def retrieve_knowledge_graph_handler(self, params: Dict[str, Any]) -> bool:
        query = params.get('query')
        output_var = params.get('output_var')
        if not query or not output_var:
            self.vm.logger.error("Missing 'query' or 'output_var' in parameters.")
            self.vm.state['errors'].append("Missing 'query' or 'output_var' in parameters.")
            return False

        # Simulate retrieval of data from knowledge graph
        result = f"Simulated knowledge graph data for query '{query}'"
        self.vm.state['variables'][output_var] = result  # Correctly store variable
        self.vm.logger.info(f"Retrieved data for query '{query}' and stored in variable '{output_var}'.")
        return True

    def retrieve_knowledge_embedded_chunks_handler(self, params: Dict[str, Any]) -> bool:
        embedding_query = self.vm.resolve_parameter(params.get('embedding_query'))
        output_var = params.get('output_var')
        top_k = params.get('top_k', 5)

        if not isinstance(embedding_query, str) or not isinstance(output_var, str):
            self.vm.logger.error("Invalid parameters for 'retrieve_knowledge_embedded_chunks'.")
            self.vm.state['errors'].append("Invalid parameters for 'retrieve_knowledge_embedded_chunks'.")
            return False

        result = self.vm.instruction_handlers.retrieve_knowledge_embedded_chunks(embedding_query, top_k)
        if result is not None:
            self.vm.variables[output_var] = result
            self.vm.logger.info(f"Retrieved top {top_k} embedded chunks for query '{embedding_query}' and stored in '{output_var}'.")
            return True
        else:
            self.vm.logger.error(f"Failed to retrieve embedded chunks for query '{embedding_query}'.")
            self.vm.state['errors'].append(f"Failed to retrieve embedded chunks for query '{embedding_query}'.")
            return False

    def llm_generate_handler(self, params: Dict[str, Any]) -> bool:
        prompt = params.get('prompt')
        output_var = params.get('output_var')
        if not prompt or not output_var:
            self.vm.logger.error("Missing 'prompt' or 'output_var' in parameters.")
            self.vm.state['errors'].append("Missing 'prompt' or 'output_var' in parameters.")
            return False

        prompt = interpolate_variables(prompt, self.vm.state['variables'])  # Updated line

        response = self.vm.llm_interface.generate(prompt)
        if response:
            self.vm.state['variables'][output_var] = response  # Updated line
            self.vm.logger.info(f"LLM response stored in variable '{output_var}'.")
            return True
        else:
            self.vm.logger.error("LLM failed to generate a response.")
            self.vm.state['errors'].append("LLM failed to generate a response.")
            return False

    def condition_handler(self, params: Dict[str, Any]) -> bool:
        condition = self.vm.resolve_parameter(params.get('condition'))
        if_true = params.get('if_true', [])
        if_false = params.get('if_false', [])

        if not isinstance(condition, str):
            self.vm.logger.error("Invalid condition for 'condition' instruction.")
            self.vm.state['errors'].append("Invalid condition for 'condition' instruction.")
            return False

        result = self.vm.llm_interface.evaluate_condition(condition)
        if result == 'true':
            return self.vm.execute_subplan(if_true)
        elif result == 'false':
            return self.vm.execute_subplan(if_false)
        else:
            self.vm.logger.error(f"Invalid condition result: {result}")
            self.vm.state['errors'].append(f"Invalid condition result: {result}")
            return False

    def assign_handler(self, params: Dict[str, Any]) -> bool:
        value = params.get('value')
        var_name = params.get('var_name')
        if not var_name:
            self.vm.logger.error("Missing 'var_name' in parameters.")
            self.vm.state['errors'].append("Missing 'var_name' in parameters.")
            return False

        value_resolved = self.vm.resolve_parameter(value)
        self.vm.state['variables'][var_name] = value_resolved  # Updated line
        self.vm.logger.info(f"Assigned value to variable '{var_name}'.")
        return True

    def reasoning_handler(self, params: Dict[str, Any]) -> bool:
        explanation = params.get('explanation')
        dependency_analysis = params.get('dependency_analysis')

        if not isinstance(explanation, str) or not isinstance(dependency_analysis, str):
            self.vm.logger.error("Invalid parameters for 'reasoning'.")
            self.vm.state['errors'].append("Invalid parameters for 'reasoning'.")
            return False

        self.vm.logger.info("Reasoning step:")
        self.vm.logger.info(f"Explanation: {explanation}")
        self.vm.logger.info(f"Dependency Analysis: {dependency_analysis}")
        # update state
        self.vm.state['msgs'].append({
            'explanation': explanation,
            'dependency_analysis': dependency_analysis
        }
        return True

    def revisit_plan(self) -> None:
        self.vm.logger.info("Revisiting the plan based on new information...")
        adjust_success = self.vm.adjust_plan()
        if adjust_success:
            self.vm.logger.info("Plan adjusted successfully.")
        else:
            self.vm.logger.error("Failed to adjust the plan.")