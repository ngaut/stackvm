import subprocess
import logging
import os
from typing import List  # Add this import

class GitManager:
    def __init__(self, repo_path: str, readme_content: str = None):
        self.repo_path = repo_path
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')  # Updated formatter to include filename and line number
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        # Create the directory if it doesn't exist
        if not os.path.exists(self.repo_path):
            os.makedirs(self.repo_path)
            self.logger.info(f"Created directory: {self.repo_path}")
        
        # Initialize the repository if it's not already a Git repo
        if not os.path.exists(os.path.join(self.repo_path, '.git')):
            self.init_repo(readme_content)
        
        self.bare_repo_path = repo_path + '_bare.git'
        if not os.path.exists(self.bare_repo_path):
            self.init_bare_repo()

    def init_repo(self, readme_content: str = None):
        if readme_content is None:
            readme_content = "Initial commit."  # Set a default README content
        
        if self.run_command(['git', 'init']):
            self.logger.info(f"Initialized new Git repository in {self.repo_path}")
            
            # Rename the default branch to 'main'
            if not self.run_command(['git', 'branch', '-M', 'main']):
                self.logger.error("Failed to rename branch to 'main'.")
                return  # Exit if renaming fails to avoid further issues
            
            # Create an initial commit with the README.md
            readme_path = os.path.join(self.repo_path, 'README.md')
            try:
                with open(readme_path, 'w') as f:
                    f.write(readme_content)
                self.logger.info(f"Created README.md at {readme_path}")
            except Exception as e:
                self.logger.error(f"Failed to create README.md: {e}")
                return  # Exit if README creation fails
            
            if self.commit_changes("Initial commit"):
                self.logger.info("Created initial commit on 'main' branch.")
            else:
                self.logger.error("Failed to create initial commit.")
        else:
            self.logger.error(f"Failed to initialize Git repository in {self.repo_path}")
    
    def init_bare_repo(self):
        subprocess.run(['git', 'init', '--bare', self.bare_repo_path], check=True)
        self.run_command(['git', 'remote', 'add', 'origin', self.bare_repo_path])
        self.run_command(['git', 'push', '-u', 'origin', 'main'])

    def run_command(self, command: List[str]) -> bool:
        try:
            subprocess.check_output(command, cwd=self.repo_path, stderr=subprocess.STDOUT)
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Git command {' '.join(command)} failed: {e.output.decode()}")
            return False
    
    def commit_changes(self, message: str) -> bool:
        if not self.run_command(['git', 'add', '.']):
            return False
        result = self.run_command(['git', 'commit', '-m', message])
        if not result:
            output = subprocess.check_output(['git', 'status'], cwd=self.repo_path, stderr=subprocess.STDOUT).decode()
            if "nothing to commit, working tree clean" in output:
                self.logger.info("No changes to commit.")
                return True
        return result
    
    def push_changes(self, message: str) -> bool:
        if not self.commit_changes(message):
            return False
        return self.run_command(['git', 'push', 'origin', 'HEAD'])
    
    def pull_changes(self) -> bool:
        return self.run_command(['git', 'pull', 'origin', 'main'])
    
    def create_branch(self, branch_name: str) -> bool:
        if not self.run_command(['git', 'branch', branch_name]):
            self.logger.error(f"Failed to create branch '{branch_name}'.")
            return False
        self.logger.info(f"Branch '{branch_name}' created.")
        return True

    def checkout_branch(self, branch_name: str) -> bool:
        if not self.run_command(['git', 'checkout', branch_name]):
            self.logger.error(f"Failed to checkout branch '{branch_name}'.")
            return False
        self.logger.info(f"Checked out branch '{branch_name}'.")
        return True

    def list_branches(self) -> List[str]:
        try:
            output = subprocess.check_output(['git', 'branch'], cwd=self.repo_path, stderr=subprocess.STDOUT)
            branches = output.decode().split('\n')
            branches = [branch.strip('* ').strip() for branch in branches if branch]
            return branches
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to list branches: {e.output.decode()}")
            return []

    def merge_branch(self, branch: str) -> bool:
        """
        Merges the specified branch into the current branch.

        Args:
            branch (str): The name of the branch to merge.

        Returns:
            bool: True if the merge was successful, False otherwise.
        """
        if not self.run_command(['git', 'merge', branch]):
            self.logger.error(f"Failed to merge branch '{branch}' into '{self.repo_path}'.")
            return False
        self.logger.info(f"Successfully merged branch '{branch}' into '{self.repo_path}'.")
        return True