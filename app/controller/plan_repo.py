"""
Visualization module for the VM execution and Git repository management.
"""

import json
import os
import logging
from git import Repo
from git.exc import GitCommandError
from readerwriterlock import rwlock
from contextlib import contextmanager

from app.services import commit_message_wrapper

logger = logging.getLogger(__name__)

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
