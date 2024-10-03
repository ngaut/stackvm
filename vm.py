import copy
import json
import logging
from typing import Any, Dict, List, Optional

from instruction_handlers import InstructionHandlers
from utils import interpolate_variables, parse_plan
from llm_interface import LLMInterface
from config import LLM_MODEL

class PlanExecutionVM:
    def __init__(self):
        self.variables: Dict[str, Any] = {}
        self.state: Dict[str, Any] = {
            'milestones': {},
            'errors': [],
            'previous_plans': [],
            'goal': None,
            'current_plan': [],
            'program_counter': 0,
            'goal_completed': False
        }

        # Initialize logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        self.instruction_handlers = InstructionHandlers(self)
        self.llm_interface = LLMInterface(LLM_MODEL)

        # Register instruction handlers
        self.register_instruction('retrieve_knowledge_graph', self.instruction_handlers.retrieve_knowledge_graph_handler)
        self.register_instruction('retrieve_knowledge_embedded_chunks', self.instruction_handlers.retrieve_knowledge_embedded_chunks_handler)
        self.register_instruction('llm_generate', self.instruction_handlers.llm_generate_handler)
        self.register_instruction('condition', self.instruction_handlers.condition_handler)
        self.register_instruction('assign', self.instruction_handlers.assign_handler)
        self.register_instruction('reasoning', self.instruction_handlers.reasoning_handler)

    def set_goal(self, goal: str) -> None:
        if not isinstance(goal, str):
            self.logger.error("Goal must be a string.")
            self.state['errors'].append("Goal must be a string.")
            return
        self.state['goal'] = goal
        self.logger.info(f"Goal set: {goal}")

    def save_milestone(self, name: str) -> None:
        if not isinstance(name, str):
            self.logger.error("Milestone name must be a string.")
            self.state['errors'].append("Milestone name must be a string.")
            return
        self.state['milestones'][name] = {
            'variables': copy.deepcopy(self.variables),
            'program_counter': self.state['program_counter']
        }
        self.logger.info(f"Milestone '{name}' saved.")

    def load_milestone(self, name: str) -> None:
        if not isinstance(name, str):
            self.logger.error("Milestone name must be a string.")
            self.state['errors'].append("Milestone name must be a string.")
            return
        if name in self.state['milestones']:
            milestone = self.state['milestones'][name]
            self.variables = copy.deepcopy(milestone['variables'])
            self.state['program_counter'] = milestone['program_counter']
            self.logger.info(f"Milestone '{name}' loaded.")
        else:
            self.logger.error(f"Milestone '{name}' does not exist.")
            self.state['errors'].append(f"Milestone '{name}' does not exist.")

    def resolve_parameter(self, param):
        if isinstance(param, dict) and 'var' in param:
            var_name = param['var']
            value = self.variables.get(var_name)
            self.logger.info(f"Resolved variable '{var_name}' to value: {value}")
            return value
        elif isinstance(param, str):
            return interpolate_variables(param, self.variables)
        else:
            return param

    def execute_step_handler(self, step: Dict[str, Any]) -> bool:
        step_type = step.get('type')
        params = step.get('parameters', {})
        if not isinstance(step_type, str):
            self.logger.error("Invalid step type.")
            self.state['errors'].append("Invalid step type.")
            return False
        handler = getattr(self.instruction_handlers, f"{step_type}_handler", None)
        if handler:
            return handler(params)
        else:
            self.logger.warning(f"Unknown instruction: {step_type}")
            return False

    def execute_plan(self, plan: List[Dict[str, Any]]) -> bool:
        self.logger.info("Starting plan execution.")
        for index, step in enumerate(plan):
            self.state['program_counter'] = index
            success = self.execute_step_handler(step)
            if not success:
                self.logger.error(f"Execution failed at step {index}.")
                self.state['errors'].append(f"Execution failed at step {index}.")
                return False
            if self.state['goal_completed']:
                self.logger.info("Goal completed during plan execution.")
                return True
        self.logger.info("Plan executed successfully.")
        return True

    def execute_subplan(self, subplan: List[Dict[str, Any]]) -> bool:
        self.logger.info("Executing subplan.")
        for step in subplan:
            success = self.execute_step_handler(step)
            if not success:
                self.logger.error("Subplan execution failed.")
                self.state['errors'].append("Subplan execution failed.")
                return False
            if self.state['goal_completed']:
                break
        return True

    def generate_plan(self) -> bool:
        if not self.state['goal']:
            self.logger.error("No goal is set.")
            self.state['errors'].append("No goal is set.")
            return False

        self.logger.info("Generating plan using LLM.")
        prompt = f"""You are an intelligent assistant designed to analyze user queries and retrieve information from a knowledge graph multiple times. For the following goal, please:

1. Analyze the requester's intent and the requester's query:
   - Analyze and list the prerequisites of the query.
   - Analyze and list the assumptions of the query. 
   
2. Break Down query into sub-queries:
   - Each sub-query must be smaller, specific, retrievable with existing tools, and no further reasoning is required to achieve it.
   - Identify dependencies between sub-queries and draw a dependency graph.

3. Generate an Action Plan:
   - For each sub-query (Assumptions included), create a corresponding action step to achieve it.
   - Ensure the plan follows the format specified in the spec.md file.
   - Include a 'reasoning' step at the beginning of the plan that explains the overall approach and provides a dependency analysis of the steps.

Goal: {self.state['goal']}

Please provide your response as a JSON array of instruction steps, where each step has a 'type' and 'parameters'. 
The final step should assign the result to the 'result' variable. The 'reasoning' step should include both 'explanation' and 'dependency_analysis' parameters.

"""
        with open('spec.md', 'r') as file:
            prompt += "the content of spec.md is:\n\n" + file.read()

        plan_response = self.llm_interface.generate(prompt)
        
        if not plan_response:
            self.logger.error("LLM failed to generate a response.")
            self.state['errors'].append("LLM failed to generate a response.")
            return False
        
        plan = parse_plan(plan_response)
        
        if plan:
            self.state['current_plan'] = plan
            self.state['previous_plans'].append(plan)
            self.save_milestone("AfterPlanGeneration")
            self.logger.info("Plan generated and parsed successfully.")
            return True
        else:
            self.logger.error("Failed to parse the generated plan.")
            self.state['errors'].append("Failed to parse the generated plan.")
            return False

    def adjust_plan(self) -> bool:
        self.logger.info("Adjusting plan based on errors and context.")
        context_info = {
            'errors': self.state['errors'],
            'milestones': list(self.state['milestones'].keys()),
            'previous_plans': len(self.state['previous_plans'])
        }
        prompt = f"""You are an intelligent assistant designed to analyze and adjust plans. Given the following context and the original goal, please generate an adjusted plan:

1. Original Goal: {self.state['goal']}
2. Context Information:
   {json.dumps(context_info, indent=2)}

3. Current Plan:
   {json.dumps(self.state['current_plan'], indent=2)}

Please provide an adjusted plan that addresses the errors and follows the format specified in the spec.md file. The plan should be a JSON array of instruction steps, where each step has a 'type' and 'parameters'. The final step should assign the result to the 'result' variable.

Include a 'reasoning' step at the beginning of the plan that explains the adjustments made and provides a dependency analysis of the steps.

Ensure that the plan adheres to the following guidelines from spec.md:
1. Use supported instruction types: assign, llm_generate, retrieve_knowledge_graph, retrieve_knowledge_embedded_chunks, condition, and reasoning.
2. Follow the correct parameter structure for each instruction type.
3. Use variable references where appropriate, using the format {{"var": "variable_name"}}.
4. Include error handling and conditional logic where necessary.
5. Maintain a logical flow and dependencies between steps.

Provide your response as a valid JSON array of instruction steps.
"""

        with open('spec.md', 'r') as file:
            prompt += "\n\nFor reference, here is the content of spec.md:\n\n" + file.read()

        plan_response = self.llm_interface.generate(prompt)
        if not plan_response:
            self.logger.error("LLM failed to generate an adjusted plan.")
            self.state['errors'].append("LLM failed to generate an adjusted plan.")
            return False

        new_plan = parse_plan(plan_response)
        if new_plan:
            self.state['current_plan'] = new_plan
            self.state['previous_plans'].append(new_plan)
            self.save_milestone("AfterPlanAdjustment")
            self.state['errors'] = []
            self.logger.info("Plan adjusted successfully.")
            return True
        else:
            self.logger.error("Failed to parse the adjusted plan.")
            self.state['errors'].append("Failed to parse the adjusted plan.")
            return False

    def update_plan(self, new_plan: List[Dict[str, Any]]) -> None:
        """
        Updates the current plan with a new plan.
        """
        if new_plan:
            self.state['current_plan'] = new_plan
            self.state['previous_plans'].append(new_plan)
            self.save_milestone("AfterPlanUpdate")
            self.logger.info("Plan updated successfully.")
        else:
            self.logger.info("No changes to the current plan.")

    def run(self) -> None:
        max_iterations = 5
        iterations = 0

        while not self.state['goal_completed'] and iterations < max_iterations:
            self.logger.info(f">>>>>>>>>>>>>>>>>>>>Iteration {iterations}>>>>>>>>>>>>>>>>>>>")

            iterations += 1

            if not self.state['goal']:
                self.logger.error("No goal is set.")
                self.state['errors'].append("No goal is set.")
                break

            execution_success = self.execute_plan(self.state['current_plan'])
            if not execution_success:
                self.logger.error("Execution failed. Adjusting plan based on errors.")
                self.state['errors'].append("Execution failed. Adjusting plan based on errors.")
                adjust_success = self.adjust_plan()
                if not adjust_success:
                    self.logger.error("Failed to adjust the plan. Stopping execution.")
                    self.state['errors'].append("Failed to adjust the plan. Stopping execution.")
                    break
            
            if self.state['goal_completed']:
                self.logger.info("Goal achieved successfully.")
                break

        if iterations >= max_iterations:
            self.logger.error("Maximum iterations reached without achieving the goal.")
            self.state['errors'].append("Maximum iterations reached without achieving the goal.")

        result = self.variables.get('result')
        if result:
            result = interpolate_variables(result, self.variables)
            print(f"\nFinal Result: {result}")
        else:
            print("\nNo result was generated.")

    def reset_state(self) -> None:
        self.variables = {}
        self.state['program_counter'] = 0
        self.state['errors'] = []
        self.state['goal_completed'] = False
        self.logger.info("State has been reset.")

    def register_instruction(self, instruction_name: str, handler_method):
        """
        Registers an instruction handler.
        """
        if not isinstance(instruction_name, str) or not callable(handler_method):
            self.logger.error("Invalid instruction registration.")
            self.state['errors'].append("Invalid instruction registration.")
            return
        setattr(self.instruction_handlers, f"{instruction_name}_handler", handler_method)
        self.logger.info(f"Registered handler for instruction: {instruction_name}")

    def get_current_state(self) -> Dict[str, Any]:
        """
        Returns the current state of the VM.
        """
        return {
            'variables': self.variables,
            'state': self.state,
            'program_counter': self.state['program_counter'],
            'errors': self.state['errors'],
            'goal': self.state['goal'],
            'current_plan': self.state['current_plan'],
            'goal_completed': self.state['goal_completed']
        }

if __name__ == "__main__":
    vm = PlanExecutionVM()
    vm.set_goal("summary the performance improvement of tidb from version 6.5 to newest version")
    
    if vm.generate_plan():
        print("Generated Plan:")
        print(json.dumps(vm.state['current_plan'], indent=2))
        vm.run()
    else:
        print("Failed to generate plan.")