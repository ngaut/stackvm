import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import copy
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from instruction_handlers import InstructionHandlers
from utils import interpolate_variables, parse_plan, load_state, save_state, get_commit_message_schema, StepType
from llm_interface import LLMInterface
from config import LLM_MODEL, GIT_REPO_PATH, VM_SPEC_PATH
from git_manager import GitManager
try:
    import git
except ImportError:
    print("GitPython is not installed. Please install it using: pip install GitPython")
    sys.exit(1)


class PlanExecutionVM:
    def __init__(self, repo_path=None):
        self.state: Dict[str, Any] = {
            'variables': {},
            'errors': [],
            'goal': None,
            'current_plan': [],
            'program_counter': 0,
            'goal_completed': False,
            'msgs': []
        }

        # Initialize logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        self.llm_interface = LLMInterface(LLM_MODEL)
        
        # Use the provided repo_path or the default GIT_REPO_PATH
        self.repo_path = repo_path or GIT_REPO_PATH
        self.git_manager = GitManager(self.repo_path)
        self.commit_message = None  # New attribute to store commit message

        # Change the current working directory to the Git repo path
        os.chdir(self.repo_path)

        self.handlers_registered = False
        self.register_handlers()

    def register_handlers(self):
        if not self.handlers_registered:
            self.instruction_handlers = InstructionHandlers(self)
            self.register_instruction('retrieve_knowledge_graph', self.instruction_handlers.retrieve_knowledge_graph_handler)
            self.register_instruction('retrieve_knowledge_embedded_chunks', self.instruction_handlers.retrieve_knowledge_embedded_chunks_handler)
            self.register_instruction('llm_generate', self.instruction_handlers.llm_generate_handler)
            self.register_instruction('condition', self.instruction_handlers.condition_handler)
            self.register_instruction('assign', self.instruction_handlers.assign_handler)
            self.register_instruction('reasoning', self.instruction_handlers.reasoning_handler)
            self.handlers_registered = True

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

    def set_goal(self, goal: str) -> None:
        self.state['goal'] = goal
        self.logger.info(f"Goal set: {goal}")
        save_state(self.state, self.repo_path)

    def resolve_parameter(self, param):
        if isinstance(param, dict) and 'var' in param:
            var_name = param['var']
            value = self.state['variables'].get(var_name)
            self.logger.info(f"Resolved variable '{var_name}' to value: {value}")
            return value
        elif isinstance(param, str):
            return interpolate_variables(param, self.state['variables'])
        else:
            return param

    def _set_commit_message(self, step_type: StepType, seq_no: str, description: str) -> None:
        self.commit_message = get_commit_message_schema(step_type.value, seq_no, description, {}, {})  # Use the enum value

    def execute_step_handler(self, step: Dict[str, Any]) -> bool:
        step_type = step.get('type')
        params = step.get('parameters', {})
        seq_no = step.get('seq_no', 'Unknown')  # Ensure this is set correctly
        if not isinstance(step_type, str):
            self.logger.error("Invalid step type.")
            self.state['errors'].append("Invalid step type.")
            return False
        handler = getattr(self.instruction_handlers, f"{step_type}_handler", None)
        if handler:
            success = handler(params)
            if success:
                save_state(self.state, self.repo_path)
                self.logger.info(f"Saved VM state after executing step {self.state['program_counter']}")
        
                self.logger.debug(f"Current Variables: {json.dumps(self.state['variables'], indent=2)}")
        
                input_parameters = {}
                for k, v in params.items():
                    value_preview = str(v)[:50] + '...' if len(str(v)) > 50 else str(v)
                    input_parameters[k] = value_preview
        
                output_vars = params.get('output_var')
                if isinstance(output_vars, str):
                    output_vars = [output_vars]
                elif not isinstance(output_vars, list):
                    output_vars = []
                output_variables = {}
                for k in output_vars:
                    v = self.state['variables'].get(k)
                    value_preview = str(v)[:50] + '...' if len(str(v)) > 50 else str(v)
                    output_variables[k] = value_preview
            
                # Set a meaningful description for the commit message
                description = f"Executed step '{step_type}' with parameters: {json.dumps(input_parameters)}"
                self._set_commit_message(StepType.STEP_EXECUTION, str(seq_no), description)  # Use the enum value
        
                return success
        else:
            self.logger.warning(f"Unknown instruction: {step_type}")
            return False

    def execute_subplan(self, subplan: List[Dict[str, Any]]) -> bool:
        self.logger.info("Executing subplan.")
        for step in subplan:
            success = self.execute_step_handler(step)
            if not success:
                self.logger.error("Subplan execution failed.")
                self.state['errors'].append("Subplan execution failed.")
                
                # Commit subplan failure to Git
                description = f"Subplan execution failed at step: {step.get('type')}"
                self._set_commit_message(StepType.PLAN_UPDATE, "Unknown", description)  # Use the enum
                if not self.git_manager.commit_changes(self.commit_message):
                    self.logger.error("Failed to commit changes to Git.")
                    # Handle the failure as needed
                
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
        with open(VM_SPEC_PATH, 'r') as file:
            prompt += "the content of spec.md is:\n\n" + file.read()

        plan_response = self.llm_interface.generate(prompt)
        
        if not plan_response:
            self.logger.error("LLM failed to generate a response.")
            self.state['errors'].append("LLM failed to generate a response.")
            return False
        
        plan = parse_plan(plan_response)
        
        if plan:
            # Create a new branch for the plan
            branch_name = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            try:
                if not self.git_manager.create_branch(branch_name):
                    self.logger.error(f"Failed to create branch '{branch_name}'.")
                    return False

                if not self.git_manager.checkout_branch(branch_name):
                    self.logger.error(f"Failed to checkout branch '{branch_name}'.")
                    return False
            except Exception as e:
                self.logger.error(f"Error in Git operations: {str(e)}")
                return False

            # Save the plan in the state and commit
            self.state['current_plan'] = plan
            self.logger.info("Plan generated and parsed successfully.")

            # Save state and commit the generated plan to Git
            save_state(self.state, self.repo_path)
            self._set_commit_message(StepType.GENERATE_PLAN, "0", f"Generated new plan on branch '{branch_name}'")  # Use the enum
            return True
        else:
            self.logger.error("Failed to parse the generated plan.")
            self.state['errors'].append("Failed to parse the generated plan.")
            return False

    def step(self):
        if self.state['program_counter'] < len(self.state['current_plan']):
            step = self.state['current_plan'][self.state['program_counter']]
            self.logger.info(f"Executing step {self.state['program_counter']}: {step['type']}")
            try:
                success = self.execute_step_handler(step)
                if not success:
                    self.logger.error(f"Failed to execute step {self.state['program_counter']}: {step['type']}")
                    return False
            except Exception as e:
                self.logger.error(f"Error executing step {self.state['program_counter']}: {str(e)}")
                self.state['errors'].append(f"Error in step {self.state['program_counter']}: {str(e)}")
                return False
            self.state['program_counter'] += 1
            save_state(self.state, self.repo_path)  # Save state after each step
            return True
        else:
            self.logger.info("Program execution complete.")
            return False

    def set_variable(self, var_name: str, value: Any) -> None:
        """
        Centralized method to set a variable in the VM's state.
        Logs the assignment and handles goal completion if needed.
        """
        self.state['variables'][var_name] = value
        self.logger.info(f"Variable '{var_name}' set to '{value}'.")
        
        # Mark goal as completed if 'result' is assigned
        if var_name == 'result':
            self.state['goal_completed'] = True
            self.logger.info("Goal has been marked as completed.")

    def get_variable(self, var_name: str) -> Any:
        """
        Centralized method to retrieve a variable's value from the VM's state.
        """
        return self.state['variables'].get(var_name)

    def load_state(self, commit_hash):
        """
        Load the state from a file based on the specific commit point.
        """
        loaded_state = load_state(commit_hash, self.repo_path)
        if loaded_state:
            self.state = loaded_state
            self.logger.info(f"State loaded from commit {commit_hash}")
        else:
            self.logger.error(f"Failed to load state from commit {commit_hash}")