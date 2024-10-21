"""
Visualization module for the VM execution and Git repository management.
"""

import json
import os
import logging
from git import Repo, git
from git.exc import GitCommandError
from readerwriterlock import rwlock
from contextlib import contextmanager

from app.services import GitManager, commit_message_wrapper

logger = logging.getLogger(__name__)


class RepoManager:
    def __init__(self, base_path):
        self.base_path = base_path
        self.repos = {}
        self.locks = {}
        self.repos_lock = rwlock.RWLockFair()  # Read-write lock for repos and locks
        self.load_repos(base_path)

    def load_repos(self, base_path):
        with self.repos_lock.gen_wlock():
            for repo_name in os.listdir(base_path):
                if repo_name.startswith("."):
                    continue
                self.repos[repo_name] = GitManager(os.path.join(base_path, repo_name))
                self.locks[repo_name] = rwlock.RWLockFair()

    def get_repo(self, repo_name):
        with self.repos_lock.gen_rlock():
            return self.repos.get(repo_name)

    def get_or_create_repo(self, repo_name):
        with self.repos_lock.gen_rlock():
            repo = self.repos.get(repo_name)
            if repo:
                return repo

        # If repo is not found, acquire write lock to add it
        with self.repos_lock.gen_wlock():
            # Double-checked locking
            repo = self.repos.get(repo_name)
            if not repo:
                repo = GitManager(os.path.join(self.base_path, repo_name))
                self.repos[repo_name] = repo
                self.locks[repo_name] = rwlock.RWLockFair()
            return repo

    def repo_exists(self, repo_name):
        with self.repos_lock.gen_rlock():
            repo_path = os.path.join(self.base_path, repo_name)
            return os.path.exists(repo_path) and os.path.isdir(
                os.path.join(repo_path, ".git")
            )

    @contextmanager
    def lock_repo_for_write(self, repo_name, timeout=10):
        """
        Context manager to acquire a write lock for a specific repository.
        Ensures that write operations are mutually exclusive.
        """
        with self.repos_lock.gen_rlock():
            lock = self.locks.get(repo_name)
            if not lock:
                raise ValueError(f"No lock found for repository '{repo_name}'")

        w_lock = lock.gen_wlock()
        acquired = w_lock.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(
                f"Could not acquire write lock for repository '{repo_name}' within {timeout} seconds."
            )
        try:
            yield
        finally:
            w_lock.release()

    @contextmanager
    def lock_repo_for_read(self, repo_name, timeout=300):
        """
        Context manager to acquire a read lock for a specific repository.
        Allows multiple concurrent read operations.
        """
        with self.repos_lock.gen_rlock():
            lock = self.locks.get(repo_name)
            if not lock:
                raise ValueError(f"No lock found for repository '{repo_name}'")

        r_lock = lock.gen_rlock()
        acquired = r_lock.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(
                f"Could not acquire read lock for repository '{repo_name}' within {timeout} seconds."
            )
        try:
            yield
        finally:
            r_lock.release()


def get_repo(repo_path):
    """Initialize and return a Git repository object."""
    try:
        return Repo(repo_path)
    except Exception as exc:
        logger.error(
            "Failed to initialize repository at %s: %s",
            repo_path,
            str(exc),
            exc_info=True,
        )
        return None


def get_commits(repo, branch_name):
    """Fetch commits for a given branch."""
    try:
        return list(repo.iter_commits(branch_name))
    except GitCommandError as exc:
        logger.error(
            "Error fetching commits for branch %s: %s",
            branch_name,
            str(exc),
            exc_info=True,
        )
        return []


def get_vm_state_for_commit(repo, commit):
    """Retrieve VM state from a specific commit."""
    try:
        vm_state_content = repo.git.show(f"{commit.hexsha}:vm_state.json")
        return json.loads(vm_state_content)
    except GitCommandError:
        logger.error("vm_state.json not found in commit %s", commit.hexsha)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in vm_state.json for commit %s", commit.hexsha)
    return None


def commit_vm_changes(vm):
    if commit_message_wrapper.get_commit_message():
        commit_hash = vm.git_manager.commit_changes(
            commit_message_wrapper.get_commit_message()
        )
        if commit_hash:
            logger.info(f"Committed changes: {commit_hash}")
        else:
            logger.warning("Failed to commit changes")
        commit_message_wrapper.clear_commit_message()
        return commit_hash
    return None
