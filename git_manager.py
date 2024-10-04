import subprocess
import logging
import os
from typing import List, Optional  # Added Optional

class GitManager:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.logger = logging.getLogger('git_manager')
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - git_manager - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        # Create the repository directory if it doesn't exist
        if not os.path.exists(self.repo_path):
            os.makedirs(self.repo_path)
            self.logger.info(f"Created directory: {self.repo_path}")

        # Initialize the repository if it's not already a Git repo
        if not os.path.exists(os.path.join(self.repo_path, '.git')):
            self.init_repo()

    def init_repo(self) -> None:
        # Initialize a new Git repository with 'main' as the initial branch
        init_command = ['git', 'init', '--initial-branch=main']
        if self.run_command(init_command):
            self.logger.info(f"Initialized new Git repository in {self.repo_path}")

            # Create a README.md file
            readme_path = os.path.join(self.repo_path, 'README.md')
            with open(readme_path, 'w') as f:
                f.write("# Auto-generated repository\n")
            self.logger.info(f"Created README.md at {readme_path}")

            # Add and commit the README.md
            self.run_command(['git', 'add', 'README.md'])
            if not self.commit_changes("Initial commit"):
                self.logger.error("Failed to create initial commit.")
        else:
            self.logger.error(f"Failed to initialize Git repository in {self.repo_path}")

    def run_command(self, command: List[str]) -> bool:
        try:
            subprocess.check_output(command, cwd=self.repo_path, stderr=subprocess.STDOUT)
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Git command {' '.join(command)} failed: {e.output.decode()}")
            return False

    def commit_changes(self, commit_message: str) -> bool:
        # Add all changes, including untracked files
        add_command = ['git', 'add', '-A']
        add_result = self.run_command(add_command)
        if not add_result:
            self.logger.error("Failed to add changes to Git index.")
            return False

        commit_command = ['git', 'commit', '-m', commit_message]
        return self.run_command(commit_command)

    def get_current_branch(self) -> Optional[str]:
        try:
            output = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=self.repo_path, stderr=subprocess.STDOUT)
            branch = output.decode().strip()
            return branch
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to get current branch: {e.output.decode()}")
            return None

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
