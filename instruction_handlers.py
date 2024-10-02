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

        result = self.retrieve_knowledge_graph(query)
        if result is None:
            return False

        self.vm.variables[output_var] = result
        self.vm.logger.info(f"Stored result in variable '{output_var}'.")
        self.vm.save_milestone("AfterKnowledgeGraphRetrieval")
        return True

    def retrieve_knowledge_embedded_chunks_handler(self, params: Dict[str, Any]) -> bool:
        embedding_query = self.vm.resolve_parameter(params.get('embedding_query'))
        top_k = self.vm.resolve_parameter(params.get('top_k'))
        output_var = params.get('output_var')

        if not isinstance(embedding_query, str) or not isinstance(top_k, int) or not isinstance(output_var, str):
            self.vm.logger.error("Invalid parameters for 'retrieve_knowledge_embedded_chunks'.")
            self.vm.state['errors'].append("Invalid parameters for 'retrieve_knowledge_embedded_chunks'.")
            return False

        result = self.retrieve_knowledge_embedded_chunks(embedding_query, top_k)
        if result is None:
            return False

        self.vm.variables[output_var] = result
        self.vm.logger.info(f"Stored result in variable '{output_var}'.")
        self.vm.save_milestone("AfterEmbeddedChunksRetrieval")
        return True

    def llm_generate_handler(self, params: Dict[str, Any]) -> bool:
        prompt = self.vm.resolve_parameter(params.get('prompt'))
        context = self.vm.resolve_parameter(params.get('context'))
        output_var = params.get('output_var')

        if not isinstance(prompt, str) or not isinstance(output_var, str):
            self.vm.logger.error("Invalid parameters for 'llm_generate'.")
            self.vm.state['errors'].append("Invalid parameters for 'llm_generate'.")
            return False

        result = self.vm.llm_interface.generate(prompt, context)
        if result is None:
            return False

        self.vm.variables[output_var] = result
        self.vm.logger.info(f"Stored LLM output in variable '{output_var}'.")
        self.vm.save_milestone("AfterLLMGeneration")
        return True

    def condition_handler(self, params: Dict[str, Any]) -> bool:
        condition_prompt = self.vm.resolve_parameter(params.get('prompt'))
        context = self.vm.resolve_parameter(params.get('context'))
        true_branch = params.get('true_branch')
        false_branch = params.get('false_branch')

        if not isinstance(condition_prompt, str):
            self.vm.logger.error("Invalid condition prompt for 'condition'.")
            self.vm.state['errors'].append("Invalid condition prompt for 'condition'.")
            return False
        if not isinstance(true_branch, list) or not isinstance(false_branch, list):
            self.vm.logger.error("Invalid branches for 'condition'.")
            self.vm.state['errors'].append("Invalid branches for 'condition'.")
            return False

        condition_result = self.vm.llm_interface.evaluate_condition(condition_prompt, context)
        if condition_result is None:
            return False

        if condition_result.lower() == 'true':
            self.vm.logger.info("Condition evaluated to True. Executing true_branch.")
            return self.vm.execute_subplan(true_branch)
        else:
            self.vm.logger.info("Condition evaluated to False. Executing false_branch.")
            return self.vm.execute_subplan(false_branch)

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

    def reasoning_handler(self, params: Dict[str, Any]) -> bool:
        explanation = params.get('explanation')
        dependency_analysis = params.get('dependency_analysis')

        if not isinstance(explanation, str):
            self.vm.logger.error("Invalid explanation for 'reasoning'.")
            self.vm.state['errors'].append("Invalid explanation for 'reasoning'.")
            return False

        if dependency_analysis and not isinstance(dependency_analysis, (str, dict, list)):
            self.vm.logger.error("Invalid dependency analysis for 'reasoning'.")
            self.vm.state['errors'].append("Invalid dependency analysis for 'reasoning'.")
            return False

        self.vm.logger.info(f"Plan reasoning: {explanation}")
        if dependency_analysis:
            self.vm.logger.info(f"Dependency analysis: {dependency_analysis}")

        return True