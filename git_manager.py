import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import git
    from git import Repo
except ImportError:
    print("GitPython is not installed. Please install it using: pip install GitPython")
    sys.exit(1)

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
            # add a empty vm_state.json
            vm_state_path = os.path.join(self.repo_path, 'vm_state.json')
            with open(vm_state_path, 'w') as f:
                f.write('{}')
            repo.index.add(['vm_state.json'])
            repo.index.commit("Initial commit")
        else:
            repo = Repo(self.repo_path)
            self.logger.info(f"Opened existing Git repository in {self.repo_path}")

        return repo

    def commit_changes(self, commit_message):
        try:
            self.repo.git.add(all=True)
            if self.repo.is_dirty(untracked_files=True):
                commit = self.repo.index.commit(commit_message)
                return commit.hexsha  # Return the commit hash as a string
            else:
                # If there are no changes to commit, return the latest commit hash
                self.logger.info(f"No changes to commit, returning the latest commit hash {self.repo.head.commit.hexsha}")
                return self.repo.head.commit.hexsha  # Return the commit hash as a string
        except Exception as e:
            self.logger.error(f"Error committing changes: {str(e)}")
            return None

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
