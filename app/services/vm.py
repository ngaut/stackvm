import json
import logging
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, List

from app.instructions import InstructionHandlers
from app.services import StepType
from app.services import GitManager, VariableManager
from app.services.step import Step, StepStatus

# Constants
VARIABLE_PREVIEW_LENGTH = 50


class PlanExecutionVM:
    """
    Virtual Machine for executing plans.
    """

    def __init__(self, repo_path: str, llm_interface: Any = None, max_workers=3):
        self.variable_manager = VariableManager()
        self.state: Dict[str, Any] = {
            "errors": [],
            "goal": None,
            "current_plan": [],
            "program_counter": 0,
            "goal_completed": False,
            "msgs": [],
        }

        self.logger = self._setup_logger()
        self.llm_interface = llm_interface
        self.repo_path = repo_path
        self.branch_manager = GitManager(self.repo_path)
        self.set_state(self.branch_manager.get_current_commit_hash())

        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.steps: Dict[str, Step] = {}

        os.chdir(self.repo_path)

        self.handlers_registered = False
        self.register_handlers()

    def _setup_logger(self) -> logging.Logger:
        """Set up and return a logger for the class."""
        logger = logging.getLogger(__name__)
        return logger

    def close_executor(self):
        self.executor.shutdown(wait=True)
        self.logger.info("ThreadPoolExecutor has been shut down.")

    def __del__(self):
        try:
            self.close_executor()
        except Exception as e:
            self.logger.error(f"Error shutting down executor: {str(e)}")

    def _generate_cache_key(self, step: Dict[str, Any]) -> str:
        """Generate a cache key for a step."""
        seq_no = step.get("seq_no")
        step_type = step.get("type")
        return f"{step_type}_{seq_no}"

    def register_handlers(self) -> None:
        """Register all instruction handlers."""
        if not self.handlers_registered:
            self.instruction_handlers = InstructionHandlers(self)
            handler_methods = ["calling", "jmp", "assign", "reasoning"]
            for method in handler_methods:
                self.register_instruction(
                    method, getattr(self.instruction_handlers, f"{method}_handler")
                )
            self.handlers_registered = True

    def register_instruction(
        self, instruction_name: str, handler_method: callable
    ) -> None:
        """Register an individual instruction handler."""
        if not isinstance(instruction_name, str) or not callable(handler_method):
            self.logger.error("Invalid instruction registration.")
            self.state["errors"].append("Invalid instruction registration.")
            return
        setattr(
            self.instruction_handlers, f"{instruction_name}_handler", handler_method
        )
        self.logger.info("Registered handler for instruction: %s", instruction_name)

    def set_goal(self, goal: str) -> None:
        """Set the goal for the VM and save the state."""
        self.state["goal"] = goal
        self.logger.info("Goal set: %s", goal)
        self.save_state()

    def set_plan(self, plan: List[Dict[str, Any]]) -> None:
        """Set the plan for the VM and save the state."""
        self.state["current_plan"] = plan
        self.steps = {
            step_dict["seq_no"]: self.create_step(step_dict) for step_dict in plan
        }
        self.save_state()

    def resolve_parameter(self, param: Any) -> Any:
        """Resolve a parameter, interpolating variables if it's a string."""
        vars = self.variable_manager.find_referenced_variables(param)
        for var in vars:
            self.variable_manager.decrease_ref_count(var)
        return self.variable_manager.interpolate_variables(param)

    def set_state_msg(self, msg: str) -> None:
        """Add a message to the state."""
        self.state["msgs"].append(msg)
        self.logger.info("Message added to state: %s", msg)

    def create_step(self, step: Dict[str, Any]) -> Step:
        """Create a Step object from a dictionary."""

        step_type = step.get("type")
        params = step.get("parameters", {})
        seq_no = step.get("seq_no")
        if not isinstance(step_type, str):
            raise ValueError(f"Invalid step type for {step}.")
        if not isinstance(seq_no, int):
            raise ValueError(f"Invalid seq_no {step}.")

        handler = getattr(self.instruction_handlers, f"{step_type}_handler", None)
        if not handler:
            self.logger.warning(f"Unknown instruction: {step_type}")
            handler = self.instruction_handlers.unknown_handler

        return Step(handler, seq_no, step_type, params)

    def _log_step_execution(
        self,
        step_type: str,
        params: Dict[str, Any],
        seq_no: str,
        output_parameters: Dict[str, Any],
    ):
        """Log the execution of a step and prepare commit message."""
        if step_type == "calling":
            input_vars = params.get("tool_params", {})
            description = f"Executed seq_no: {seq_no}, step: '{step_type}', tool: {params.get('tool_name', 'Unknown')}"
        else:
            input_vars = params
            description = f"Executed seq_no: {seq_no}, step: {step_type}"

        input_parameters = {k: self._preview_value(v) for k, v in input_vars.items()}

        self.logger.info("Commit message -  %s with parameters: %s", description, json.dumps(params))
        if output_parameters:
            output_parameters = {
                k: self._preview_value(v) for k, v in output_parameters.items()
            }
            self.logger.info("Output variables: %s", json.dumps(output_parameters))

        return {
            "description": description,
            "input_parameters": input_parameters,
            "output_variables": output_parameters,
        }

    @staticmethod
    def _preview_value(value: Any) -> str:
        """Create a preview string for a value."""
        value_str = str(value)
        return (
            value_str[:VARIABLE_PREVIEW_LENGTH] + "..."
            if len(value_str) > VARIABLE_PREVIEW_LENGTH
            else value_str
        )

    def step(self, **kwargs) -> Dict[str, Any]:
        """Execute the next step in the plan."""
        if self.state["program_counter"] >= len(self.state["current_plan"]):
            self.logger.error(
                "Program counter (%d) out of range for current plan (length: %d)",
                self.state["program_counter"],
                len(self.state["current_plan"]),
            )
            self.state["errors"].append(
                f"Program counter out of range: {self.state['program_counter']}"
            )
            return {
                "success": False,
                "error": f"Program counter out of range: {self.state['program_counter']}",
            }

        current_step_dict = self.state["current_plan"][self.state["program_counter"]]
        current_step = self.steps[current_step_dict["seq_no"]]

        concurrent_steps = self._find_concurrent_steps()
        for step in concurrent_steps:
            if step.get_status() == StepStatus.PENDING:
                self.logger.info("Executing concurrent step %s", step)
                step.set_status(StepStatus.SUMMITED)
                future = self.executor.submit(step.run, **kwargs)
                step.set_future(future)

        try:
            if current_step.get_status() == StepStatus.PENDING:
                self.logger.info(
                    "Executing step %d: %s", self.state["program_counter"], current_step
                )
                current_step.run(**kwargs)
            elif current_step.get_status() in (StepStatus.SUMMITED, StepStatus.RUNNING):
                # wait future
                self.logger.info(
                    "Waiting for concurrent step %s to complete", current_step
                )
                try:
                    current_step.get_future().result()
                except Exception as e:
                    self.logger.error(
                        f"Failed to execute step {current_step.seq_no}: {str(e)}"
                    )
                    self.state["errors"].append(
                        f"Failed to execute step {current_step.seq_no}: {str(e)}"
                    )
                    return {
                        "success": False,
                        "error": f"Failed to execute step {current_step.seq_no}: {str(e)}",
                        "step_type": current_step.step_type,
                        "seq_no": current_step.seq_no,
                    }

            if current_step.get_status() == StepStatus.RUNNING:
                raise RuntimeError("Step is still running")

            success, output = current_step.get_result()

            if not success:
                self.logger.error(
                    f"Failed to execute step {current_step.seq_no}: {output}"
                )
                self.state["errors"].append(
                    f"Failed to execute step {current_step.seq_no}: {output}"
                )
                return {
                    "success": False,
                    "error": output,
                    "step_type": current_step.step_type,
                    "seq_no": current_step.seq_no,
                }

            commit_message_dict = self._log_step_execution(
                current_step.step_type,
                current_step.parameters,
                current_step.seq_no,
                output,
            )

            if output is not None and output.get("target_seq") is not None:
                target_index = self.find_step_index(output["target_seq"])
                if target_index is not None:
                    self.state["program_counter"] = target_index
                else:
                    return {
                        "success": False,
                        "error": f"Target step {output['target_seq']} not found",
                    }
            else:
                self.state["program_counter"] += 1

            # Garbage collect if necessary
            if self.state["program_counter"] < len(self.state["current_plan"]):
                self.garbage_collect()

            self.save_state()

            commit_hash = self.branch_manager.commit_changes(
                commit_info={
                    "type": StepType.STEP_EXECUTION.value,
                    "seq_no": current_step.seq_no,
                    **commit_message_dict,
                }
            )

            return {
                "success": True,
                "step_type": current_step.step_type,
                "parameters": current_step.parameters,
                "output": output,
                "seq_no": current_step.seq_no,
                "commit_hash": commit_hash,
            }
        except Exception as e:
            traceback.print_exc()
            self.logger.error(
                "Error executing step %d: %s", self.state["program_counter"], str(e)
            )
            self.state["errors"].append(
                f"Error in step {self.state['program_counter']}: {str(e)}"
            )
            return {
                "success": False,
                "error": f"Error in step {self.state['program_counter']}: {str(e)}",
            }

    def set_variable(self, var_name: str, value: Any) -> None:
        self.variable_manager.set(var_name, value)

        if var_name in ("final_answer"):
            self.state["goal_completed"] = True
            self.logger.info("Goal has been marked as completed.")
            return

        reference_count = 0
        for i in range(
            self.state["program_counter"] + 1, len(self.state["current_plan"])
        ):
            step = self.state["current_plan"][i]
            parameters = step.get("parameters", {})
            if step["type"] == "calling":
                parameters = parameters.get("tool_params", {})
            for param_name, param_value in parameters.items():
                referenced_vars = self.variable_manager.find_referenced_variables(
                    param_value
                )
                if var_name in referenced_vars:
                    reference_count += 1

        self.logger.info("Reference count for %s: %d", var_name, reference_count)

        self.variable_manager.set_reference_count(var_name, reference_count)

    def recalculate_variable_refs(self) -> None:
        """Recalculate the reference counts for all variables in the current plan."""
        # Reset all reference counts to zero
        variables_refs = {}
        for var_name in self.variable_manager.get_all_variables():
            variables_refs[var_name] = 0

        # Recalculate reference counts based on the current plan
        for i in range(self.state["program_counter"], len(self.state["current_plan"])):
            step = self.state["current_plan"][i]
            parameters = step.get("parameters", {})
            if step["type"] == "calling":
                parameters = parameters.get("tool_params", {})
            for param_name, param_value in parameters.items():
                referenced_vars = self.variable_manager.find_referenced_variables(
                    param_value
                )
                for var_name in variables_refs.keys():
                    if var_name in referenced_vars:
                        variables_refs[var_name] = variables_refs[var_name] + 1

        self.variable_manager.set_all_variables(
            self.variable_manager.get_all_variables(), variables_refs
        )

        self.logger.info("Variable reference counts recalculated.")

    def get_variable(self, var_name: str) -> Any:
        return self.variable_manager.get(var_name)

    def garbage_collect(self) -> None:
        self.variable_manager.garbage_collect()

    def set_state(self, commit_hash: str) -> None:
        """Load the state from a file based on the specific commit point."""
        loaded_state = self.branch_manager.load_state(commit_hash)
        if loaded_state:
            self.state = loaded_state
            self.variable_manager.set_all_variables(
                loaded_state.get("variables", {}),
                loaded_state.get("variables_refs", {}),
            )
            self.set_plan(self.state["current_plan"])
            self.logger.info("State loaded from commit %s", commit_hash)
        else:
            self.logger.error("Failed to load state from commit %s", commit_hash)

    def save_state(self):
        state_data = self.state.copy()
        state_data["variables"] = self.variable_manager.get_all_variables()
        state_data["variables_refs"] = (
            self.variable_manager.get_all_variables_reference_count()
        )
        self.branch_manager.update_state(state_data)

    def find_step_index(self, seq_no: int) -> Optional[int]:
        """Find the index of a step with the given sequence number."""
        for index, step in enumerate(self.state["current_plan"]):
            if step.get("seq_no") == seq_no:
                return index
        self.logger.error("Seq_no %d not found in the current plan.", seq_no)
        self.state["errors"].append(f"Seq_no {seq_no} not found in the current plan.")
        return None

    def get_all_variables(self) -> Dict[str, Any]:
        return self.variable_manager.get_all_variables()

    def get_current_step(self) -> dict:
        return self.state["current_plan"][self.state["program_counter"]]

    def _find_concurrent_steps(self) -> List[Step]:
        """Find all steps that can be executed concurrently."""
        concurrent_steps = []
        next_index = self.state["program_counter"] + 1

        while next_index < len(self.state["current_plan"]):
            step_dict = self.state["current_plan"][next_index]
            step = self.steps[step_dict["seq_no"]]

            if step.step_type != "calling":
                break  # only consider calling steps

            # check if all referenced variables exist
            tool_params = step.parameters.get("tool_params", {})
            is_ready = True
            for param_name, param_value in tool_params.items():
                vars = self.variable_manager.find_referenced_variables_by_pattern(
                    param_value
                )
                if any(
                    var not in self.variable_manager.get_all_variables() for var in vars
                ):
                    is_ready = False
                    break

            if is_ready:
                concurrent_steps.append(step)
            next_index += 1

        return concurrent_steps
