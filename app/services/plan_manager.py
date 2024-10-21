import os
import shutil
import logging
from app.services import GitManager

logger = logging.getLogger(__name__)

class PlanManager:
    def __init__(self):
        self.logger = logger

    def save_current_plan(self, repo: GitManager, target_directory: str) -> bool:
        """
        Save the current plan's project directory to the specified target directory.

        :param repo_name: Name of the repository to save.
        :param target_directory: Path to the target directory where the plan will be saved.
        :return: True if save is successful, False otherwise.
        """
        source_path = repo.repo_path
        
        if not os.path.exists(source_path):
            self.logger.error(f"Source repository '{repo_name}' does not exist at {source_path}.")
            return False

        if not os.path.exists(target_directory):
            try:
                os.makedirs(target_directory)
                self.logger.info(f"Created target directory at {target_directory}.")
            except Exception as e:
                self.logger.error(f"Failed to create target directory {target_directory}: {str(e)}")
                return False

        destination_path = os.path.join(target_directory, repo_name)
        
        try:
            if os.path.exists(destination_path):
                self.logger.info(f"Destination path '{destination_path}' already exists. Removing it.")
                shutil.rmtree(destination_path)
            shutil.copytree(source_path, destination_path)
            self.logger.info(f"Successfully saved plan '{repo_name}' to '{destination_path}'.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save plan '{repo_name}' to '{destination_path}': {str(e)}")
            return False

