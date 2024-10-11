from typing import Any, Dict

class VariableManager:
    def __init__(self):
        self.variables = {}
        self.variable_refs = {}

    def set(self, var_name: str, value: Any) -> None:
        if var_name in self.variables:
            self.decrease_ref_count(var_name)
        
        self.variables[var_name] = value
        self.variable_refs[var_name] = 1

    def get(self, var_name: str) -> Any:
        if var_name in self.variables:
            self.variable_refs[var_name] += 1
        return self.variables.get(var_name)

    def decrease_ref_count(self, var_name: str) -> None:
        if var_name in self.variable_refs:
            self.variable_refs[var_name] -= 1
            if self.variable_refs[var_name] <= 0:
                del self.variables[var_name]
                del self.variable_refs[var_name]

    def garbage_collect(self) -> None:
        for var_name in list(self.variable_refs.keys()):
            if self.variable_refs[var_name] <= 0:
                del self.variables[var_name]
                del self.variable_refs[var_name]

    def get_all_variables(self) -> Dict[str, Any]:
        return self.variables.copy()

    def set_all_variables(self, variables: Dict[str, Any]) -> None:
        self.variables = variables.copy()
        self.variable_refs = {k: 1 for k in variables}

    def interpolate_variables(self, text: Any) -> Any:
        """Interpolate variables in the given text."""
        if not isinstance(text, str):
            return text
        for var, value in self.variables.items():
            text = text.replace(f"${{{var}}}", str(value))
        return text