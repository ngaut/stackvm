# StackVM

## Prerequisites

- Python 3.10 or higher
- Poetry for dependency management
- Access to TiDB Serverless or local TiDB instance
- OpenAI API key (if using OpenAI as LLM provider)
- Ollama (if using local LLM)

## Installation

To run this project, you need to install the required dependencies using Poetry:

```bash
poetry install
```

## Configuration

Create your `.env` file by copying the template:

```bash
cp .env.example .env
```

Configure your environment variables in `.env`:

```env
# Required Configuration
OPENAI_API_KEY=your_openai_api_key
AUTOFLOW_API_KEY=your_autoflow_api_key
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
DATABASE_URI=mysql+pymysql://your_username:password@host:port/stackvm?ssl_ca=/etc/ssl/cert.pem&ssl_verify_cert=true&ssl_verify_identity=true

# Optional: Ollama Configuration
OLLAMA_DEBUG=1
OLLAMA_BASE_URL=http://localhost:11434

# Optional: Backend CORS
BACKEND_CORS_ORIGINS=["http://localhost:5173"]
```

### Initialize Database

After configuring your database connection, set up the schema:

```sql
CREATE DATABASE stackvm;
```

Then run the migrations:

```bash
make migrate
```

## Usage

1. Start the server:
```bash
python main.py --server
```

2. Access the web interface using [stackvm-ui](https://github.com/634750802/stackvm-ui)

3. Run a specific task:

To run the script, use the following command:

```bash
python main.py --goal "your goal description" --response_format '{"lang": "Japanese"}'
```

- **--goal**: Sets a goal for the VM to achieve.
- **--response_format**: (Optional) Specifies the response format for the task as a JSON string representing a dictionary. Defaults to an empty dictionary `{}` if not provided.

## LLM Configuration

StackVM now supports local Language Models through Ollama integration:

- **Default LLM Provider**: The default LLM provider is set based on the `LLM_PROVIDER` variable in the `.env` file.
- **Default Model**: The default model is set based on the `LLM_MODEL` variable in the `.env` file.
- **Ollama Base URL**: Configurable via the `OLLAMA_BASE_URL` variable in the `.env` file.

### Using Ollama

1. **Install and Run Ollama**:
   
   Ensure Ollama is installed. You can run Ollama with debugging enabled using the following command:

   ```bash
   OLLAMA_DEBUG=1 ollama serve
   ```

2. **Set Ollama as the LLM Provider**:
   
   In your `.env` file, set:
   
   ```env
   LLM_PROVIDER=ollama
   LLM_MODEL=your_preferred_ollama_model
   ```

### Switching Back to OpenAI

1. **Set OpenAI as the LLM Provider**:
   
   In your `.env` file, set:
   
   ```env
   LLM_PROVIDER=openai
   LLM_MODEL=gpt-4o-mini
   OPENAI_API_KEY=your_openai_api_key
   ```

## Project Structure

- `app/config/settings.py`: Configuration settings, including environment variable loading and default paths.
- `app/controller/api_routes.py`: Defines API routes for the Flask application, handling VM data retrieval and rendering the main interface.
- `app/controller/plan.py`: Handles plan generation and updating based on suggestions.
- `app/controller/task.py`: Manages task-related operations within the VM.
- `app/services/prompts.py`: Contains functions to generate prompts for updating VM execution steps.
- `app/services/utils.py`: Utility functions for state management and commit message parsing.
- `app/services/branch_manager.py`: Manage branches for plan execution using Git.
- `app/services/mysql_branch_manager.py`: Manage branches for plan execution using TiDB.
- `app/services/llm_interface.py`: Interface for interacting with the OpenAI language model.
- `app/services/variable_manager.py`: Manages variable interpolation and references within the VM.
- `app/services/vm.py`: Implements the `PlanExecutionVM` class for executing plans.
- `app/tools/instruction_handlers.py`: Handles instruction execution and API interactions for knowledge graph searches.
- `app/tools/retrieve.py`: Implements retrieval logic using the TiDB AI API.
- `spec.md`: Specifications and requirements for the project, detailing the VM's functionality and design.
- `plan_example.md`: Example plan demonstrating the instruction execution and plan structure.
- `models/task.py`: Defines the `Task` model for managing tasks within the database.
- `templates/index.html`: HTML template for the main interface.
- `static/scripts.js`: JavaScript for front-end functionalities, including chart management and UI interactions.
- `static/styles.css`: CSS styles for the web interface, ensuring a responsive and user-friendly design.

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

### Step 2: Implement the Tool

In your new tool file, implement the tool function. Use the `@tool` decorator to mark it as a tool.

```python:path/to/tools/my_tool.py
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
- Ensure that Ollama is running if you have set `LLM_PROVIDER=ollama` in your `.env` file.
