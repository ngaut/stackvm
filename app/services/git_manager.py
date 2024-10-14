import os
from git import Repo, GitCommandError
import logging
import json
from typing import Optional, Dict, Any
from .utils import StepType


def get_commit_message_schema(
    step_type: str,
    seq_no: str,
    description: str,
    input_parameters: Dict[str, Any],
    output_variables: Dict[str, Any],
) -> str:
    """Generate a commit message schema in JSON format."""
    commit_info = {
        "type": step_type,
        "seq_no": seq_no,
        "description": description,
        "input_parameters": input_parameters,
        "output_variables": output_variables,
    }
    return json.dumps(commit_info)


class CommitMessageWrapper:
    def __init__(self):
        self.commit_message: Optional[str] = None

    def set_commit_message(
        self,
        step_type: StepType,
        seq_no: str,
        description: str,
        input_parameters: Dict[str, Any],
        output_variables: Dict[str, Any],
    ) -> None:
        commit_info = {
            "type": step_type.value,
            "seq_no": seq_no,
            "description": description,
            "input_parameters": input_parameters,
            "output_variables": output_variables,
        }
        # Set the commit message using the commit_info dictionary
        self.commit_message = json.dumps(commit_info)

    def get_commit_message(self) -> Optional[str]:
        return self.commit_message

    def clear_commit_message(self) -> None:
        self.commit_message = None


commit_message_wrapper = CommitMessageWrapper()


class GitManager:
    def __init__(self, repo_path):
        self.repo_path = repo_path
        self.logger = logging.getLogger(__name__)
        self.repo = self._initialize_repo()

    def _initialize_repo(self):
        if not os.path.exists(self.repo_path):
            os.makedirs(self.repo_path)
            self.logger.info(f"Created directory: {self.repo_path}")

        if not os.path.exists(os.path.join(self.repo_path, ".git")):
            repo = Repo.init(self.repo_path)
            self.logger.info(f"Initialized new Git repository in {self.repo_path}")

            # Create and commit an initial README.md file
            readme_path = os.path.join(self.repo_path, "README.md")
            with open(readme_path, "w") as f:
                f.write(
                    "# VM Execution Repository\n\nThis repository contains the execution history of the VM."
                )
            self.logger.info(f"Created README.md at {readme_path}")

            repo.index.add(["README.md"])
            # add a empty vm_state.json
            vm_state_path = os.path.join(self.repo_path, "vm_state.json")
            with open(vm_state_path, "w") as f:
                f.write("{}")
            repo.index.add(["vm_state.json"])
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
                self.logger.info(
                    f"No changes to commit, returning the latest commit hash {self.repo.head.commit.hexsha}"
                )
                return (
                    self.repo.head.commit.hexsha
                )  # Return the commit hash as a string
        except Exception as e:
            self.logger.error(f"Error committing changes: {str(e)}")
            return None

    def list_branches(self):
        return [branch.name for branch in self.repo.branches]

    def create_branch(self, branch_name):
        try:
            self.repo.create_head(branch_name)
            return True
        except GitCommandError as e:
            self.logger.error(f"Failed to create branch {branch_name}: {str(e)}")
            return False

    def checkout_branch(self, branch_name):
        try:
            self.repo.git.checkout(branch_name)
            return True
        except GitCommandError as e:
            self.logger.error(f"Failed to checkout branch {branch_name}: {str(e)}")
            return False

    def get_current_branch(self):
        return self.repo.active_branch.name

    def create_branch_from_commit(self, branch_name, commit_hash=None):
        try:
            # If commit_hash is None, use the latest commit of the current branch
            if not commit_hash:
                commit_hash = self.repo.head.commit.hexsha

            # Create a new branch from the specified commit hash
            self.repo.git.branch(branch_name, commit_hash)
            self.logger.info(f"Created branch {branch_name} from commit {commit_hash}")
            return True
        except GitCommandError as e:
            self.logger.error(
                f"Failed to create branch {branch_name} from commit {commit_hash}: {str(e)}"
            )
            return False
