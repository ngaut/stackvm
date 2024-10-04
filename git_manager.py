import os
import git
from git import Repo
import logging

class GitManager:
    def __init__(self, repo_path):
        self.repo_path = repo_path
        self.logger = logging.getLogger(__name__)
        self.repo = self._initialize_repo()

    def _initialize_repo(self):
        if not os.path.exists(self.repo_path):
            os.makedirs(self.repo_path)
            self.logger.info(f"Created directory: {self.repo_path}")

        if not os.path.exists(os.path.join(self.repo_path, '.git')):
            repo = Repo.init(self.repo_path)
            self.logger.info(f"Initialized new Git repository in {self.repo_path}")
            
            # Create and commit an initial README.md file
            readme_path = os.path.join(self.repo_path, 'README.md')
            with open(readme_path, 'w') as f:
                f.write('# VM Execution Repository\n\nThis repository contains the execution history of the VM.')
            self.logger.info(f"Created README.md at {readme_path}")
            
            repo.index.add(['README.md'])
            repo.index.commit("Initial commit")
        else:
            repo = Repo(self.repo_path)
            self.logger.info(f"Opened existing Git repository in {self.repo_path}")

        return repo

    def commit_changes(self, message):
        try:
            self.repo.git.add(all=True)
            if self.repo.is_dirty():
                self.repo.index.commit(message)
                self.logger.info(f"Committed changes with message: {message}")
                return True
            else:
                self.logger.info("No changes to commit.")
                return False
        except git.GitCommandError as e:
            self.logger.error(f"Git commit failed: {str(e)}")
            return False

    def run_command(self, command):
        try:
            result = self.repo.git.execute(command)
            return result
        except git.GitCommandError as e:
            self.logger.error(f"Git command failed: {str(e)}")
            return None

    def list_branches(self):
        return [branch.name for branch in self.repo.branches]

    def create_branch(self, branch_name):
        try:
            self.repo.create_head(branch_name)
            self.logger.info(f"Created new branch: {branch_name}")
            return True
        except git.GitCommandError as e:
            self.logger.error(f"Failed to create branch {branch_name}: {str(e)}")
            return False

    def checkout_branch(self, branch_name):
        try:
            self.repo.git.checkout(branch_name)
            self.logger.info(f"Checked out branch: {branch_name}")
            return True
        except git.GitCommandError as e:
            self.logger.error(f"Failed to checkout branch {branch_name}: {str(e)}")
            return False
