import copy
import json
import logging
import pickle
import time
from typing import Any, Callable, Dict, List, Optional
import openai
import os

# define LLM model
llm_model = "gpt-4o-mini"

class StackVM:
    """
    A Stack-Based Virtual Machine that uses a simplified instruction set to perform various tasks.
    Now with a separate method to generate the plan.
    """

    def __init__(self):
        """
        Initializes the StackVM with default state and sets up the instruction handlers.
        """
        self.stack: List[Any] = []
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
        self.instruction_handlers: Dict[str, Callable] = {}
        self.register_instruction('retrieve_knowledge_graph', self.retrieve_knowledge_graph_handler)
        self.register_instruction('retrieve_knowledge_embedded_chunks', self.retrieve_knowledge_embedded_chunks_handler)
        self.register_instruction('llm_generate', self.llm_generate_handler)
        self.register_instruction('condition', self.condition_handler)
        self.register_instruction('assign', self.assign_handler)

        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d]: %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        # Set up OpenAI API Key
        openai.api_key = os.getenv('OPENAI_API_KEY')
        if not openai.api_key:
            self.logger.error("OpenAI API key not set. Please set the OPENAI_API_KEY environment variable.")
            self.state['errors'].append("OpenAI API key not set. Please set the OPENAI_API_KEY environment variable.")
            raise ValueError("OpenAI API key not set.")
        
        # Initialize OpenAI client
        self.client = openai.OpenAI()

    # Stack Operations
    def push(self, value: Any) -> None:
        """
        Pushes a value onto the stack.
        """
        self.stack.append(value)
        self.logger.info(f"Pushed to stack: {value}")

    def pop(self) -> Optional[Any]:
        """
        Pops a value from the stack.
        """
        if not self.stack:
            self.logger.error("Stack underflow.")
            self.state['errors'].append("Stack underflow.")
            return None
        value = self.stack.pop()
        self.logger.info(f"Popped from stack: {value}")
        return value

    def peek(self) -> Optional[Any]:
        """
        Peeks at the top value of the stack without removing it.
        """
        if not self.stack:
            self.logger.error("Stack is empty.")
            self.state['errors'].append("Stack is empty.")
            return None
        return self.stack[-1]

    # State Management
    def set_goal(self, goal: str) -> None:
        """
        Sets the VM's goal.
        """
        if not isinstance(goal, str):
            self.logger.error("Goal must be a string.")
            self.state['errors'].append("Goal must be a string.")
            return
        self.state['goal'] = goal
        self.logger.info(f"Goal set: {goal}")

    def save_milestone(self, name: str) -> None:
        """
        Saves the current state as a milestone.
        """
        if not isinstance(name, str):
            self.logger.error("Milestone name must be a string.")
            self.state['errors'].append("Milestone name must be a string.")
            return
        self.state['milestones'][name] = {
            'stack': copy.deepcopy(self.stack),
            'variables': copy.deepcopy(self.variables),
            'program_counter': self.state['program_counter']
        }
        self.logger.info(f"Milestone '{name}' saved.")

    def load_milestone(self, name: str) -> None:
        """
        Loads a saved milestone.
        """
        if not isinstance(name, str):
            self.logger.error("Milestone name must be a string.")
            self.state['errors'].append("Milestone name must be a string.")
            return
        if name in self.state['milestones']:
            milestone = self.state['milestones'][name]
            self.stack = copy.deepcopy(milestone['stack'])
            self.variables = copy.deepcopy(milestone['variables'])
            self.state['program_counter'] = milestone['program_counter']
            self.logger.info(f"Milestone '{name}' loaded.")
        else:
            self.logger.error(f"Milestone '{name}' does not exist.")
            self.state['errors'].append(f"Milestone '{name}' does not exist.")

    # Instruction Registration
    def register_instruction(self, instruction_name: str, handler: Callable) -> None:
        """
        Registers an instruction handler.
        """
        if not isinstance(instruction_name, str) or not callable(handler):
            self.logger.error("Invalid instruction registration.")
            self.state['errors'].append("Invalid instruction registration.")
            return
        self.instruction_handlers[instruction_name] = handler

    # Instruction Handlers
    def retrieve_knowledge_graph_handler(self, params: Dict[str, Any]) -> bool:
        """
        Handler for the 'retrieve_knowledge_graph' instruction.
        Uses 'query' parameter, writes output to 'output_var'.
        """
        query = self.resolve_parameter(params.get('query'))
        output_var = params.get('output_var')

        if not isinstance(query, str) or not isinstance(output_var, str):
            self.logger.error("Invalid parameters for 'retrieve_knowledge_graph'.")
            self.state['errors'].append("Invalid parameters for 'retrieve_knowledge_graph'.")
            return False

        # Interpolate variables in the query
        query = self.interpolate_variables(query)

        result = self.retrieve_knowledge_graph(query)
        if result is None:
            return False

        self.variables[output_var] = result
        self.logger.info(f"Stored result in variable '{output_var}'.")
        self.save_milestone("AfterKnowledgeGraphRetrieval")
        return True

    def retrieve_knowledge_embedded_chunks_handler(self, params: Dict[str, Any]) -> bool:
        """
        Handler for the 'retrieve_knowledge_embedded_chunks' instruction.
        Uses 'embedding_query', 'top_k', writes output to 'output_var'.
        """
        embedding_query = self.resolve_parameter(params.get('embedding_query'))
        top_k = self.resolve_parameter(params.get('top_k'))
        output_var = params.get('output_var')

        if not isinstance(embedding_query, str) or not isinstance(top_k, int) or not isinstance(output_var, str):
            self.logger.error("Invalid parameters for 'retrieve_knowledge_embedded_chunks'.")
            self.state['errors'].append("Invalid parameters for 'retrieve_knowledge_embedded_chunks'.")
            return False

        result = self.retrieve_knowledge_embedded_chunks(embedding_query, top_k)
        if result is None:
            return False

        self.variables[output_var] = result
        self.logger.info(f"Stored result in variable '{output_var}'.")
        self.save_milestone("AfterEmbeddedChunksRetrieval")
        return True

    def llm_generate_handler(self, params: Dict[str, Any]) -> bool:
        """
        Handler for the 'llm_generate' instruction.
        Uses 'prompt', 'context', writes output to 'output_var'.
        """
        prompt = self.resolve_parameter(params.get('prompt'))
        context = self.resolve_parameter(params.get('context'))
        output_var = params.get('output_var')

        if not isinstance(prompt, str) or not isinstance(output_var, str):
            self.logger.error("Invalid parameters for 'llm_generate'.")
            self.state['errors'].append("Invalid parameters for 'llm_generate'.")
            return False

        result = self.llm_generate(prompt, context)
        if result is None:
            return False

        self.variables[output_var] = result
        self.logger.info(f"Stored LLM output in variable '{output_var}'.")
        self.save_milestone("AfterLLMGeneration")
        return True

    def condition_handler(self, params: Dict[str, Any]) -> bool:
        """
        Handler for the 'condition' instruction.
        Evaluates a condition using the LLM and executes a branch.
        """
        condition_prompt = self.resolve_parameter(params.get('prompt'))
        context = self.resolve_parameter(params.get('context'))
        true_branch = params.get('true_branch')
        false_branch = params.get('false_branch')

        if not isinstance(condition_prompt, str):
            self.logger.error("Invalid condition prompt for 'condition'.")
            self.state['errors'].append("Invalid condition prompt for 'condition'.")
            return False
        if not isinstance(true_branch, list) or not isinstance(false_branch, list):
            self.logger.error("Invalid branches for 'condition'.")
            self.state['errors'].append("Invalid branches for 'condition'.")
            return False

        # Evaluate the condition using the LLM
        condition_result = self.evaluate_condition(condition_prompt, context)
        if condition_result is None:
            return False

        # Decide which branch to execute
        if condition_result.lower() == 'true':
            self.logger.info("Condition evaluated to True. Executing true_branch.")
            return self.execute_subplan(true_branch)
        else:
            self.logger.info("Condition evaluated to False. Executing false_branch.")
            return self.execute_subplan(false_branch)

    def assign_handler(self, params: Dict[str, Any]) -> bool:
        """
        Handler for the 'assign' instruction.
        Assigns a value to a variable.
        """
        value = self.resolve_parameter(params.get('value'))
        var_name = params.get('var_name')

        if not isinstance(var_name, str):
            self.logger.error("Invalid variable name for 'assign'.")
            self.state['errors'].append("Invalid variable name for 'assign'.")
            return False

        # If the value is a string, replace any variable placeholders
        if isinstance(value, str):
            for var, var_value in self.variables.items():
                value = value.replace(f"{{{{{var}}}}}", str(var_value))

        self.variables[var_name] = value
        self.logger.info(f"Assigned value to variable '{var_name}': {value}")
        
        # If we're assigning to the 'result' variable, consider the goal completed
        if var_name == 'result':
            self.state['goal_completed'] = True
            self.logger.info("Goal completed.")
        
        return True

    # Instruction Implementations
    def retrieve_knowledge_graph(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves information from the knowledge graph based on a query.
        """
        self.logger.info(f"Retrieving knowledge graph data for query: '{query}'")
        # Simulate retrieval (Replace with actual implementation if available)
        knowledge_graph_data = {
            'query': query,
            'data': f"Structured information related to '{query}'"
        }
        return knowledge_graph_data

    def retrieve_knowledge_embedded_chunks(self, embedding_query: str, top_k: int = 5) -> Optional[List[str]]:
        """
        Retrieves embedded knowledge chunks based on an embedding query.
        """
        self.logger.info(f"Retrieving top {top_k} embedded chunks for query: '{embedding_query}'")
        # Simulate retrieval (Replace with actual implementation if available)
        embedded_chunks = [f"Chunk {i+1} related to '{embedding_query}'" for i in range(top_k)]
        return embedded_chunks

    def llm_generate(self, prompt: str, context: Optional[str] = None) -> Optional[str]:
        """
        Generates a response using the LLM.
        """
        self.logger.info(f"Generating response from LLM for prompt: '{prompt}'")
        if context:
            self.logger.info(f"With context: '{context}'")
            full_prompt = f"{context}\n{prompt}"
        else:
            full_prompt = prompt

        # Interpolate variables in the prompt
        for var, value in self.variables.items():
            full_prompt = full_prompt.replace(f"{{{{{var}}}}}", str(value))

        try:
            response = self.client.chat.completions.create(
                model=llm_model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0
            )
            result = response.choices[0].message.content.strip()
            return result
        except Exception as e:
            self.logger.error(f"LLM generation failed: {e}")
            self.state['errors'].append(f"LLM generation failed: {e}")
            return None

    def evaluate_condition(self, prompt: str, context: Optional[str] = None) -> Optional[str]:
        """
        Evaluates a condition using the LLM. Expects 'true' or 'false' as response.
        """
        self.logger.info(f"Evaluating condition with prompt: '{prompt}'")
        if context:
            self.logger.info(f"With context: '{context}'")
            full_prompt = f"{context}\n{prompt}"
        else:
            full_prompt = prompt

        try:
            response = self.client.chat.completions.create(
                model=llm_model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Respond with 'true' or 'false' only."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0
            )
            result = response.choices[0].message.content.strip().lower()
            if result in ['true', 'false']:
                return result
            else:
                self.logger.error(f"Invalid condition response: '{result}'. Expected 'true' or 'false'.")
                self.state['errors'].append(f"Invalid condition response: '{result}'. Expected 'true' or 'false'.")
                return None
        except Exception as e:
            self.logger.error(f"Condition evaluation failed: {e}")
            self.state['errors'].append(f"Condition evaluation failed: {e}")
            return None

    # Helper Methods
    def resolve_parameter(self, param):
        """
        Resolves a parameter that may be a direct value or a variable reference.
        """
        if isinstance(param, dict) and 'var' in param:
            var_name = param['var']
            value = self.variables.get(var_name)
            self.logger.info(f"Resolved variable '{var_name}' to value: {value}")
            return value
        else:
            return param

    # Step Execution
    def execute_step_handler(self, step: Dict[str, Any]) -> bool:
        """
        Executes a single step in the plan using the appropriate instruction handler.
        """
        step_type = step.get('type')
        params = step.get('parameters', {})
        if not isinstance(step_type, str):
            self.logger.error("Invalid step type.")
            self.state['errors'].append("Invalid step type.")
            return False
        handler = self.instruction_handlers.get(step_type)
        if handler:
            return handler(params)
        else:
            self.logger.warning(f"Unknown instruction: {step_type}")
            return False

    # Plan Execution
    def execute_plan(self, plan: List[Dict[str, Any]]) -> bool:
        """
        Executes the given plan step by step.
        """
        self.logger.info("Starting plan execution.")
        for index in range(len(plan)):
            self.state['program_counter'] = index
            step = plan[index]
            success = self.execute_step_handler(step)
            if not success:
                self.logger.error(f"Execution failed at step {index}.")
                self.state['errors'].append(f"Execution failed at step {index}.")
                return False
            # Check if goal is completed during execution
            if self.state['goal_completed']:
                self.logger.info("Goal completed during plan execution.")
                return True
        self.logger.info("Plan executed successfully.")
        return True

    def execute_subplan(self, subplan: List[Dict[str, Any]]) -> bool:
        """
        Executes a subplan.
        """
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

    # Plan Generation
    def generate_plan(self) -> bool:
        """
        Generates a plan using the LLM and stores it in the VM's state.
        """
        if not self.state['goal']:
            self.logger.error("No goal is set.")
            self.state['errors'].append("No goal is set.")
            return False

        self.logger.info("Generating plan using LLM.")
        prompt = f"Generate a plan in JSON format to achieve the goal: '{self.state['goal']}'. The plan should be a list of steps with 'type', 'parameters', and use variables for dependencies. Ensure the response is valid JSON."
        
        # Append the spec of the vm to the prompt
        with open('spec.md', 'r') as file:
            prompt += "\n\n" + file.read()
        
        plan_response = self.llm_generate(prompt)
        
        if not plan_response:
            self.logger.error("LLM failed to generate a response.")
            self.state['errors'].append("LLM failed to generate a response.")
            return False
        
        # Attempt to extract JSON from the response
        try:
            # Find the first occurrence of '[' and the last occurrence of ']'
            start = plan_response.find('[')
            end = plan_response.rfind(']')
            
            if start != -1 and end != -1 and start < end:
                json_str = plan_response[start:end+1]
                plan = json.loads(json_str)
            else:
                raise ValueError("No valid JSON array found in the response")
            
            if not isinstance(plan, list):
                raise ValueError("Parsed plan is not a list")
            
            # Modify the plan to assign to 'result' if necessary
            if plan and isinstance(plan, list):
                for step in plan:
                    if (step.get('type') == 'assign' and
                            step.get('parameters', {}).get('var_name') == 'final_summary'):
                        step['parameters']['var_name'] = 'result'
            
            self.state['current_plan'] = plan
            self.state['previous_plans'].append(plan)
            self.save_milestone("AfterPlanGeneration")
            self.logger.info("Plan generated and parsed successfully.")
            return True
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse plan: {e}")
            self.state['errors'].append(f"Failed to parse plan: {e}")
            self.logger.error(f"Raw response: {plan_response}")
        except ValueError as e:
            self.logger.error(f"Invalid plan structure: {e}")
            self.state['errors'].append(f"Invalid plan structure: {e}")
            self.logger.error(f"Raw response: {plan_response}")
        
        return False

    # Plan Adjustment
    def adjust_plan(self) -> bool:
        """
        Adjusts the plan based on errors and current context.
        """
        self.logger.info("Adjusting plan based on errors and context.")
        errors = '\n'.join(self.state['errors'])
        context_info = {
            'errors': self.state['errors'],
            'milestones': list(self.state['milestones'].keys()),
            'previous_plans': len(self.state['previous_plans'])
        }
        prompt = f"Given the goal '{self.state['goal']}' and the following context:\n{context_info}\nGenerate an adjusted plan in JSON format that includes variable assignments and references."
        plan_response = self.llm_generate(prompt)
        if not plan_response:
            return False
        new_plan = self.parse_plan(plan_response)
        if new_plan:
            self.state['current_plan'] = new_plan
            self.state['previous_plans'].append(new_plan)
            self.save_milestone("AfterPlanAdjustment")
            self.state['errors'] = []  # Reset errors after plan adjustment
            return True
        else:
            self.logger.error("Failed to adjust the plan.")
            self.state['errors'].append("Failed to adjust the plan.")
            return False

    # VM Run Loop
    def run(self) -> None:
        """
        Starts the VM's execution loop to achieve the goal.
        """
        max_iterations = 5  # Prevent infinite loops
        iterations = 0

        while not self.state['goal_completed'] and iterations < max_iterations:
            iterations += 1

            if not self.state['goal']:
                self.logger.error("No goal is set.")
                self.state['errors'].append("No goal is set.")
                break

            # Plan Execution
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

        # Output the final result
        result = self.variables.get('result')
        if result:
            # Replace any remaining variable placeholders
            for var, var_value in self.variables.items():
                result = result.replace(f"{{{{{var}}}}}", str(var_value))
            #print(f"\nFinal Result: {result}")
        else:
            print("\nNo result was generated.")

    # Plan Parsing
    def parse_plan(self, plan_response: str) -> Optional[List[Dict[str, Any]]]:
        """
        Parses the LLM's response into an executable plan.
        """
        try:
            # Assuming the response is JSON formatted
            plan = json.loads(plan_response)
            if not isinstance(plan, list):
                self.logger.error("Parsed plan is not a list.")
                self.state['errors'].append("Parsed plan is not a list.")
                return None
            self.logger.info("Plan parsed successfully.")
            return plan
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse plan: {e}")
            self.state['errors'].append(f"Failed to parse plan: {e}")
            return None

    # State Persistence
    def save_state(self, filename: str) -> None:
        """
        Saves the VM's state to a file.
        """
        try:
            with open(filename, 'wb') as f:
                pickle.dump(self.state, f)
            self.logger.info(f"VM state saved to {filename}.")
        except Exception as e:
            self.logger.error(f"Failed to save state: {e}")
            self.state['errors'].append(f"Failed to save state: {e}")

    def load_state(self, filename: str) -> None:
        """
        Loads the VM's state from a file.
        """
        try:
            with open(filename, 'rb') as f:
                self.state = pickle.load(f)
            self.logger.info(f"VM state loaded from {filename}.")
        except Exception as e:
            self.logger.error(f"Failed to load state: {e}")
            self.state['errors'].append(f"Failed to load state: {e}")

    # Reset State
    def reset_state(self) -> None:
        """
        Resets the VM's state to the initial state.
        """
        self.stack = []
        self.variables = {}
        self.state['program_counter'] = 0
        self.state['errors'] = []
        self.state['goal_completed'] = False
        self.logger.info("State has been reset.")

    # Additional Helper Methods
    def simulate_transient_error(self) -> bool:
        """
        Simulates a transient error randomly.
        """
        import random
        return random.choice([True, False])

    def interpolate_variables(self, text: str) -> str:
        """
        Replaces variable placeholders in a string with their actual values.
        """
        if not isinstance(text, str):
            return text
        for var, value in self.variables.items():
            text = text.replace(f"{{{{{var}}}}}", str(value))
        return text

# Example Usage
if __name__ == "__main__":
    vm = StackVM()
    vm.set_goal("summary the performance improvement of tidb from version 6.5 to newest version")

    # Generate the plan
    if vm.generate_plan():
        # Optionally, inspect or modify the plan here
        print("Generated Plan:")
        print(json.dumps(vm.state['current_plan'], indent=2))

        # Run the VM to execute the plan
        vm.run()

        # Output the final result
        result = vm.variables.get('result')
        if result:
            print(f"\nFinal Result: {result}")
        else:
            print("\nNo result was generated.")
    else:
        print("Failed to generate plan.")