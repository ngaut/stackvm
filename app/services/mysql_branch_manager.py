import logging
import uuid
import json
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import scoped_session, Session
from deepdiff import DeepDiff
from contextlib import contextmanager

from app.database import SessionLocal
from app.models.branch import Branch, Commit
from .branch_manager import BranchManager
from .utils import parse_commit_message

logger = logging.getLogger(__name__)

Scoped_Session = scoped_session(SessionLocal)

class MySQLBranchManager(BranchManager):
    def __init__(self, task_id: str):
        """Initialize MySQL branch manager for a specific task."""
        self.task_id = task_id

        # In-memory state
        self._current_branch_name = None
        self._current_commit_hash = None
        self.current_state = {}

        # Initialize to main branch if it exists, or create it
        with self.get_session() as session:
            main_branch = self._get_branch(session, "main")
            if main_branch:
                self._current_branch_name = "main"
                self._current_commit_hash = main_branch.head_commit_hash
                self.current_state = main_branch.head_commit.vm_state
                return

        # create main branch if it doesn't exist
        self.create_branch("main")

    @contextmanager
    def get_session(self):
        """Provide a transactional scope around a series of operations."""
        session = Scoped_Session()
        try:
            yield session
        finally:
            session.close()
            Scoped_Session.remove()  # Important! Remove session from registry

    def _get_branch(self, session: Session, branch_name: str) -> Optional[Branch]:
        """Helper method to get a branch by name."""
        return (
            session.query(Branch)
            .filter(Branch.task_id == self.task_id, Branch.name == branch_name)
            .first()
        )

    def _get_commit(self, session: Session, commit_hash: str) -> Optional[Commit]:
        """Helper method to get a commit by hash."""
        return (
            session.query(Commit)
            .filter(Commit.task_id == self.task_id, Commit.commit_hash == commit_hash)
            .first()
        )

    def list_branches(self) -> List[Dict[str, Any]]:
        """List all branches with their latest commits."""
        with self.get_session() as session:
            branches = (
                session.query(Branch).filter(Branch.task_id == self.task_id).all()
            )

            branch_data = []
            for branch in branches:
                branch_data.append(
                    {
                        "name": branch.name,
                        "last_commit_date": branch.head_commit.committed_at.isoformat(),
                        "last_commit_hash": branch.head_commit_hash,
                        "last_commit_message": branch.head_commit.message,
                        "is_active": branch.name == self._current_branch_name,
                    }
                )

            # Sort branches by active status and commit date
            branch_data.sort(
                key=lambda x: (-x["is_active"], x["last_commit_date"]), reverse=True
            )
            return branch_data

    def create_branch(self, branch_name: str) -> bool:
        """Create a new branch."""
        try:
            with self.get_session() as session:
                if self._get_branch(session, branch_name):
                    logger.error("Branch %s already exists", branch_name)
                    return False

                # If this is the first branch (main), create initial commit
                if not self._current_commit_hash:
                    if branch_name != "main":
                        raise ValueError(
                            "Main branch is not created, unexpected branch name: %s",
                            branch_name,
                        )

                    initial_commit = Commit(
                        commit_hash=str(uuid.uuid4().hex),
                        task_id=self.task_id,
                        message={"description": "Initial commit"},
                        vm_state={},
                    )
                    session.add(initial_commit)
                    session.flush()  # Get the commit hash
                    self._current_commit_hash = initial_commit.commit_hash

                # Create new branch pointing to current commit
                new_branch = Branch(
                    name=branch_name,
                    task_id=self.task_id,
                    head_commit_hash=self._current_commit_hash,
                )
                session.add(new_branch)
                session.commit()

                # Update current branch if this is the first branch
                if not self._current_branch_name:
                    self._current_branch_name = branch_name

                return True
        except Exception as e:
            logger.error("Failed to create branch %s: %s", branch_name, str(e))
            session.rollback()
            return False

    def _checkout_branch(self, session: Session, branch_name: str) -> bool:
        """Switch to the specified branch."""
        branch = self._get_branch(session, branch_name)
        if not branch:
            logger.error("Branch %s does not exist", branch_name)
            return False

        self._current_branch_name = branch_name
        self._current_commit_hash = branch.head_commit_hash
        self.current_state = branch.head_commit.vm_state
        return True

    def checkout_branch(self, branch_name: str) -> bool:
        """Switch to the specified branch."""
        with self.get_session() as session:
            return self._checkout_branch(session, branch_name)

    def checkout_branch_from_commit(
        self, branch_name: str, commit_hash: Optional[str] = None
    ) -> bool:
        """Create a new branch from the specified commit hash."""
        try:
            with self.get_session() as session:
                # Use current commit if none specified
                if not commit_hash:
                    commit_hash = self._current_commit_hash

                commit = self._get_commit(session, commit_hash)
                if not commit:
                    logger.error("Commit %s does not exist", commit_hash)
                    return False

                # Create new branch pointing to the specified commit
                new_branch = Branch(
                    name=branch_name,
                    task_id=self.task_id,
                    head_commit_hash=commit_hash,
                )
                session.add(new_branch)
                session.commit()

                # Switch to the new branch
                return self._checkout_branch(session, branch_name)
        except Exception as e:
            logger.error(
                "Failed to create branch %s from commit %s: %s",
                branch_name,
                commit_hash,
                str(e),
            )
            session.rollback()
            return False

    def delete_branch(self, branch_name: str) -> bool:
        """Delete the specified branch."""
        try:
            with self.get_session() as session:
                branch = self._get_branch(session, branch_name)
                if not branch:
                    logger.error("Branch %s does not exist", branch_name)
                    return False

                if branch_name == self._current_branch_name:
                    # Find another branch to switch to
                    other_branch = (
                        session.query(Branch)
                        .filter(
                            Branch.task_id == self.task_id, Branch.name != branch_name
                        )
                        .first()
                    )

                    if not other_branch:
                        raise ValueError(f"Cannot delete the only branch {branch_name}")

                    # Update in-memory state
                    self._current_branch_name = other_branch.name
                    self._current_commit_hash = other_branch.head_commit_hash
                    self.current_state = other_branch.head_commit.vm_state

                session.delete(branch)
                session.commit()
                return True
        except Exception as e:
            logger.error("Failed to delete branch %s: %s", branch_name, str(e))
            session.rollback()
            return False

    def get_current_branch(self) -> str:
        """Get the name of the current active branch."""
        if not self._current_branch_name:
            self.checkout_branch("main")
        return self._current_branch_name

    def get_current_commit_hash(self) -> str:
        """Get the current commit hash."""
        return self._current_commit_hash

    def get_parent_commit_hash(self, commit_hash: str) -> Optional[str]:
        """Get the parent commit hash."""
        with self.get_session() as session:
            commit = self._get_commit(session, commit_hash)
            return commit.parent_hash if commit else None

    def get_commits(self, branch_name: str) -> List[Dict[str, Any]]:
        """Get all commits in the branch's history."""
        with self.get_session() as session:
            branch = self._get_branch(session, branch_name)
            if not branch:
                return []

            commits = []
            current_hash = branch.head_commit_hash

            while current_hash:
                commit = self._get_commit(session, current_hash)
                if not commit:
                    break

                seq_no, title, details, commit_type = parse_commit_message(
                    commit.message
                )

                commits.append(
                    {
                        "time": commit.committed_at.isoformat(),
                        "title": title,
                        "details": details,
                        "commit_hash": commit.commit_hash,
                        "seq_no": seq_no,
                        "vm_state": commit.vm_state,
                        "commit_type": commit_type,
                        "message": commit.message,
                    }
                )

                current_hash = commit.parent_hash

            return commits

    def get_commit(self, commit_hash: str) -> Optional[Dict[str, Any]]:
        """Get a specific commit."""
        with self.get_session() as session:
            commit = self._get_commit(session, commit_hash)
            if not commit:
                return None

            seq_no, title, details, commit_type = parse_commit_message(
                commit.message.get("description", "")
            )

            return {
                "time": commit.committed_at.isoformat(),
                "title": title,
                "details": details,
                "commit_hash": commit.commit_hash,
                "seq_no": seq_no,
                "vm_state": commit.vm_state,
                "commit_type": commit_type,
                "message": commit.message,
            }

    def commit_changes(self, commit_info: Dict[str, Any]) -> Optional[str]:
        """Create a new commit and update branch pointer."""
        try:
            with self.get_session() as session:
                if not self._current_branch_name:
                    raise ValueError("No active branch")

                # Generate commit hash
                commit_hash = str(uuid.uuid4().hex)

                # Create new commit
                new_commit = Commit(
                    commit_hash=commit_hash,
                    task_id=self.task_id,
                    parent_hash=self._current_commit_hash,
                    message=commit_info,
                    vm_state=self.current_state,
                )

                session.add(new_commit)

                # Update branch pointer
                branch = self._get_branch(session, self._current_branch_name)
                branch.head_commit_hash = commit_hash

                session.add(branch)

                session.commit()

                # Update current commit hash
                self._current_commit_hash = commit_hash

                return commit_hash
        except Exception as e:
            session.rollback()
            logger.error("Error committing changes: %s", str(e))
            return None

    def load_state(self, commit_hash: str) -> Optional[Dict[str, Any]]:
        """Load state from a specific commit."""
        with self.get_session() as session:
            commit = self._get_commit(session, commit_hash)
            return commit.vm_state if commit else None

    def update_state(self, state: Dict[str, Any]) -> None:
        """Update the current state."""
        self.current_state = state

    def get_state_diff(self, commit_hash: str) -> str:
        """Get state differences between a commit and its parent."""
        with self.get_session() as session:
            commit = self._get_commit(session, commit_hash)
            if not commit:
                return ""

            if not commit.parent_hash:
                return "Initial commit:\n" + json.dumps(commit.vm_state, indent=2)

            parent = self._get_commit(session, commit.parent_hash)
            if not parent:
                return ""

            # Use DeepDiff for detailed comparison
            diff = DeepDiff(parent.vm_state, commit.vm_state, verbose_level=2)

            # Format the diff in a git-like style
            formatted_diff = []

            if "dictionary_item_added" in diff:
                formatted_diff.append("Added:")
                for item in diff["dictionary_item_added"]:
                    path = item.replace("root", "")
                    value = eval(f"commit.vm_state{path}")
                    formatted_diff.append(f"  + {path}: {json.dumps(value)}")

            if "dictionary_item_removed" in diff:
                formatted_diff.append("\nRemoved:")
                for item in diff["dictionary_item_removed"]:
                    path = item.replace("root", "")
                    value = eval(f"parent.vm_state{path}")
                    formatted_diff.append(f"  - {path}: {json.dumps(value)}")

            if "values_changed" in diff:
                formatted_diff.append("\nModified:")
                for path, change in diff["values_changed"].items():
                    path = path.replace("root", "")
                    formatted_diff.append(f"  ~ {path}:")
                    formatted_diff.append(f"    - {json.dumps(change['old_value'])}")
                    formatted_diff.append(f"    + {json.dumps(change['new_value'])}")

            return "\n".join(formatted_diff)
