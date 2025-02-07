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

### Starting the Server

Start the server using the following command:

```bash
gunicorn -w 16 -b 0.0.0.0:5000 -t 300 main:app
```

### Running Tasks

Run a specific task using the following command:

```bash
flask stackvm execute --goal "your goal description" --response-format '{"lang": "Japanese"}' --namespace-name "your-namespace"
```

Options:
- **--goal**: Sets a goal for the VM to achieve (required).
- **--response-format**: (Optional) Specifies the response format for the task as a JSON string. Defaults to an empty dictionary `{}`.
- **--namespace-name**: (Optional) Specifies the namespace to use for the task. Determines which tools are available.

### Managing Namespaces

StackVM uses namespaces to manage tool access and configurations. Here are the available namespace management commands:

1. **Create a Namespace**:
```bash
flask namespace create my-namespace --allowed-tools tool1 --allowed-tools tool2 --description "My namespace description"
```

2. **Update a Namespace**:
```bash
flask namespace update my-namespace --allowed-tools new-tool --description "Updated description"
```

3. **Delete a Namespace**:
```bash
flask namespace delete my-namespace
```

4. **List All Namespaces**:
```bash
flask namespace list
```

5. **Show Namespace Details**:
```bash
flask namespace show my-namespace
```

Options for namespace management:
- **--allowed-tools**: Specify which tools are available in the namespace. Can be specified multiple times.
- **--description**: Add a description to the namespace.

## LLM Configuration

StackVM supports multiple LLM configurations including a dedicated reasoning model:

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

### Reasoning Model with OpenAI

You can configure both standard and reasoning models in your `.env` file:

```env
# Standard LLM Configuration
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o

# Reasoning Model Configuration (Optional)
REASON_LLM_PROVIDER=openai
REASON_LLM_MODEL=o3-mini
```

If `REASON_LLM_PROVIDER` and `REASON_LLM_MODEL` are not set, they will default to the standard LLM configuration values.

The reasoning model is specifically used for:
- Plan generation
- Plan updates
- Plan evaluation
- Complex decision making

## Project Structure

- `app/`: Main application directory
  - `api/`: API endpoints and routes
    - `api_routes.py`: API routes for task management and VM operations
  - `config/`: Configuration settings
    - `settings.py`: Environment variables and application settings
    - `database.py`: Database configuration
  - `core/`: Core business logic
    - `task/`: Task management
      - `manager.py`: Task creation and management
      - `queue.py`: Asynchronous task queue implementation
    - `vm/`: Virtual Machine implementation
      - `engine.py`: Plan execution engine
      - `step.py`: Step execution logic
    - `plan/`: Plan management
      - `generator.py`: Plan generation and updates
      - `utils.py`: Plan-related utilities
    - `labels/`: Label classification system
  - `llm/`: Language Model integration
    - `base.py`: Abstract base class for LLM providers
    - `interface.py`: LLM provider interface
  - `storage/`: Data storage and persistence
    - `branch_manager/`: Branch management implementations
      - `git.py`: Git-based branch manager
      - `mysql.py`: MySQL-based branch manager
    - `models/`: Database models
  - `utils/`: Utility functions
    - `logging.py`: Centralized logging configuration
  - `instructions/`: Tool definitions and handlers
    - `tools.py`: Tool registration and management
    - `global_tools_hub.py`: Global tool registry

- `alembic/`: Database migration scripts
- `notebooks/`: Jupyter notebooks for maintanence

## Features

- Dynamic plan generation and execution using a language model.
- Conditional execution based on LLM evaluation.
- Automatic plan updates based on execution progress and errors.
- Support for multiple plan or execution branches.
- Real-time execution of VM steps with commit tracking.
- Web interface for visualizing VM states, commit history, and code diffs.
- Local LLM support.
- Namespace-based tool access management.

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

### Step 3: Register the Tool with a Namespace

After implementing your tool, you can register it with a specific namespace:

```bash
flask namespace create my-namespace --allowed-tools my_custom_tool
```

Or add it to an existing namespace:

```bash
flask namespace update my-namespace --allowed-tools my_custom_tool
```

## Contributing

If you would like to contribute to this project, please fork the repository and submit a pull request with your changes.

## Troubleshooting

- If you encounter any issues related to missing modules or dependencies, make sure you have installed all required packages as mentioned in the Installation section.
- If you're getting API-related errors, check that your TiDB AI API key is correctly set in your environment variables.
- For any LLM-related issues, ensure your OpenAI API key is properly configured.
- Ensure that Ollama is running if you have set `LLM_PROVIDER=ollama` in your `.env` file.
- If you're having issues with tool access, verify that the tools are properly registered in the namespace you're using.
