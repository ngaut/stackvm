from datetime import datetime
import os
from git import Repo, GitCommandError, NULL_TREE
import logging
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

from .utils import StepType, parse_commit_message

logger = logging.getLogger(__name__)


class BranchManager(ABC):
    """Abstract base class for branch and commit management."""

    @abstractmethod
    def list_branches(self) -> List[str]:
        """List all branches."""

    @abstractmethod
    def create_branch(self, branch_name: str) -> bool:
        """Create a new branch."""

    @abstractmethod
    def checkout_branch(self, branch_name: str) -> bool:
        """Switch to the specified branch."""

    @abstractmethod
    def delete_branch(self, branch_name: str) -> bool:
        """Delete the specified branch."""

    @abstractmethod
    def get_current_branch(self) -> str:
        """Get the name of the current active branch."""

    @abstractmethod
    def checkout_branch_from_commit(
        self, branch_name: str, commit_hash: Optional[str] = None
    ) -> bool:
        """Create a new branch from the specified commit hash."""

    @abstractmethod
    def get_current_commit_hash(self) -> str:
        """Retrieve the current commit hash."""

    @abstractmethod
    def get_parent_commit_hash(self, commit_hash: str) -> str:
        """Retrieve the parent commit hash based on the commit hash."""

    @abstractmethod
    def get_commits(self, branch_name: str) -> List[Any]:
        """Get all commits from the specified branch."""

    @abstractmethod
    def get_commit(self, commit_hash: str) -> Any:
        """Get the commit object based on the commit hash."""

    @abstractmethod
    def load_state(self, commit_hash: str) -> Optional[Dict[str, Any]]:
        """Load the state from a specific commit."""

    @abstractmethod
    def update_state(self, state: Dict[str, Any]) -> None:
        """Update the state to the current commit."""

    @abstractmethod
    def get_state_diff(self, commit_hash: str) -> str:
        """Get the state differences introduced by the specified commit."""

    @abstractmethod
    def commit_changes(self, commit_info: Dict[str, Any]) -> Optional[str]:
        """Commit changes and return the commit hash."""


class GitManager(BranchManager):
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

    def list_branches(self):
        branches = self.repo.branches
        branch_data = [
            {
                "name": branch.name,
                "last_commit_date": branch.commit.committed_datetime.isoformat(),
                "last_commit_message": branch.commit.message.split("\n")[0],
                "is_active": branch.name == self.get_current_branch(),
            }
            for branch in branches
        ]
        branch_data.sort(
            key=lambda x: (-x["is_active"], x["last_commit_date"]), reverse=True
        )
        return branch_data

    def create_branch(self, branch_name: str) -> bool:
        try:
            self.repo.create_head(branch_name)
            return True
        except GitCommandError as e:
            logger.error("Failed to create branch %s: %s", branch_name, str(e))
            return False

    def checkout_branch(self, branch_name):
        try:
            # Check if the branch exists
            if branch_name not in self.repo.branches:
                logger.error("Branch %s does not exist.", branch_name)
                return False

            # Attempt to checkout the branch
            self.repo.git.checkout(branch_name)
            logger.info("Checked out branch %s.", branch_name)
            return True
        except GitCommandError as e:
            # Log specific error details
            logger.error("Failed to checkout branch %s: %s", branch_name, str(e))
            return False

    def delete_branch(self, branch_name):
        if branch_name == self.get_current_branch():
            available_branches = [
                b.name for b in self.list_branches() if b.name != branch_name
            ]
            if not available_branches:
                raise ValueError(f"Cannot delete the only branch {branch_name}")

            switch_to = (
                "main" if "main" in available_branches else available_branches[0]
            )
            self.checkout_branch(switch_to)
            logger.info(f"Switched to branch {switch_to} before deleting {branch_name}")

        self.repo.git.branch("-D", branch_name)

    def get_current_branch(self):
        return self.repo.active_branch.name

    def checkout_branch_from_commit(self, branch_name, commit_hash=None):
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

    def get_current_commit_hash(self):
        """Retrieve the latest commit hash of the current branch."""
        return self.repo.head.commit.hexsha

    def get_parent_commit_hash(self, commit_hash: str) -> str:
        """Retrieve the parent commit hash based on the commit hash."""
        commit = self.repo.commit(commit_hash)
        if commit.parents:
            return commit.parents[0].hexsha
        else:
            return None

    def get_commits(self, branch_name: str) -> List[Any]:
        """Get all commits from the specified branch."""
        try:
            commits = list(self.repo.iter_commits(branch_name))
            vm_states = []
            for commit in commits:
                commit_time = datetime.fromtimestamp(commit.committed_date)
                seq_no, title, details, commit_type = parse_commit_message(
                    commit.message
                )

                vm_state = self.load_state(commit.hexsha)
                vm_states.append(
                    {
                        "time": commit_time.isoformat(),
                        "title": title,
                        "details": details,
                        "commit_hash": commit.hexsha,
                        "seq_no": seq_no,
                        "vm_state": vm_state,
                        "commit_type": commit_type,
                        "message": commit.message,
                    }
                )
            return vm_states
        except Exception as e:
            logger.error(
                "Error fetching commits for branch %s: %s",
                branch_name,
                str(e),
                exc_info=True,
            )
            raise e

    def get_commit(self, commit_hash: str) -> Any:
        try:
            commit = self.repo.commit(commit_hash)
            commit_time = datetime.fromtimestamp(commit.committed_date)
            seq_no, title, details, commit_type = parse_commit_message(commit.message)

            vm_state = self.load_state(commit.hexsha)
            return {
                "time": commit_time.isoformat(),
                "title": title,
                "details": details,
                "commit_hash": commit.hexsha,
                "seq_no": seq_no,
                "vm_state": vm_state,
                "commit_type": commit_type,
                "message": commit.message,
            }
        except Exception as e:
            logger.error(
                "Error fetching commit for hash %s: %s",
                commit_hash,
                str(e),
                exc_info=True,
            )
            raise e

    def commit_changes(self, commit_info: Dict[str, Any]) -> Optional[str]:
        try:
            commit_message = json.dumps(commit_info)
            self.repo.git.add(all=True)
            if self.repo.is_dirty(untracked_files=True):
                commit = self.repo.index.commit(commit_message)
                return commit.hexsha  # Return the commit hash as a string
            else:
                # If there are no changes to commit, return the latest commit hash
                logger.info(
                    "No changes to commit, returning the latest commit hash %s",
                    self.repo.head.commit.hexsha,
                )
                return self.repo.head.commit.hexsha
        except Exception as e:
            logger.error("Error committing changes: %s", str(e))
            raise e

    def load_state(self, commit_hash: str) -> Optional[Dict[str, Any]]:
        """Load the state from a specific commit."""
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

    def update_state(self, state: Dict[str, Any]) -> None:
        """Update the state to the current commit."""
        try:
            state_file = os.path.join(self.repo_path, "vm_state.json")
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2, default=str, sort_keys=True)
        except Exception as e:
            logger.error(f"Error saving state: {str(e)}")
            raise e

    def get_state_diff(self, commit_hash: str) -> str:
        commit = self.repo.commit(commit_hash)
        if commit.parents:
            parent = commit.parents[0]
            return self.repo.git.diff(parent, commit, "--unified=3")
        else:
            return self.repo.git.show(
                commit, "--pretty=format:", "--no-commit-id", "-p"
            )
