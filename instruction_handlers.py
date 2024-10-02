from typing import Any, Dict, Optional, List

class InstructionHandlers:
    def __init__(self, vm):
        self.vm = vm

    def retrieve_knowledge_graph_handler(self, params: Dict[str, Any]) -> bool:
        query = self.vm.resolve_parameter(params.get('query'))
        output_var = params.get('output_var')

        if not isinstance(query, str) or not isinstance(output_var, str):
            self.vm.logger.error("Invalid parameters for 'retrieve_knowledge_graph'.")
            self.vm.state['errors'].append("Invalid parameters for 'retrieve_knowledge_graph'.")
            return False

        result = self.vm.instruction_handlers.retrieve_knowledge_graph(query)
        if result is not None:
            self.vm.variables[output_var] = result
            self.vm.logger.info(f"Retrieved knowledge graph data for query '{query}' and stored in '{output_var}'.")
            return True
        else:
            self.vm.logger.error(f"Failed to retrieve knowledge graph data for query '{query}'.")
            self.vm.state['errors'].append(f"Failed to retrieve knowledge graph data for query '{query}'.")
            return False

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
        prompt = self.vm.resolve_parameter(params.get('prompt'))
        context = self.vm.resolve_parameter(params.get('context'))
        output_var = params.get('output_var')

        if not isinstance(prompt, str) or not isinstance(output_var, str):
            self.vm.logger.error("Invalid parameters for 'llm_generate'.")
            self.vm.state['errors'].append("Invalid parameters for 'llm_generate'.")
            return False

        result = self.vm.llm_interface.generate(prompt, context)
        if result is not None:
            self.vm.variables[output_var] = result
            self.vm.logger.info(f"Generated content and stored in '{output_var}'.")
            return True
        else:
            self.vm.logger.error("Failed to generate content using LLM.")
            self.vm.state['errors'].append("Failed to generate content using LLM.")
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
        value = self.vm.resolve_parameter(params.get('value'))
        var_name = params.get('var_name')

        if not isinstance(var_name, str):
            self.vm.logger.error("Invalid variable name for 'assign'.")
            self.vm.state['errors'].append("Invalid variable name for 'assign'.")
            return False

        self.vm.variables[var_name] = value
        self.vm.logger.info(f"Assigned value to variable '{var_name}': {value}")
        
        if var_name == 'result':
            self.vm.state['goal_completed'] = True
            self.vm.logger.info("Goal completed.")
        
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
        return True

    def retrieve_knowledge_graph(self, query: str) -> Optional[Dict[str, Any]]:
        self.vm.logger.info(f"Retrieving knowledge graph data for query: '{query}'")
        knowledge_graph_data = {
            'query': query,
            'data': f"Structured information related to '{query}'"
        }
        return knowledge_graph_data

    def retrieve_knowledge_embedded_chunks(self, embedding_query: str, top_k: int = 5) -> Optional[List[str]]:
        self.vm.logger.info(f"Retrieving top {top_k} embedded chunks for query: '{embedding_query}'")
        embedded_chunks = [f"Chunk {i+1} related to '{embedding_query}'" for i in range(top_k)]
        return embedded_chunks

    def revisit_plan(self) -> None:
        self.vm.logger.info("Revisiting the plan based on new information...")
        adjust_success = self.vm.adjust_plan()
        if adjust_success:
            self.vm.logger.info("Plan adjusted successfully.")
        else:
            self.vm.logger.error("Failed to adjust the plan.")