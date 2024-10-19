# StackVM

## Installation

To run this project, you need to install the required dependencies. You can do this using Poetry:


```bash
poetry install
```


## LLM Configuration

StackVM now supports local Language Models through Ollama integration:

- **Default LLM Provider**: The default LLM provider is now set to 'ollama'.
- **Default Model**: The default model is set to 'qwen2.5-coder:latest'.
- **Ollama Base URL**: By default, it's set to 'http://localhost:11434'.

To use Ollama:
1. Ensure Ollama is installed and running(OLLAMA_DEBUG=1 ollama serve) on your local machine.
2. The system will use Ollama by default. If you want to explicitly set it:
   ```bash
   export LLM_PROVIDER=ollama
   export LLM_MODEL=your_preferred_ollama_model
   ```

To switch back to OpenAI:
1. Set the LLM provider to 'openai':
   ```bash
   export LLM_PROVIDER=openai
   export LLM_MODEL="gpt-4o-mini"
   export OPENAI_API_KEY=your_openai_api_key
   ```

## Usage

1. **Run the Visualization Script**: 
   To summarize the performance improvement of TiDB from version 6.5 to the newest version, execute the following command:
   ```bash
   python main.py --goal "summary the performance improvement of tidb from version 6.5 to newest version"
   ```

2. **Debug and Optimize Your Goal**: 
   To debug and optimize your goal, run:
   ```bash
   python main.py --server
   ```

3. **Access the Web Interface**: 
   Use your browser to open [http://127.0.0.1:5000/](http://127.0.0.1:5000/).

## Project Structure

- `app/config/settings.py`: Configuration settings, including environment variable loading and default paths.
- `app/controller/api_routes.py`: Defines API routes for the Flask application, handling VM data retrieval and rendering the main interface.
- `app/controller/engine.py`: Manages the generation and execution of plans using the language model.
- `app/controller/plan_repo.py`: Handles Git repository management and commit operations.
- `app/services/prompts.py`: Contains functions to generate prompts for updating VM execution steps.
- `app/services/utils.py`: Utility functions for state management and commit message parsing.
- `app/services/git_manager.py`: Manages Git repository initialization and operations.
- `app/services/llm_interface.py`: Interface for interacting with the OpenAI language model.
- `app/services/variable_manager.py`: Manages variable interpolation and reference within the VM.
- `app/services/plan_manager.py`: Manages plan saving functionality.
- `app/tools/instruction_handlers.py`: Handles instruction execution and API interactions for knowledge graph searches.
- `main.py`: Entry point for running the VM with a specified goal or starting the visualization server.
- `spec.md`: Specifications and requirements for the project, detailing the VM's functionality and design.

## Features

- Dynamic plan generation and execution using a language model.
- Conditional execution based on LLM evaluation.
- Automatic plan updates based on execution progress and errors.
- Support for multiple plan or execution branches.
- Real-time execution of VM steps with commit tracking.
- Web interface for visualizing VM states, commit history, and code diffs.
- Local LLM support.

## Customizing Tools

This project integrates with the TiDB AI API for knowledge graph searches and vector searches.

### Step 1: Create a New Tool File

Navigate to the tools directory in your project. Create a new Python file for your tool, e.g., `my_tool.py`.

### Step 2:  Implement the Tool

In your new tool file, implement the tool function. Use the @tool decorator to mark it as a tool.

```json
from . import tool

@tool
def my_custom_tool(param1, param2):
   """
   This tool performs a custom operation using param1 and param2.

   Arguments:
   - `param1`: Description of param1.
   - `param2`: Description of param2.

   Returns:
   - Result of the custom operation.
   """

   # Your tool logic here

   return response_data
```

## Contributing

If you would like to contribute to this project, please fork the repository and submit a pull request with your changes.

## Troubleshooting

- If you encounter any issues related to missing modules or dependencies, make sure you have installed all required packages as mentioned in the Installation section.
- If you're getting API-related errors, check that your TiDB AI API key is correctly set in your environment variables.
- For any LLM-related issues, ensure your OpenAI API key is properly configured.
