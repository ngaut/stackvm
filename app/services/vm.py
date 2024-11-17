from abc import ABC, abstractmethod
import json
import logging
import os
import traceback
from typing import Any, Dict, Optional, List
from app.instructions import InstructionHandlers
from app.services import StepType
from app.services import GitManager, VariableManager

# Constants
VARIABLE_PREVIEW_LENGTH = 50


class Executable(ABC):
    @abstractmethod
    def execute(self) -> Dict[int, Dict[str, Any]]:
        """
        return a dictionary map{seq_no => execution result}
        """
        pass


class StepBlock(Executable):
    def __init__(self, step: Dict[str, Any], vm: PlanExecutionVM):
        if step.get("seq_no") is None:
            raise ValueError("StepBlock must have a seq_no")
        self.step_no = step.get("seq_no")
        self.step = step
        self.vm = vm

    def execute(self, **kwargs) -> Dict[int, Dict[str, Any]]:
        result: Dict[str, Any] = self.vm.execute_step_handler(self.step, **kwargs)
        return {self.step_no: result}

    def __str__(self):
        return f"StepBlock({self.step_no}): {self.step}"


class PlanExecutionVM:
    """
    Virtual Machine for executing plans.
    """

    def __init__(self, repo_path: str, llm_interface: Any = None):
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
        self.blocks: Dict[int, Executable] = {}  # map seq_no to Executable

        os.chdir(self.repo_path)

        self.handlers_registered = False
        self.register_handlers()

    def _setup_logger(self) -> logging.Logger:
        """Set up and return a logger for the class."""
        logger = logging.getLogger(__name__)
        return logger

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
        # self.logger.info("Plan set: %s for goal: %s", plan, self.state["goal"])
        self.blocks = self.parse_plan(plan)
        self.save_state()

    def resolve_parameter(self, param: Any) -> Any:
        """Resolve a parameter, interpolating variables if it's a string."""
        vars = self.variable_manager.find_referenced_variables(param)
        for var in vars:
            self.variable_manager.decrease_ref_count(var)
        return self.variable_manager.interpolate_variables(param)

    def execute_step_handler(self, step: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Execute a single step in the plan and return step execution details."""
        step_type = step.get("type")
        params = step.get("parameters", {})
        seq_no = step.get("seq_no", "Unknown")

        if not isinstance(step_type, str):
            self.logger.error("Invalid step type.")
            self.state["errors"].append("Invalid step type.")
            return {
                "success": False,
                "error": "Invalid step type.",
                "step_type": step_type,
                "seq_no": seq_no,
            }

        handler = getattr(self.instruction_handlers, f"{step_type}_handler", None)
        if not handler:
            self.logger.warning(f"Unknown instruction: {step_type}")
            handler = self.instruction_handlers.unknown_handler

        success, output = handler(params, **kwargs)
        if success:
            self.save_state()
            commit_message_dict = self._log_step_execution(
                step_type, params, seq_no, output
            )
            return {
                "success": True,
                "step_type": step_type,
                "parameters": params,
                "output": output,
                "seq_no": seq_no,
                "commit_message_dict": commit_message_dict,
                "target_seq": output.get("target_seq"),
            }
        else:
            self.logger.error(
                "Failed to execute step %d: %s",
                self.state["program_counter"],
                step["type"],
            )
            self.state["errors"].append(
                f"Failed to execute step {self.state['program_counter']}: {step['type']}"
            )
            return {
                "success": False,
                "error": f"Failed to execute step {self.state['program_counter']}: {step['type']}",
                "step_type": step_type,
                "seq_no": seq_no,
            }

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

        self.logger.info("%s with parameters: %s", description, json.dumps(params))
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
        """Execute the next step in the plan and return step details."""
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

        step = self.state["current_plan"][self.state["program_counter"]]
        self.logger.info(
            "Executing step %d: %s, seq_no: %s, plan length: %d",
            self.state["program_counter"],
            step["type"],
            step.get("seq_no", "Unknown"),
            len(self.state["current_plan"]),
        )

        try:
            step_result = self.execute_step_handler(step, **kwargs)
            if not step_result["success"]:
                return step_result

            # Increment program counter unless it's a jump
            if step["type"] not in ("jmp"):
                self.state["program_counter"] += 1

            # Garbage collect if necessary
            if self.state["program_counter"] < len(self.state["current_plan"]):
                self.garbage_collect()

            self.save_state()
            commit_hash = self.branch_manager.commit_changes(
                commit_info={
                    "type": StepType.STEP_EXECUTION.value,
                    "seq_no": str(step.get("seq_no", "Unknown")),
                    **step_result.get("commit_message_dict", {}),
                }
            )

            step_result["commit_hash"] = commit_hash
            return step_result
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
            self.blocks = self.parse_plan(self.state["current_plan"])
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

    def parse_plan(self, plan: List[Dict[str, Any]]) -> Dict[int, Executable]:
        executables = {}
        for step in plan:
            seq_no = step.get("seq_no")
            if seq_no is not None:
                executables[seq_no] = StepBlock(step, self)
            else:
                self.logger.warning("Step without seq_no: %s", step)
        return executables

    def execute_block(self):
        """Execute the next block in the plan and return step details."""
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

        block = self.blocks.get(self.state["program_counter"])
        if block is None:
            self.logger.error(
                "Block not found for program counter %d", self.state["program_counter"]
            )
            self.state["errors"].append(
                f"Block not found for program counter {self.state['program_counter']}"
            )
            return {
                "success": False,
                "error": f"Block not found for program counter {self.state['program_counter']}",
            }

        self.logger.info(
            "Executing block: %s (program counter:%d), plan length: %d",
            block,
            self.state["program_counter"],
            len(self.state["current_plan"]),
        )

        try:
            results = block.execute(**kwargs)

            success = True
            errors = []
            program_counter = self.state["program_counter"]
            for seq_no, result in results.items():
                if not result["success"]:
                    success = False
                    errors.append(result["error"])

                # Check if the step has a target_seq and jump to that step if it exists
                if result.get("target_seq") is not None:
                    target_seq = result["target_seq"]
                    target_index = self.find_step_index(target_seq)
                    if target_index is not None:
                        program_counter = target_index
                    else:
                        errors.append(
                            f"Target step {target_seq} not found for step {seq_no}"
                        )
                        success = False

                # forwards the program counter if the step was executed successfully
                if seq_no >= program_counter:
                    program_counter += 1

            if not success:
                self.logger.error(
                    "Failed to execute block from step %d: %s",
                    self.state["program_counter"],
                    results,
                )
                self.state["errors"].extend(errors)
                return {
                    "success": False,
                    "error": f"Failed to execute block from step {self.state['program_counter']}: {results}",
                }

            # Garbage collect if necessary
            if program_counter < len(self.state["current_plan"]):
                self.garbage_collect()
            self.state["program_counter"] = program_counter

            self.save_state()
            commit_hash = self.branch_manager.commit_changes(
                commit_info={
                    "type": StepType.STEP_EXECUTION.value,
                    "seq_no": str(step.get("seq_no", "Unknown")),
                    **step_result.get("commit_message_dict", {}),
                }
            )
            return {
                "success": True,
                "commit_hash": commit_hash,
                "instruction_results": results,
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
