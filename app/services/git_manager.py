import os
from git import Repo, GitCommandError, NULL_TREE
import logging
import json
from typing import Dict, Any, Optional
from .utils import StepType, parse_commit_message

logger = logging.getLogger(__name__)


class GitManager:
    def __init__(self, repo_path):
        self.repo_path = repo_path
        self.repo = self._initialize_repo()

    def _initialize_repo(self):
        if not os.path.exists(self.repo_path):
            os.makedirs(self.repo_path)
            logger.info("Created directory: %s", self.repo_path)

        if not os.path.exists(os.path.join(self.repo_path, ".git")):
            repo = Repo.init(self.repo_path)
            logger.info("Initialized new Git repository in %s", self.repo_path)

            # Create and commit an initial README.md file
            readme_path = os.path.join(self.repo_path, "README.md")
            with open(readme_path, "w") as f:
                f.write(
                    "# VM Execution Repository\n\nThis repository contains the execution history of the VM."
                )
            logger.info("Created README.md at %s", readme_path)

            repo.index.add(["README.md"])
            # add a empty vm_state.json
            vm_state_path = os.path.join(self.repo_path, "vm_state.json")
            with open(vm_state_path, "w") as f:
                f.write("{}")
            repo.index.add(["vm_state.json"])
            repo.index.commit("Initial commit")
        else:
            repo = Repo(self.repo_path)
            logger.info("Opened existing Git repository in %s", self.repo_path)

        return repo

    def commit_changes(
        self,
        step_type: StepType,
        seq_no: str,
        description: str,
        input_parameters: Dict[str, Any],
        output_variables: Dict[str, Any],
    ):
        commit_info = {
            "type": step_type.value,
            "seq_no": seq_no,
            "description": description,
            "input_parameters": input_parameters,
            "output_variables": output_variables,
        }
        commit_message = json.dumps(commit_info)

        try:
            self.repo.git.add(all=True)
            if self.repo.is_dirty(untracked_files=True):
                commit = self.repo.index.commit(commit_message)
                return commit.hexsha  # Return the commit hash as a string
            else:
                # If there are no changes to commit, return the latest commit hash
                logger.info(
                    f"No changes to commit, returning the latest commit hash {self.repo.head.commit.hexsha}"
                )
                return (
                    self.repo.head.commit.hexsha
                )  # Return the commit hash as a string
        except Exception as e:
            logger.error(f"Error committing changes: {str(e)}")
            return None

    def get_current_commit(self, commit_hash: str):
        return self.repo.commit(commit_hash)

    def list_branches(self):
        return self.repo.branches

    def create_branch(self, branch_name):
        try:
            self.repo.create_head(branch_name)
            return True
        except GitCommandError as e:
            logger.error(f"Failed to create branch {branch_name}: {str(e)}")
            return False

    def checkout_branch(self, branch_name):
        try:
            self.repo.git.checkout(branch_name)
            return True
        except GitCommandError as e:
            logger.error(f"Failed to checkout branch {branch_name}: {str(e)}")
            return False

    def delete_branch(self, branch_name):
        self.repo.git.branch("-D", branch_name)

    def get_current_branch(self):
        return self.repo.active_branch.name

    def create_branch_from_commit(self, branch_name, commit_hash=None):
        try:
            # If commit_hash is None, use the latest commit of the current branch
            if not commit_hash:
                commit_hash = self.repo.head.commit.hexsha

            # Create a new branch from the specified commit hash
            self.repo.git.branch(branch_name, commit_hash)
            logger.info(f"Created branch {branch_name} from commit {commit_hash}")
            return True
        except GitCommandError as e:
            logger.error(
                f"Failed to create branch {branch_name} from commit {commit_hash}: {str(e)}"
            )
            return False

    def get_commits(self, branch_name):
        """Fetch commits for a given branch."""
        try:
            return list(self.repo.iter_commits(branch_name))
        except GitCommandError as exc:
            logger.error(
                "Error fetching commits for branch %s: %s",
                branch_name,
                str(exc),
                exc_info=True,
            )
            return []

    def load_commit_state(self, commit_hash: str) -> Optional[Dict[str, Any]]:
        """Load the state from a file based on the specific commit point."""
        try:
            state_content = self.repo.git.show(f"{commit_hash}:vm_state.json")
            return json.loads(state_content)
        except (GitCommandError, json.JSONDecodeError) as e:
            logger.error(f"Error loading state from commit {commit_hash}: {str(e)}")
        except Exception as e:
            logger.error(
                "Unexpected error loading state from commit %s: %s", commit_hash, str(e)
            )
        return None

    def get_commit(self, commit_hash: str):
        return self.repo.commit(commit_hash)

    def get_code_diff(self, commit_hash: str):
        commit = self.repo.commit(commit_hash)
        if commit.parents:
            parent = commit.parents[0]
            return self.repo.git.diff(parent, commit, "--unified=3")
        else:
            return self.repo.git.show(
                commit, "--pretty=format:", "--no-commit-id", "-p"
            )

    def get_commit_detail(self, commit_hash: str):
        commit = self.get_commit(commit_hash)

        if commit.parents:
            diff = commit.diff(commit.parents[0])
        else:
            diff = commit.diff(NULL_TREE)

        seq_no, _, _, _ = parse_commit_message(commit.message)
        return {
            "hash": commit.hexsha,
            "author": commit.author.name,
            "date": commit.committed_datetime.isoformat(),
            "message": commit.message,
            "seq_no": seq_no,
            "files_changed": [item.a_path for item in diff],
        }
