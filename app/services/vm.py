import json
import logging
import os
import traceback
from typing import Any, Dict, Optional, List
from app.instructions import InstructionHandlers
from app.services import StepType
from app.services import GitManager, VariableManager
import concurrent.futures
from collections import defaultdict
import threading

# Constants
VARIABLE_PREVIEW_LENGTH = 50


class PlanExecutionVM:
    """
    Virtual Machine for executing plans.
    """

    def __init__(self, repo_path: str, llm_interface: Any = None, max_workers: int = 5):
        self.variable_manager = VariableManager()
        self.state: Dict[str, Any] = {
            "errors": [],
            "goal": None,
            "current_plan": [],
            "goal_completed": False,
            "msgs": [],
            "executed_steps": set(),  # Track which steps have been executed
        }

        self.logger = self._setup_logger()
        self.llm_interface = llm_interface
        self.repo_path = repo_path
        self.branch_manager = GitManager(self.repo_path)
        self.set_state(self.branch_manager.get_current_commit_hash())

        os.chdir(self.repo_path)

        self.handlers_registered = False
        self.register_handlers()

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.step_futures = {}
        self.step_status = {}  # Tracks status of each step (pending, running, completed, failed)
        self.step_dependencies = defaultdict(list)  # Maps each step to its dependent steps
        self.variable_producers = {}  # Maps variables to the step that produces them
        self.lock = threading.RLock()  # Ensure thread-safe operations
        self._build_dependency_graph()

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
        """Set the goal for the VM."""
        with self.lock:
            self.state["goal"] = goal
            self.logger.info("Goal set: %s", goal)

    def set_plan(self, plan: List[Dict[str, Any]]) -> None:
        """Set the plan and initialize dependency tracking."""
        with self.lock:
            self.state["current_plan"] = plan
            self.state["executed_steps"] = set()  # Reset executed steps
            self._build_dependency_graph()  # Rebuild dependency graph for new plan
            self.logger.info("New plan set with %d steps", len(plan))

    def resolve_parameter(self, param: Any) -> Any:
        """Resolve a parameter, interpolating variables if it's a string."""
        vars = self.variable_manager.find_referenced_variables(param)
        for var in vars:
            self.variable_manager.decrease_ref_count(var)
        return self.variable_manager.interpolate_variables(param)

    def execute_step_handler(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single step in the plan and return step execution details."""
        step_type = step.get("type")
        params = step.get("parameters", {})
        seq_no = step.get("seq_no", "Unknown")

        if not isinstance(step_type, str):
            self.logger.error("Invalid step type.")
            return {
                "success": False,
                "error": "Invalid step type",
                "step_type": step_type,
                "seq_no": seq_no,
            }

        handler_name = f"{step_type}_handler"
        handler = getattr(self.instruction_handlers, handler_name, None)

        if not handler:
            self.logger.error(f"No handler found for instruction type: {step_type}")
            return {
                "success": False,
                "error": f"No handler found for instruction type: {step_type}",
                "step_type": step_type,
                "seq_no": seq_no,
            }

        try:
            success, execution_result = handler(params)
            if not success:
                return {
                    "success": False,
                    "error": f"Handler execution failed for step type: {step_type}",
                    "step_type": step_type,
                    "seq_no": seq_no,
                }

            # Log step execution
            log_result = self._log_step_execution(
                step_type, params, seq_no, execution_result or {}
            )

            return {
                "success": True,
                "execution_result": log_result,
                "step_type": step_type,
                "seq_no": seq_no,
            }

        except Exception as e:
            self.logger.error(
                f"Error executing step {seq_no} of type {step_type}: {str(e)}"
            )
            return {
                "success": False,
                "error": str(e),
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

    def step(self) -> Dict[str, Any]:
        """Execute a single step and return step details."""
        with self.lock:
            ready_steps = [
                step for step in self.state["current_plan"]
                if self._is_step_ready(step)
            ]
            
            if not ready_steps:
                return {
                    "success": False,
                    "error": "No ready steps available for execution",
                }

            step = ready_steps[0]
            try:
                step_result = self.execute_step_handler(step)
                if not step_result["success"]:
                    return step_result

                # Garbage collect if necessary
                self.garbage_collect()

                self.save_state()
                commit_hash = self.branch_manager.commit_changes(
                    commit_info={
                        "type": StepType.STEP_EXECUTION.value,
                        "seq_no": str(step.get("seq_no", "Unknown")),
                        **step_result.get("execution_result", {}),
                    }
                )

                step_result["commit_hash"] = commit_hash
                return step_result
            except Exception as e:
                traceback.print_exc()
                self.logger.error(
                    "Error executing step %s: %s", 
                    step.get("seq_no"), 
                    str(e)
                )
                self.state["errors"].append(
                    f"Error in step {step.get('seq_no')}: {str(e)}"
                )
                return {
                    "success": False,
                    "error": f"Error in step {step.get('seq_no')}: {str(e)}",
                }

    def set_variable(self, var_name: str, value: Any) -> None:
        """Set a variable value and update its reference count."""
        self.variable_manager.set(var_name, value)

        if var_name in ("final_answer"):
            self.state["goal_completed"] = True
            self.logger.info("Goal has been marked as completed.")
            return

        # Update reference count based on remaining unexecuted steps
        reference_count = 0
        for step in self.state["current_plan"]:
            if step.get("seq_no") not in self.state["executed_steps"]:
                parameters = step.get("parameters", {})
                if step["type"] == "calling":
                    parameters = parameters.get("tool_params", {})
                for param_value in parameters.values():
                    referenced_vars = self.variable_manager.find_referenced_variables(
                        param_value
                    )
                    if var_name in referenced_vars:
                        reference_count += 1

        self.logger.info("Reference count for %s: %d", var_name, reference_count)
        self.variable_manager.set_reference_count(var_name, reference_count)

    def recalculate_variable_refs(self) -> None:
        """Recalculate the reference counts for all variables in the current plan."""
        variables_refs = {
            var_name: 0 
            for var_name in self.variable_manager.get_all_variables()
        }

        # Count references in unexecuted steps
        for step in self.state["current_plan"]:
            if step.get("seq_no") not in self.state["executed_steps"]:
                for param_value in step.get("parameters", {}).values():
                    referenced_vars = self.variable_manager.find_referenced_variables(
                        param_value
                    )
                    for var_name in variables_refs:
                        if var_name in referenced_vars:
                            variables_refs[var_name] += 1

        self.variable_manager.set_all_variables(
            self.variable_manager.get_all_variables(),
            variables_refs
        )

        self.logger.info("Variable reference counts recalculated.")

    def get_variable(self, var_name: str) -> Any:
        return self.variable_manager.get(var_name)

    def garbage_collect(self) -> None:
        """Perform garbage collection on variables no longer needed."""
        self.variable_manager.garbage_collect()

    def set_state(self, commit_hash: str) -> None:
        with self.lock:
            loaded_state = self.branch_manager.load_state(commit_hash)
            if loaded_state:
                self.state = loaded_state
                self.variable_manager.set_all_variables(
                    loaded_state.get("variables", {}),
                    loaded_state.get("variables_refs", {}),
                )
                self.logger.info("State loaded from commit %s", commit_hash)
            else:
                self.logger.error("Failed to load state from commit %s", commit_hash)

    def save_state(self):
        with self.lock:
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
        """Get the next step to be executed based on dependency graph."""
        ready_steps = [
            step for step in self.state["current_plan"]
            if self._is_step_ready(step)
        ]
        return ready_steps[0] if ready_steps else None

    def _build_dependency_graph(self):
        """Build dependency graph and initialize step statuses."""
        self.step_status = {
            step.get("seq_no"): "pending" 
            for step in self.state["current_plan"]
        }
        
        for step in self.state["current_plan"]:
            seq_no = step.get("seq_no")
            params = step.get("parameters", {})
            
            # Handle special case for jump instructions
            if step["type"] == "jmp":
                # All previous steps must complete before a jump
                prev_steps = [s.get("seq_no") for s in self.state["current_plan"] if s.get("seq_no") < seq_no]
                for prev_seq in prev_steps:
                    self.step_dependencies[prev_seq].append(seq_no)
                continue
                
            if step["type"] == "assign":
                for var_name in params.keys():
                    self.variable_producers[var_name] = seq_no
                    
            # Identify dependencies based on variable references
            referenced_vars = self.variable_manager.find_referenced_variables(params)
            for var in referenced_vars:
                producer_seq = self.variable_producers.get(var)
                if producer_seq:
                    self.step_dependencies[producer_seq].append(seq_no)
                    
        self.logger.info("Dependency graph built: %s", dict(self.step_dependencies))

    def _is_step_ready(self, step: Dict[str, Any]) -> bool:
        """Check if a step is ready to be executed."""
        seq_no = step.get("seq_no")
        
        # Check if step was already executed
        if seq_no in self.state["executed_steps"]:
            return False
            
        # Special handling for jump instructions
        if step["type"] == "jmp":
            # Ensure all previous steps are completed before executing jump
            prev_steps = [s.get("seq_no") for s in self.state["current_plan"] if s.get("seq_no") < seq_no]
            return all(s in self.state["executed_steps"] for s in prev_steps)
            
        # Check variable dependencies
        params = step.get("parameters", {})
        referenced_vars = self.variable_manager.find_referenced_variables(params)
        for var in referenced_vars:
            producer_seq = self.variable_producers.get(var)
            if producer_seq and producer_seq not in self.state["executed_steps"]:
                return False
        return True

    def execute_parallel_steps(self):
        """Execute all ready steps in parallel."""
        with self.lock:
            ready_steps = [
                step for step in self.state["current_plan"]
                if self._is_step_ready(step)
            ]
            
        self.logger.info("Ready steps for parallel execution: %s", 
                        [s.get('seq_no') for s in ready_steps])
                        
        for step in ready_steps:
            seq_no = step.get('seq_no')
            if self.step_status[seq_no] != 'pending':
                continue
                
            future = self.executor.submit(self._execute_step_safely, step)
            self.step_futures[future] = seq_no
            self.step_status[seq_no] = 'running'

    def _execute_step_safely(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a step with proper state management."""
        try:
            with self.lock:
                result = self.execute_step_handler(step)
                if result["success"]:
                    seq_no = step.get("seq_no")
                    self.state["executed_steps"].add(seq_no)
                    
                    # Handle jump instruction
                    if step["type"] == "jmp" and result.get("target_seq"):
                        target_seq = result["target_seq"]
                        # Mark all steps between current and target as executed
                        for s in self.state["current_plan"]:
                            s_seq = s.get("seq_no")
                            if seq_no < s_seq < target_seq:
                                self.state["executed_steps"].add(s_seq)
                
                self.save_state()
                return result
        except Exception as e:
            self.logger.error(f"Error executing step {step.get('seq_no')}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "step_type": step.get("type"),
                "seq_no": step.get("seq_no")
            }

    def monitor_futures(self):
        """Monitor and handle completed futures."""
        done, _ = concurrent.futures.wait(
            self.step_futures.keys(), 
            return_when=concurrent.futures.FIRST_COMPLETED
        )
        
        for future in done:
            seq_no = self.step_futures.pop(future)
            try:
                result = future.result()
                if result["success"]:
                    self.step_status[seq_no] = 'completed'
                    self.logger.info(f"Step {seq_no} completed successfully.")
                    
                    # Check for newly ready dependent steps
                    self._schedule_dependent_steps(seq_no)
                else:
                    self.step_status[seq_no] = 'failed'
                    self.logger.error(f"Step {seq_no} failed with error: {result['error']}")
                    # Optionally halt execution on failure
                    self._handle_step_failure(seq_no, result['error'])
            except Exception as e:
                self.step_status[seq_no] = 'failed'
                self.logger.error(f"Step {seq_no} generated an exception: {str(e)}")
                self._handle_step_failure(seq_no, str(e))

    def _schedule_dependent_steps(self, completed_seq_no: int):
        """Schedule dependent steps that are now ready for execution."""
        for dependent_seq in self.step_dependencies.get(completed_seq_no, []):
            dependent_step = next(
                (s for s in self.state["current_plan"] if s.get("seq_no") == dependent_seq),
                None
            )
            if dependent_step and self._is_step_ready(dependent_step):
                future = self.executor.submit(self._execute_step_safely, dependent_step)
                self.step_futures[future] = dependent_seq
                self.step_status[dependent_seq] = 'running'

    def _handle_step_failure(self, failed_seq_no: int, error: str):
        """Handle step failure by optionally halting execution."""
        with self.lock:
            self.state["errors"].append(f"Step {failed_seq_no} failed: {error}")
            # Optionally implement failure handling strategy:
            # 1. Continue with independent steps
            # 2. Halt all execution
            # 3. Retry failed step
            # Current implementation: continue with independent steps

    def run(self) -> Dict[str, Any]:
        """Execute the plan with parallel processing."""
        try:
            self.execute_parallel_steps()
            while self.step_futures:
                self.monitor_futures()
                
            # Check if all steps were executed successfully
            all_completed = all(
                status == 'completed' 
                for status in self.step_status.values()
            )
            
            return {
                "success": all_completed,
                "executed_steps": len(self.state["executed_steps"]),
                "errors": self.state["errors"],
                "goal_completed": self.state["goal_completed"]
            }
        finally:
            self.executor.shutdown(wait=True)

    def _get_step_by_seq(self, seq_no: int) -> Optional[Dict[str, Any]]:
        """Get a step by its sequence number."""
        return next(
            (step for step in self.state["current_plan"] if step.get("seq_no") == seq_no),
            None
        )
