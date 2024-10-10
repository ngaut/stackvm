import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import copy
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from instruction_handlers import InstructionHandlers
from utils import interpolate_variables, parse_plan, load_state, save_state, StepType
from config import LLM_MODEL, GIT_REPO_PATH, VM_SPEC_PATH, VM_SPEC_CONTENT
from git_manager import GitManager
from prompts import get_generate_plan_prompt
from commit_message_wrapper import commit_message_wrapper  # Add this import
try:
    import git
except ImportError:
    print("GitPython is not installed. Please install it using: pip install GitPython")
    sys.exit(1)


class PlanExecutionVM:
    def __init__(self, repo_path=None, llm_interface=None):
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

        self.llm_interface = llm_interface
        
        # Use the provided repo_path or the default GIT_REPO_PATH
        self.repo_path = repo_path or GIT_REPO_PATH
        self.git_manager = GitManager(self.repo_path)

        # Change the current working directory to the Git repo path
        os.chdir(self.repo_path)

        self.handlers_registered = False
        self.register_handlers()

    def register_handlers(self):
        if not self.handlers_registered:
            self.instruction_handlers = InstructionHandlers(self)
            self.register_instruction('retrieve_knowledge_graph', self.instruction_handlers.retrieve_knowledge_graph_handler)
            self.register_instruction('vector_search', self.instruction_handlers.vector_search_handler)
            self.register_instruction('llm_generate', self.instruction_handlers.llm_generate_handler)
            self.register_instruction('jmp_if', self.instruction_handlers.jmp_if_handler)
            self.register_instruction('jmp', self.instruction_handlers.jmp_handler)
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

    def execute_step_handler(self, step: Dict[str, Any]) -> bool:
        step_type = step.get('type')
        params = step.get('parameters', {})
        seq_no = step.get('seq_no', 'Unknown')
        if not isinstance(step_type, str):
            self.logger.error("Invalid step type.")
            self.state['errors'].append("Invalid step type.")
            return False
        handler = getattr(self.instruction_handlers, f"{step_type}_handler", None)
        if handler:
            success = handler(params)
            if success:
                save_state(self.state, self.repo_path)
                
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
                commit_message_wrapper.set_commit_message(StepType.STEP_EXECUTION, str(seq_no), description)
        
                return success
        else:
            self.logger.warning(f"Unknown instruction: {step_type}")
            return False

    def step(self):
        if self.state['program_counter'] < len(self.state['current_plan']):
            step = self.state['current_plan'][self.state['program_counter']]
            self.logger.info(f"Executing step {self.state['program_counter']}: {step['type']}, seq_no: {step.get('seq_no', 'Unknown')}, plan length: {len(self.state['current_plan'])}")
            try:
                success = self.execute_step_handler(step)
                if not success:
                    self.logger.error(f"Failed to execute step {self.state['program_counter']}: {step['type']}")
                    return False
                if step['type'] not in ("jmp_if", "jmp"):
                    self.state['program_counter'] += 1
                save_state(self.state, self.repo_path)  # Save state after each step
                return True
            except Exception as e:
                self.logger.error(f"Error executing step {self.state['program_counter']}: {str(e)}")
                self.state['errors'].append(f"Error in step {self.state['program_counter']}: {str(e)}")
                return False
        else:
            self.logger.error(f"Program counter ({self.state['program_counter']}) out of range for current plan (length: {len(self.state['current_plan'])})")
            self.state['errors'].append(f"Program counter out of range: {self.state['program_counter']}")
            return False

    def set_variable(self, var_name: str, value: Any) -> None:
        """
        Centralized method to set a variable in the VM's state.
        Logs the assignment and handles goal completion if needed.
        """
        self.state['variables'][var_name] = value
        
        # Mark goal as completed if 'result' is assigned
        if var_name == 'result':
            self.state['goal_completed'] = True
            self.logger.info("Goal has been marked as completed.")

    def get_variable(self, var_name: str) -> Any:
        """
        Centralized method to retrieve a variable's value from the VM's state.
        """
        return self.state['variables'].get(var_name)

    def set_state(self, commit_hash):
        """
        Load the state from a file based on the specific commit point.
        """
        loaded_state = load_state(commit_hash, self.repo_path)
        if loaded_state:
            self.state = loaded_state
            self.logger.info(f"State loaded from commit {commit_hash}")
        else:
            self.logger.error(f"Failed to load state from commit {commit_hash}")

    def find_step_index(self, seq_no: int) -> Optional[int]:
        for index, step in enumerate(self.state['current_plan']):
            if step.get('seq_no') == seq_no:
                return index
        self.logger.error(f"Seq_no {seq_no} not found in the current plan.")
        self.state['errors'].append(f"Seq_no {seq_no} not found in the current plan.")
        return None