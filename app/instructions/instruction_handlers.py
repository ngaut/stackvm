import json
from typing import Any, Dict, Optional, List, Union, Tuple
from inspect import signature

from app.utils import find_first_json_object
from .tools import ToolsHub


class InstructionHandlers:
    def __init__(self, vm):
        self.vm = vm  # Store the vm instance
        self.tools_calling = ToolsHub()

    def _handle_error(
        self,
        message: str,
        instruction: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Common error handling method with enhanced context for reflection.

        Args:
            message (str): The error message.
            instruction (Optional[str]): The instruction that caused the error.
            params (Optional[Dict[str, Any]]): The parameters of the instruction.

        Returns:
            bool: Always returns False to indicate an error occurred.
        """
        error_context = {
            "error_message": message,
            "instruction": instruction,
            "params": params,
            "program_counter": self.vm.state.get("program_counter"),
        }

        self.vm.logger.error(f"Error occurred: {json.dumps(error_context, indent=2)}")
        self.vm.state["errors"].append(error_context)
        return False

    def _set_output_vars(
        self,
        instruction_output: Any,
        output_vars: Optional[Union[str, List[str]]] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Sets multiple output variables based on the instruction's output and the output_vars mapping.

        Args:
            instruction_output (Any): The raw output from the instruction.
            output_vars (Optional[Union[str, List[str]]]): Mapping of variable names to expressions referencing the instruction's output.

        Returns:
            Tuple[bool, Dict[str, Any]]: A tuple containing a boolean indicating success and a dictionary of set variables.
        """
        if not output_vars:
            return True, {}  # No output_vars to set

        self.vm.logger.debug(f"output_vars: {output_vars}")
        instruction_output_str = self.vm._preview_value(instruction_output)
        self.vm.logger.debug(f"instruction_output: {instruction_output_str}")
        output_vars_record = {}

        try:
            if len(output_vars) > 1:
                if isinstance(instruction_output, str):
                    # Attempt to parse JSON string
                    json_object = find_first_json_object(instruction_output)
                    if json_object is None:
                        raise ValueError(
                            f"No JSON object found in the instruction output: {instruction_output}."
                        )
                    instruction_output = json.loads(json_object)
                for var_name in output_vars:
                    var_value = instruction_output.get(var_name)
                    self.vm.set_variable(var_name, var_value)
                    output_vars_record[var_name] = var_value
            elif len(output_vars) == 1:
                self.vm.set_variable(output_vars[0], instruction_output)
                output_vars_record[output_vars[0]] = instruction_output
            return True, output_vars_record
        except Exception as e:
            self.vm.logger.error(f"Failed to set output_vars: {e}")
            return False, output_vars_record

    def calling_handler(self, params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        tool_name = params.get("tool_name")
        if tool_name is None:
            return (
                self._handle_error(
                    "Missing 'tool_name' in calling parameters", "calling", params
                ),
                None,
            )

        # Retrieve the tool handler from the tools_calling dictionary
        tool_handler = self.tools_calling.get_tool_handler(tool_name)
        if tool_handler is None:
            return (
                self._handle_error(
                    f"Tool '{tool_name}' is not registered.", "calling", params
                ),
                None,
            )

        tool_parameters = {
            k: self.vm.resolve_parameter(v) for k, v in params.get("tool_params", {}).items()
        }
        output_vars = params.get("output_vars", None)
        if output_vars is None:
            return (
                self._handle_error(
                    "Missing 'output_vars' in calling parameters", "calling", params
                ),
                None,
            )
        if not isinstance(output_vars, list):
            return (
                self._handle_error(
                    "Invalid 'output_vars' type in calling parameters", "calling", params
                ),
                None,
            )
        if len(output_vars) > 1:
            tool_parameters["response_format"] = (
                "Respond with a JSON object in the following format:\n"
                + self._construct_response_format_example(output_vars)
            )

        # Get the parameters required by the tool_handler
        handler_signature = signature(tool_handler)
        required_params = handler_signature.parameters.keys()

        # Filter tool_parameters to include only those required by tool_handler
        filtered_tool_parameters = {
            k: v for k, v in tool_parameters.items() if k in required_params
        }

        # Call the tool handler with the filtered parameters
        result = tool_handler(**filtered_tool_parameters)
        if result is not None:
            return self._set_output_vars(result, output_vars)

        return (
            self._handle_error(
                f"Failed to fetch response from tool '{tool_name}'.",
                "calling",
                params,
            ),
            output_vars,
        )

    def _construct_response_format_example(
        self, output_vars: Optional[Union[str, List[str]]] = None
    ) -> Optional[str]:
        """Construct a response format example based on output variables."""
        if not output_vars and not isinstance(output_vars, list):
            return None

        example_structure = {}
        for key in output_vars:
            example_structure[key] = f"<to be filled>"

        return json.dumps(example_structure, indent=2)

    def jmp_handler(self, params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """Handle both conditional and unconditional jumps."""
        condition_prompt = self.vm.resolve_parameter(params.get("condition_prompt"))
        context = self.vm.resolve_parameter(params.get("context"))
        jump_if_true = params.get("jump_if_true")
        jump_if_false = params.get("jump_if_false")
        target_seq = params.get("target_seq")

        if condition_prompt:
            # Conditional jump
            if jump_if_true is None or jump_if_false is None:
                return (
                    self._handle_error(
                        "Missing 'condition_prompt', 'jump_if_true', or 'jump_if_false' in parameters.",
                        instruction="jmp",
                        params=params,
                    ),
                    None,
                )

            condition_prompt_with_response_format = (
                condition_prompt
                + '\nRespond with a JSON object in the following format:\n{\n  "result": boolean,\n  "explanation": string\n}'
            )
            response = self.vm.llm_interface.generate(
                condition_prompt_with_response_format, context
            )

            try:
                json_object = find_first_json_object(response)
                if json_object is None:
                    raise ValueError(
                        f"No JSON object found in the response: {response}."
                    )
                parsed_response = json.loads(json_object)
                condition_result = parsed_response.get("result")
                explanation = parsed_response.get("explanation", "")

                if not isinstance(condition_result, bool):
                    return (
                        self._handle_error(
                            f"Invalid condition result type: {type(condition_result)} in response {json_object}. Expected boolean.",
                            instruction="jmp",
                            params=params,
                        ),
                        None,
                    )

                if condition_result:
                    target_seq = jump_if_true
                else:
                    target_seq = jump_if_false

                self.vm.logger.info(
                    f"Jumping to seq_no {target_seq} based on condition result: {condition_result}. "
                    f"Explanation: {explanation}"
                )
            except json.JSONDecodeError:
                return (
                    self._handle_error(
                        "Failed to parse JSON response from LLM.",
                        instruction="jmp",
                        params=params,
                    ),
                    None,
                )
            except Exception as e:
                return (
                    self._handle_error(
                        f"Unexpected error in jmp_handler: {str(e)}",
                        instruction="jmp",
                        params=params,
                    ),
                    None,
                )
        elif target_seq is None:
            return (
                self._handle_error(
                    "Missing 'target_seq' for unconditional jump.", "jmp", params
                ),
                None,
            )

        try:
            target_index = self.vm.find_step_index(target_seq)
            if target_index is None:
                return (
                    self._handle_error(
                        f"Target sequence number {target_seq} not found in the plan.",
                        "jmp",
                        params,
                    ),
                    None,
                )

            self.vm.state["program_counter"] = target_index
            self.vm.logger.info(f"Jumped to seq_no {target_seq}")
            return True, {"target_seq": target_seq}
        except Exception as e:
            return (
                self._handle_error(
                    f"Unexpected error in jmp_handler: {str(e)}", "jmp", params
                ),
                None,
            )

    def assign_handler(self, params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """Handle variable assignment."""
        for var_name, value in params.items():
            value_resolved = self.vm.resolve_parameter(value)
            self.vm.set_variable(var_name, value_resolved)
        return True, {var_name: value_resolved}

    def reasoning_handler(self, params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """Handle reasoning steps."""
        chain_of_thoughts = params.get("chain_of_thoughts")
        dependency_analysis = params.get("dependency_analysis")

        if not isinstance(chain_of_thoughts, str) or not isinstance(
            dependency_analysis, str
        ):
            return self._handle_error("Invalid parameters for 'reasoning'."), None

        self.vm.logger.info(
            f"Reasoning step:chain_of_thoughts: {chain_of_thoughts}\n{dependency_analysis}"
        )

        self.vm.state["msgs"].append(
            {
                "chain_of_thoughts": chain_of_thoughts,
                "dependency_analysis": dependency_analysis,
            }
        )
        return True, None
