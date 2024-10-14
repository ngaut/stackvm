import json
import logging
import os
from typing import Any, Dict, Optional
from app.tools import InstructionHandlers
from app.services import load_state, save_state, StepType
from app.services import GitManager, commit_message_wrapper, VariableManager

# Constants
DEFAULT_LOGGING_LEVEL = logging.INFO
VARIABLE_PREVIEW_LENGTH = 50

class PlanExecutionVM:
    def __init__(self, repo_path: str, llm_interface: Any = None):
        self.variable_manager = VariableManager()
        self.state: Dict[str, Any] = {
            'errors': [],
            'goal': None,
            'current_plan': [],
            'program_counter': 0,
            'goal_completed': False,
            'msgs': []
        }

        self.logger = self._setup_logger()
        self.llm_interface = llm_interface
        self.repo_path = repo_path
        self.git_manager = GitManager(self.repo_path)

        os.chdir(self.repo_path)

        self.handlers_registered = False
        self.register_handlers()

    def _setup_logger(self) -> logging.Logger:
        """Set up and return a logger for the class."""
        logger = logging.getLogger(__name__)
        logger.setLevel(DEFAULT_LOGGING_LEVEL)
        return logger

    def register_handlers(self) -> None:
        """Register all instruction handlers."""
        if not self.handlers_registered:
            self.instruction_handlers = InstructionHandlers(self)
            handler_methods = [
                'retrieve_knowledge_graph',
                'vector_search',
                'llm_generate',
                'jmp',
                'assign',
                'reasoning'
            ]
            for method in handler_methods:
                self.register_instruction(method, getattr(self.instruction_handlers, f"{method}_handler"))
            self.handlers_registered = True

    def register_instruction(self, instruction_name: str, handler_method: callable) -> None:
        """Register an individual instruction handler."""
        if not isinstance(instruction_name, str) or not callable(handler_method):
            self.logger.error("Invalid instruction registration.")
            self.state['errors'].append("Invalid instruction registration.")
            return
        setattr(self.instruction_handlers, f"{instruction_name}_handler", handler_method)
        self.logger.info(f"Registered handler for instruction: {instruction_name}")

    def set_goal(self, goal: str) -> None:
        """Set the goal for the VM and save the state."""
        self.state['goal'] = goal
        self.logger.info(f"Goal set: {goal}")
        self.save_state()

    def resolve_parameter(self, param: Any) -> Any:
        """Resolve a parameter, interpolating variables if it's a string."""
        vars = self.variable_manager.find_referenced_variables(param)
        for var in vars:
            self.variable_manager.decrease_ref_count(var)
        return self.variable_manager.interpolate_variables(param)

    def execute_step_handler(self, step: Dict[str, Any]) -> bool:
        """Execute a single step in the plan."""
        step_type = step.get('type')
        params = step.get('parameters', {})
        seq_no = step.get('seq_no', 'Unknown')

        if not isinstance(step_type, str):
            self.logger.error("Invalid step type.")
            self.state['errors'].append("Invalid step type.")
            return False

        handler = getattr(self.instruction_handlers, f"{step_type}_handler", None)
        if not handler:
            self.logger.warning(f"Unknown instruction: {step_type}")
            return False

        success = handler(params)
        if success:
            self.save_state()
            self._log_step_execution(step_type, params, seq_no)
        return success

    def _log_step_execution(self, step_type: str, params: Dict[str, Any], seq_no: str) -> None:
        """Log the execution of a step and prepare commit message."""
        input_parameters = {k: self._preview_value(v) for k, v in params.items()}
        output_vars = params.get('output_var', [])
        output_vars = [output_vars] if isinstance(output_vars, str) else output_vars
        output_variables = {k: self._preview_value(self.variable_manager.get(k)) for k in output_vars}

        description = f"Executed seq_no: {seq_no}, step: '{step_type}'"
        
        self.logger.info(f"{description} with parameters: {json.dumps(input_parameters)}")
        if output_variables:
            self.logger.info(f"Output variables: {json.dumps(output_variables)}")
        
        commit_message_wrapper.set_commit_message(
            StepType.STEP_EXECUTION,
            str(seq_no),
            description,
            input_parameters,
            output_variables
        )

    @staticmethod
    def _preview_value(value: Any) -> str:
        """Create a preview string for a value."""
        value_str = str(value)
        return value_str[:VARIABLE_PREVIEW_LENGTH] + '...' if len(value_str) > VARIABLE_PREVIEW_LENGTH else value_str

    def step(self) -> bool:
        """Execute the next step in the plan."""
        if self.state['program_counter'] >= len(self.state['current_plan']):
            self.logger.error(f"Program counter ({self.state['program_counter']}) out of range for current plan (length: {len(self.state['current_plan'])})")
            self.state['errors'].append(f"Program counter out of range: {self.state['program_counter']}")
            return False

        step = self.state['current_plan'][self.state['program_counter']]
        self.logger.info(f"Executing step {self.state['program_counter']}: {step['type']}, seq_no: {step.get('seq_no', 'Unknown')}, plan length: {len(self.state['current_plan'])}")

        try:
            success = self.execute_step_handler(step)
            if not success:
                self.logger.error(f"Failed to execute step {self.state['program_counter']}: {step['type']}")
                return False
            if step['type'] not in ("jmp_if", "jmp"):
                self.state['program_counter'] += 1

            if self.state['program_counter'] < len(self.state['current_plan']):
                self.garbage_collect()
            self.save_state()
            return True
        except Exception as e:
            self.logger.error(f"Error executing step {self.state['program_counter']}: {str(e)}")
            self.state['errors'].append(f"Error in step {self.state['program_counter']}: {str(e)}")
            return False

    def set_variable(self, var_name: str, value: Any) -> None:
        self.variable_manager.set(var_name, value)
        
        if var_name in ('final_answer'):
            self.state['goal_completed'] = True
            self.logger.info("Goal has been marked as completed.")
            return

        reference_count = 0
        for i in range(self.state['program_counter'] + 1, len(self.state['current_plan'])):
            step = self.state['current_plan'][i]
            for param_name, param_value in step.get('parameters', {}).items():
                referenced_vars = self.variable_manager.find_referenced_variables(param_value)
                if var_name in referenced_vars:
                    reference_count += 1

        print(f"Reference count for {var_name}: {reference_count}")

        self.variable_manager.set_reference_count(var_name, reference_count)

    def recalculate_variable_refs(self) -> None:
        """Recalculate the reference counts for all variables in the current plan."""
        # Reset all reference counts to zero
        variables_refs = {}
        for var_name in self.variable_manager.get_all_variables():
            variables_refs[var_name] = 0

        # Recalculate reference counts based on the current plan
        for i in range(self.state['program_counter'], len(self.state['current_plan'])):
            step = self.state['current_plan'][i]
            for param_name, param_value in step.get('parameters', {}).items():
                referenced_vars = self.variable_manager.find_referenced_variables(param_value)
                for var_name in variables_refs.keys():
                    if var_name in referenced_vars:
                        variables_refs[var_name] = variables_refs[var_name] + 1

        self.variable_manager.set_all_variables(
            self.variable_manager.get_all_variables(),
            variables_refs
        )

        self.logger.info("Variable reference counts recalculated.")

    def get_variable(self, var_name: str) -> Any:
        return self.variable_manager.get(var_name)

    def garbage_collect(self) -> None:
        self.variable_manager.garbage_collect()

    def set_state(self, commit_hash: str) -> None:
        """Load the state from a file based on the specific commit point."""
        loaded_state = load_state(commit_hash, self.repo_path)
        if loaded_state:
            self.state = loaded_state
            self.variable_manager.set_all_variables(
                loaded_state.get('variables', {}),
                loaded_state.get('variables_refs', {})
            )
            self.logger.info(f"State loaded from commit {commit_hash}")
        else:
            self.logger.error(f"Failed to load state from commit {commit_hash}")

    def save_state(self):
        state_data = self.state.copy()
        state_data['variables'] = self.variable_manager.get_all_variables()
        state_data['variables_refs'] = self.variable_manager.get_all_variables_reference_count()
        save_state(state_data, self.repo_path)

    def find_step_index(self, seq_no: int) -> Optional[int]:
        """Find the index of a step with the given sequence number."""
        for index, step in enumerate(self.state['current_plan']):
            if step.get('seq_no') == seq_no:
                return index
        self.logger.error(f"Seq_no {seq_no} not found in the current plan.")
        self.state['errors'].append(f"Seq_no {seq_no} not found in the current plan.")
        return None

    def get_all_variables(self) -> Dict[str, Any]:
        return self.variable_manager.get_all_variables()
