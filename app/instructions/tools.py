import importlib.util
import inspect
import logging
import os
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
)

class ToolsHub:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ToolsHub, cls).__new__(cls, *args, **kwargs)
            cls._instance.tools = {}
            cls._instance.tools_docstrings = {}
        return cls._instance

    def register_tool(self, handler_method: callable) -> None:
        """Register a tool with its corresponding handler."""
        tool_name = handler_method.__name__
        if not isinstance(tool_name, str) or not callable(handler_method):
            raise ValueError(f"Invalid tool registration: {tool_name} is not callable")
        if not handler_method.__doc__ or len(handler_method.__doc__) < 10:
            raise ValueError(
                f"Invalid tool registration: {tool_name} has no valid docstring"
            )
        self.tools[tool_name] = handler_method
        self.tools_docstrings[tool_name] = handler_method.__doc__
        return True

    def get_tool_handler(self, tool_name: str) -> Optional[callable]:
        """Retrieve the handler for a registered tool."""
        return self.tools.get(tool_name)

    def get_tools_description(self) -> str:
        """Get the description of all registered tools."""
        description = "# Tools calling\n\nBelow are the supported tools for calling instruction.\n\n"
        for tool_name, docstring in self.tools_docstrings.items():
            description += f"## {tool_name}\n\n{docstring}\n\n"
        return description


    def load_tools(self, tools_package: str):
        """
        Dynamically load and register all tool functions from the specified package.

        Args:
            tools_package (str): The package name containing tool modules.
            hub: The global_tools_hub instance used to register tools.
        """
        try:
            # Import the tools package
            package = importlib.import_module(tools_package)
        except ImportError as e:
            logging.error(f"Failed to import tools package '{tools_package}': {e}")
            return

        # Get the directory of the tools package
        package_dir = os.path.dirname(package.__file__)

        for filename in os.listdir(package_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                module_name = filename[:-3]
                full_module_name = f"{tools_package}.{module_name}"
                try:
                    logging.info(f"Loading module {module_name} from {filename}")
                    module = importlib.import_module(full_module_name)
                    # Iterate through all members of the module
                    for name, obj in inspect.getmembers(module, inspect.isfunction):
                        # Option 1: Use naming convention (functions starting with 'tool_')
                        if name.startswith("tool_"):
                            self.register_tool(obj)
                            logging.info(f"Registered tool '{name}' from {filename}")
                        # Option 2: Use decorator to identify tool functions
                        elif hasattr(obj, "is_tool") and obj.is_tool:
                            self.register_tool(obj)
                            logging.info(f"Registered tool '{name}' from {filename}")
                except Exception as e:
                    logging.error(f"Failed to load module {full_module_name}: {e}")


# Create a global instance of ToolsHub
global_tools_hub = ToolsHub()
