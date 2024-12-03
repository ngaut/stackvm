from typing import Any, Dict
from threading import Lock
import re


class VariableManager:
    """
    Manages variables and their reference counts.
    """

    def __init__(self):
        self.variables = {}
        self.variable_refs = {}
        self._lock = Lock()

    def set(self, var_name: str, value: Any, reference_count: int = 1) -> None:
        with self._lock:
            self.variables[var_name] = value
            self.variable_refs[var_name] = reference_count

    def set_reference_count(self, var_name: str, reference_count: int) -> None:
        with self._lock:
            self.variable_refs[var_name] = reference_count

    def get(self, var_name: str) -> Any:
        with self._lock:
            return self.variables.get(var_name)

    def decrease_ref_count(self, var_name: str) -> None:
        with self._lock:
            if var_name in self.variable_refs:
                self.variable_refs[var_name] -= 1

    def garbage_collect(self) -> None:
        with self._lock:
            for var_name in list(self.variable_refs.keys()):
                if self.variable_refs[var_name] <= 0:
                    del self.variables[var_name]
                    del self.variable_refs[var_name]

    def get_all_variables(self) -> Dict[str, Any]:
        with self._lock:
            return self.variables.copy()

    def get_all_variables_reference_count(self) -> Dict[str, int]:
        with self._lock:
            return self.variable_refs.copy()

    def set_all_variables(
        self, variables: Dict[str, Any], variables_refs: Dict[str, Any]
    ) -> None:
        with self._lock:
            self.variables = variables.copy()
            self.variable_refs = variables_refs.copy()

    def interpolate_variables(self, text: Any) -> Any:
        """Interpolate variables in the given text."""
        if not isinstance(text, str):
            return text

        with self._lock:
            for var, value in self.variables.items():
                # Replace simple variable references
                text = text.replace(f"${{{var}}}", str(value))

                # Replace structured variable references if the value is a dictionary
                if isinstance(value, dict):
                    for sub_var, sub_value in value.items():
                        text = text.replace(f"${{{var}.{sub_var}}}", str(sub_value))

        try:
            result = eval(text)
            return result
        except Exception as e:
            pass

        return text

    def find_referenced_variables(self, text: Any) -> list:
        """Find and return a list of top-level variables referenced in the given text."""
        if not isinstance(text, str):
            return []

        referenced_vars = set()
        with self._lock:
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

    def find_referenced_variables_by_pattern(self, text: Any) -> list:
        """
        Find and return a list of top-level variables referenced in the given text using pattern matching.
        To reference a variable, use the format `${variable_name}` or `${variable_name.sub_var}`.
        """
        if not isinstance(text, str):
            return []

        referenced_vars = set()
        # Define the regex pattern:
        # \${          matches the string '${'
        # (\w+)        captures the variable name consisting of word characters (letters, digits, underscores)
        # (?:\.\w+)?   non-capturing group that optionally matches '.sub_var'
        # \}           matches the closing '}'
        pattern = re.compile(r"\$\{(\w+)(?:\.\w+)?\}")
        # Use findall to extract all matching variable names
        matches = pattern.findall(text)
        # Remove duplicates by converting to a set and then back to a list
        referenced_vars = set(matches)

        return list(referenced_vars)
