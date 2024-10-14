# StackVM

## Installation

To run this project, you need to install the required dependencies. You can do this using Poetry:


```bash
poetry install
```

## Configuration

Before running the project, make sure to set up your OpenAI API key and TiDB AI API key:


```bash
export OPENAI_API_KEY=your_openai_api_key_here
export TIDB_AI_API_KEY=your_tidb_ai_api_key_here
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
- `app/tools/instruction_handlers.py`: Handles instruction execution and API interactions for knowledge graph searches.
- `main.py`: Entry point for running the VM with a specified goal or starting the visualization server.
- `spec.md`: Specifications and requirements for the project, detailing the VM's functionality and design.

## Features

- Dynamic plan generation and execution using a language model.
- Automatic plan updates based on execution progress and errors.
- Web interface for visualizing VM states, commit history, and code diffs.
- Support for multiple Git repositories and branches.
- Real-time execution of VM steps with commit tracking.
- Knowledge graph retrieval using TiDB AI API.
- Vector search for embedded chunks using TiDB AI API.
- Conditional execution based on LLM evaluation.
- Variable assignment and reasoning steps in the VM execution.

## API Integration

This project integrates with the TiDB AI API for knowledge graph searches and vector searches. Make sure you have a valid API key set up in your environment variables.

## Contributing

If you would like to contribute to this project, please fork the repository and submit a pull request with your changes.

## Troubleshooting

- If you encounter any issues related to missing modules or dependencies, make sure you have installed all required packages as mentioned in the Installation section.
- If you're getting API-related errors, check that your TiDB AI API key is correctly set in your environment variables.
- For any LLM-related issues, ensure your OpenAI API key is properly configured.

## Logging

The project uses Python's logging module to log information, warnings, and errors. Check the logs for detailed information about the execution process and any issues that may arise.

