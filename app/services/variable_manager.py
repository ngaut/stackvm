from typing import Any, Dict


class VariableManager:
    """
    Manages variables and their reference counts.
    """

    def __init__(self):
        self.variables = {}
        self.variable_refs = {}

    def set(self, var_name: str, value: Any, reference_count: int = 1) -> None:
        self.variables[var_name] = value
        self.variable_refs[var_name] = reference_count

    def set_reference_count(self, var_name: str, reference_count: int) -> None:
        self.variable_refs[var_name] = reference_count

    def get(self, var_name: str) -> Any:
        return self.variables.get(var_name)

    def decrease_ref_count(self, var_name: str) -> None:
        if var_name in self.variable_refs:
            self.variable_refs[var_name] -= 1

    def garbage_collect(self) -> None:
        for var_name in list(self.variable_refs.keys()):
            if self.variable_refs[var_name] <= 0:
                del self.variables[var_name]
                del self.variable_refs[var_name]

    def get_all_variables(self) -> Dict[str, Any]:
        return self.variables.copy()

    def get_all_variables_reference_count(self) -> Dict[str, int]:
        return self.variable_refs.copy()

    def set_all_variables(
        self, variables: Dict[str, Any], variables_refs: Dict[str, Any]
    ) -> None:
        self.variables = variables.copy()
        self.variable_refs = variables_refs.copy()

    def interpolate_variables(self, text: Any) -> Any:
        """Interpolate variables in the given text."""
        if not isinstance(text, str):
            return text

        for var, value in self.variables.items():
            # Replace simple variable references
            text = text.replace(f"${{{var}}}", str(value))

            # Replace structured variable references if the value is a dictionary
            if isinstance(value, dict):
                for sub_var, sub_value in value.items():
                    text = text.replace(f"${{{var}.{sub_var}}}", str(sub_value))

        return text

    def find_referenced_variables(self, text: Any) -> list:
        """Find and return a list of top-level variables referenced in the given text."""
        if not isinstance(text, str):
            return []

        referenced_vars = set()
        for var in self.variables.keys():
            # Check for simple variable reference
            if f"${{{var}}}" in text:
                referenced_vars.add(var)
            # Check for structured variable reference
            elif isinstance(self.variables.get(var), dict) and any(
                f"${{{var}.{sub_var}}}" in text
                for sub_var in self.variables[var].keys()
            ):
                referenced_vars.add(var)

        return list(referenced_vars)
