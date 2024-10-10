# StackVM

## Installation

To run this project, you need to install the required dependencies. You can do this using pip:


```bash
pip install Flask GitPython openai requests
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
   python visualization.py --goal "summary the performance improvement of tidb from version 6.5 to newest version"
   ```

2. **Debug and Optimize Your Goal**: 
   To debug and optimize your goal, run:
   ```bash
   python visualization.py --server
   ```

3. **Access the Web Interface**: 
   Use your browser to open [http://127.0.0.1:5000/](http://127.0.0.1:5000/).

## Project Structure

- `visualization.py`: Main script for running the visualization, handling requests, and managing the VM execution.
- `vm.py`: Contains the VM logic and execution handling.
- `utils.py`: Utility functions for loading and saving state, parsing commit messages, etc.
- `git_manager.py`: Manages interactions with the Git repository.
- `config.py`: Configuration settings, including repository paths and LLM model selection.
- `templates/index.html`: HTML template for the web interface.
- `spec.md`: Specifications and requirements for the project.
- `instruction_handlers.py`: Handles various instructions and commands, including knowledge graph retrieval and vector search.
- `llm_interface.py`: Interface for interacting with the language model.
- `prompts.py`: Contains prompt templates for various LLM interactions.
- `commit_message_wrapper.py`: Wrapper for managing commit messages.

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

