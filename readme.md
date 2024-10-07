# Jarvis

## Installation

To run this project, you need to install the required dependencies. You can do this using pip:


```bash
pip install Flask GitPython
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

- `visualization.py`: Main script for running the visualization and handling requests.
- `vm.py`: Contains the VM logic and execution handling.
- `utils.py`: Utility functions for loading and saving state, parsing commit messages, etc.
- `git_manager.py`: Manages interactions with the Git repository.
- `config.py`: Configuration settings, including repository paths.
- `templates/index.html`: HTML template for the web interface.
- `spec.md`: Specifications and requirements for the project.
- `instruction_handlers.py`: Handles various instructions and commands.

## Contributing

If you would like to contribute to this project, please fork the repository and submit a pull request with your changes.

