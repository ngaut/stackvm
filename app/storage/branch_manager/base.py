from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List


class BranchManager(ABC):
    """Abstract base class for branch and commit management."""

    @abstractmethod
    def list_branches(self) -> List[str]:
        """List all branches."""

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
    def get_latest_commit(self, branch_name: Optional[str] = "main") -> Dict[str, Any]:
        """Get the latest commit for specified branch"""

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
