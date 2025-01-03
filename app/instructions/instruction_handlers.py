import json
from typing import Any, Dict, Optional, List, Union, Tuple
from inspect import signature

from app.utils import find_first_json_object
from .tools import ToolsHub


class InstructionHandlers:
    def __init__(self, vm):
        self.vm = vm  # Store the vm instance
        self.tools_calling = ToolsHub()

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
            # Attempt to parse instruction_output as JSON if it's a string
            parsed_output = None
            if isinstance(instruction_output, str):
                json_object = find_first_json_object(instruction_output)
                if json_object:
                    try:
                        parsed_output = json.loads(json_object)
                        self.vm.logger.debug(f"Parsed JSON output: {parsed_output}")
                    except json.JSONDecodeError:
                        self.vm.logger.debug(
                            "instruction_output is a string but not a valid JSON."
                        )

            if isinstance(output_vars, str):
                output_vars = [output_vars]

            for var_name in output_vars:
                if (
                    parsed_output
                    and isinstance(parsed_output, dict)
                    and var_name in parsed_output
                ):
                    var_value = parsed_output.get(var_name)
                else:
                    # Fallback to treating instruction_output as a single value
                    if len(output_vars) == 1:
                        var_value = (
                            parsed_output if parsed_output else instruction_output
                        )
                    else:
                        raise ValueError(
                            f"Not found variable {var_name} in parsed_output {parsed_output}."
                        )
                # self.vm.set_variable(var_name, var_value)
                output_vars_record[var_name] = var_value

            return True, output_vars_record
        except Exception as e:
            self.vm.logger.error(
                f"Failed to set output_vars: {e} for {instruction_output}"
            )
            return False, output_vars_record

    def unknown_handler(
        self, params: Dict[str, Any], **kwargs
    ) -> Tuple[bool, Dict[str, Any]]:
        return self.calling_handler(params, **kwargs)

    def calling_handler(
        self, params: Dict[str, Any], **kwargs
    ) -> Tuple[bool, Dict[str, Any]]:
        tool_name = params.get("tool_name")
        if tool_name is None:
            return (
                False,
                {
                    "error_message": "Missing 'tool_name' in calling parameters",
                    "instruction": "calling",
                    "params": params,
                },
            )

        # Retrieve the tool handler from the tools_calling dictionary
        tool_handler = self.tools_calling.get_tool_handler(tool_name)
        if tool_handler is None:
            return (
                False,
                {
                    "error_message": f"Tool '{tool_name}' is not registered.",
                    "instruction": "calling",
                    "params": params,
                },
            )

        tool_parameters = {
            k: self.vm.resolve_parameter(v)
            for k, v in params.get("tool_params", {}).items()
        }
        output_vars = params.get("output_vars", None)
        if output_vars is None:
            return (
                False,
                {
                    "error_message": "Missing 'output_vars' in calling parameters",
                    "instruction": "calling",
                    "params": params,
                },
            )
        if not isinstance(output_vars, list):
            return (
                False,
                {
                    "error_message": "Invalid 'output_vars' type in calling parameters",
                    "instruction": "calling",
                    "params": params,
                },
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
        supported_kwargs = {k: v for k, v in kwargs.items() if k in required_params}

        final_parameters = {**supported_kwargs, **filtered_tool_parameters}

        # Call the tool handler with the filtered parameters
        result = tool_handler(**final_parameters)
        if result is not None:
            success, output_vars_record = self._set_output_vars(result, output_vars)
            return success, {"output_vars": output_vars_record}

        return (
            False,
            {
                "error_message": f"Failed to fetch response from tool '{tool_name}', output {output_vars}",
                "instruction": "calling",
                "params": params,
            },
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

    def jmp_handler(
        self, params: Dict[str, Any], **kwargs
    ) -> Tuple[bool, Dict[str, Any]]:
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
                    False,
                    {
                        "error_message": "Missing 'condition_prompt', 'jump_if_true', or 'jump_if_false' in parameters.",
                        "instruction": "jmp",
                        "params": params,
                    },
                )

            condition_prompt_with_response_format = (
                condition_prompt
                + '\n Assume no prior knowledge. Base your response only on the input provided in this query or its explicitly mentioned sources. Respond only with a JSON object in the following format:\n{\n  "result": boolean,\n  "explanation": string\n}'
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
                        False,
                        {
                            "error_message": f"Invalid condition result type: {type(condition_result)} in response {json_object}. Expected boolean.",
                            "instruction": "jmp",
                            "params": params,
                        },
                    )

                if condition_result:
                    target_seq = jump_if_true
                else:
                    target_seq = jump_if_false

                self.vm.logger.info(
                    f"Jumping to seq_no {target_seq} based on condition result: {condition_result}. "
                    f"Explanation: {explanation}"
                )

                return True, {"target_seq": target_seq}
            except json.JSONDecodeError:
                return (
                    False,
                    {
                        "error_message": f"Failed to parse JSON response from LLM: {response}.",
                        "instruction": "jmp",
                        "params": params,
                    },
                )
            except Exception as e:
                return (
                    False,
                    {
                        "error_message": f"Unexpected error in jmp_handler: {str(e)}",
                        "instruction": "jmp",
                        "params": params,
                    },
                )

            return (
                False,
                {
                    "error_message": "Missing 'target_seq' for unconditional jump.",
                    "instruction": "jmp",
                    "params": params,
                },
            )

    def assign_handler(
        self, params: Dict[str, Any], **kwargs
    ) -> Tuple[bool, Dict[str, Any]]:
        """Handle variable assignment."""
        output_vars_record = {}
        for var_name, value in params.items():
            value_resolved = self.vm.resolve_parameter(value)
            # self.vm.set_variable(var_name, value_resolved)
            output_vars_record[var_name] = value_resolved
        return True, {"output_vars": output_vars_record}

    def reasoning_handler(
        self, params: Dict[str, Any], **kwargs
    ) -> Tuple[bool, Dict[str, Any]]:
        """Handle reasoning steps."""
        chain_of_thoughts = params.get("chain_of_thoughts")
        dependency_analysis = params.get("dependency_analysis")

        if not isinstance(chain_of_thoughts, str):
            return False, {
                "error_message": "Invalid parameters for 'reasoning'.",
                "instruction": "reasoning",
                "params": params,
            }

        self.vm.logger.info(
            f"Reasoning step:chain_of_thoughts: {chain_of_thoughts}\n{dependency_analysis}"
        )

        self.vm.set_state_msg(
            json.dumps(
                {
                    "chain_of_thoughts": chain_of_thoughts,
                    "dependency_analysis": dependency_analysis,
                }
            )
        )
        return True, None
