"""
Visualization module for the VM execution and Git repository management.
"""

import json
import os
import logging
from git import Repo
from git.exc import GitCommandError

from app.config.settings import GIT_REPO_PATH
from app.services import GitManager, commit_message_wrapper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
)


class CurrentRepo:
    def __init__(self, repo_path):
        self.git_manager = GitManager(repo_path)

    def get_current_repo_path(self):
        return self.git_manager.repo_path
    
    def set_repo(self, repo_path):
        self.git_manager = GitManager(repo_path)

global_repo = CurrentRepo(GIT_REPO_PATH)

def get_repo(repo_path):
    """Initialize and return a Git repository object."""
    try:
        return Repo(repo_path)
    except Exception as exc:
        logging.error(
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
        logging.error(
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
        logging.error("vm_state.json not found in commit %s", commit.hexsha)
    except json.JSONDecodeError:
        logging.error(
            "Invalid JSON in vm_state.json for commit %s", commit.hexsha
        )
    return None


def repo_exists(repo_name):
    repo_path = os.path.join(GIT_REPO_PATH, repo_name)
    return os.path.exists(repo_path) and os.path.isdir(os.path.join(repo_path, ".git"))


def commit_vm_changes(vm):
    if commit_message_wrapper.get_commit_message():
        commit_hash = vm.git_manager.commit_changes(
            commit_message_wrapper.get_commit_message()
        )
        if commit_hash:
            logging.info(f"Committed changes: {commit_hash}")
        else:
            logging.warning("Failed to commit changes")
        commit_message_wrapper.clear_commit_message()
        return commit_hash
    return None
