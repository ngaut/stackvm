import sys
import os
import math
import json
import random
from typing import List, Dict, Optional, Tuple
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime

from app.utils.json import extract_json
from app.database import SessionLocal
from app.models.branch import Branch, Commit
from app.models.task import Task
from sqlalchemy import select

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from notebooks.optimize_plan import (
    get_task_answer,
    evaulate_task_answer,
)


def get_task(task_id: str) -> Tuple[str, str, str]:
    """Get the task details"""
    with SessionLocal() as session:
        task = session.execute(select(Task).where(Task.id == task_id)).scalar_one()
        return {
            "goal": task.goal,
            "metadata": task.meta,
            "namespace": task.namespace_name,
        }


def get_task_commit_tree(task_id: str) -> Tuple[Dict[str, Dict], Dict[str, str]]:
    """Query all commits and branches for a specific task, organizing commits in a tree structure.

    Args:
        task_id: The ID of the task to query

    Returns:
        Tuple of:
        1. Dict of all commits indexed by commit_hash
        2. Dict of branch names mapping to their head commit hashes

        Example:
        (
            {
                "abc123": {
                    "commit_hash": "abc123",
                    "parent_hash": "def456",
                    "message": {...},
                    "vm_state": {...},
                    "committed_at": "2024-03-20T10:00:00",
                    "children": ["ghi789", "jkl012"]  # List of child commit hashes
                },
                ...
            },
            {
                "main": "abc123",
                "feature-branch": "ghi789"
            }
        )
    """

    commits_dict = {}  # hash -> commit data
    branch_heads = {}  # branch_name -> head_commit_hash

    with SessionLocal() as session:
        # First, get all commits for this task
        commits = (
            session.execute(select(Commit).where(Commit.task_id == task_id))
            .scalars()
            .all()
        )

        # Build the commit dictionary and establish parent-child relationships
        for commit in commits:
            commits_dict[commit.commit_hash] = {
                "commit_hash": commit.commit_hash,
                "parent_hash": commit.parent_hash,
                "message": commit.message,
                "vm_state": commit.vm_state,
                "committed_at": commit.committed_at.isoformat(),
                "children": [],  # Will be populated in next step
            }

        # Populate children lists
        for commit_hash, commit_data in commits_dict.items():
            parent_hash = commit_data["parent_hash"]
            if parent_hash and parent_hash in commits_dict:
                commits_dict[parent_hash]["children"].append(commit_hash)

        # Get all branches and their head commits
        branches = (
            session.execute(select(Branch).where(Branch.task_id == task_id))
            .scalars()
            .all()
        )

        for branch in branches:
            branch_heads[branch.name] = branch.head_commit_hash

    return commits_dict, branch_heads


@dataclass
class MCTSState:
    """Represents the state for a single step in the MCTS tree"""

    plan: List[Dict] = None
    seq_no: int = 0
    vm_state: Optional[Dict] = None
    commit_hash: Optional[str] = None
    final_answer: Optional[str] = None
    evaluation: Optional[Dict] = None


class MCTSNode:
    """Node in the MCTS tree"""

    def __init__(
        self,
        state: MCTSState,
        parent: Optional["MCTSNode"] = None,
        action: Optional[Dict] = None,
    ):
        self.state = state
        self.parent = parent
        self.action = action  # Action that led to this state
        self.children: List[MCTSNode] = []
        self.visits = 0
        self.value = 0.0
        self.untried_actions = self._get_valid_actions()

    def _get_valid_actions(self) -> List[Dict]:
        """Get list of valid actions from current state using LLM."""

        # TODO: Implement this, to choose what to do next
        pass

    def get_ucb_score(self, exploration_weight: float = 1.414) -> float:
        if self.visits == 0:
            return float("inf")  # Unvisited nodes have highest priority

        # Exploitation term: Average value of this node
        exploitation = self.value / self.visits

        # Exploration term: Uncertainty estimate
        # More parent visits or fewer node visits increase exploration priority
        exploration = exploration_weight * math.sqrt(
            math.log(self.parent.visits) / self.visits
        )

        return exploitation + exploration


class MCTSPlanOptimizer:
    """MCTS-based plan optimizer"""

    def __init__(
        self,
        task_id: str,
        max_iterations: int = 10,
        exploration_weight: float = 1.414,
        time_limit_seconds: int = 300,
    ):
        self.task_id = task_id
        self.max_iterations = max_iterations
        self.exploration_weight = exploration_weight
        self.time_limit_seconds = time_limit_seconds

        task_details = get_task(task_id)
        self.goal = task_details["goal"]
        self.metadata = task_details["metadata"]
        self.namespace = task_details["namespace"]

        # Build the full MCTS tree from commit history
        self._build_mcts_tree()

    def _build_mcts_tree(self) -> MCTSNode:
        """Build complete MCTS tree from commit history"""

        # Get commit tree data
        commits_dict, branches = get_task_commit_tree(self.task_id)

        # Find root commit (commit with no parent)
        root_commit_hash = next(
            hash for hash, data in commits_dict.items() if not data["parent_hash"]
        )

        # Create root node
        root_state = MCTSState(
            commit_hash=root_commit_hash,
            seq_no=-1,
        )
        self.root = MCTSNode(state=root_state)

        # Build tree recursively
        self._build_tree_recursive(self.root, root_commit_hash, commits_dict)

        # Build the branch reference
        self.branches = self._build_branch_index(branches)

        # Find and extend leaf nodes with remaining unexecuted steps
        # Start the extension process from the root
        self.find_and_extend_leaves(self.root)

    def _build_tree_recursive(
        self, parent_node: MCTSNode, commit_hash: str, commits_dict: Dict[str, Dict]
    ):
        """Recursively build MCTS tree from commit history"""
        # Get all child commits
        commit_data = commits_dict[commit_hash]
        child_hashes = commit_data["children"]

        # Create nodes for each child commit
        for child_hash in child_hashes:
            child_commit = commits_dict[child_hash]

            # Create child state
            child_state = MCTSState(
                commit_hash=child_hash,
                seq_no=child_commit["vm_state"].get("program_counter", 0) - 1,
                vm_state=child_commit["vm_state"],
                plan=child_commit["vm_state"].get("current_plan", []),
                final_answer=child_commit["vm_state"]
                .get("variables", {})
                .get("final_answer", None),
            )

            # Create child node
            child_node = MCTSNode(state=child_state, parent=parent_node)

            # Add to parent's children
            parent_node.children.append(child_node)

            if child_state.final_answer is not None:
                print(f"Final answer found for {child_hash}, evaluating...")
                # calculate the reward and backpropagate
                reward = self.evaluate_state(child_state)
                self.backpropagate(child_node, reward)
                continue

            # Recursively build tree for this child
            self._build_tree_recursive(child_node, child_hash, commits_dict)

    def _build_branch_index(self, branches: Dict[str, str]) -> Dict[str, str]:
        """Build branch index from commit history

        Args:
            branches: Dict mapping branch names to their head commit hashes

        Returns:
            Dict mapping commit hashes to their branch names
        """
        commit_hash_to_branch = {}
        for branch_name, commit_hash in branches.items():
            commit_hash_to_branch[commit_hash] = branch_name

        branches_ref = {}

        # Traverse the entire tree to map commits to branches
        def traverse(node: MCTSNode):
            if node.state.commit_hash in commit_hash_to_branch:
                branches_ref[node.state.commit_hash] = commit_hash_to_branch[
                    node.state.commit_hash
                ]
            for child in node.children:
                traverse(child)

        traverse(self.root)
        return branches_ref

    def find_and_extend_leaves(self, node: MCTSNode):
        if not node.children:  # This is a real leaf node
            current_plan = node.state.plan
            current_seq = node.state.seq_no

            # Check if there are remaining unexecuted steps
            remaining_steps = []
            for step in current_plan:
                if step.get("seq_no") > current_seq:
                    remaining_steps.append(step)

            # Create new nodes for each remaining step
            current_node = node
            for step in remaining_steps:
                new_state = MCTSState(
                    plan=current_plan,
                    seq_no=step.get("seq_no"),
                )
                new_node = MCTSNode(state=new_state, parent=current_node)
                current_node.children.append(new_node)
                current_node = new_node
        else:
            # If not a leaf, recursively check all children
            for child in node.children:
                self.find_and_extend_leaves(child)

    def select_node(self) -> MCTSNode:
        """Select a node for expansion using UCB1"""
        node = self.root
        while node.untried_actions == [] and node.children != []:
            node = max(
                node.children, key=lambda n: n.get_ucb_score(self.exploration_weight)
            )
        return node

    def expand_node(self, node: MCTSNode) -> Optional[MCTSNode]:
        """Expand selected node with a new child"""
        if not node.untried_actions:
            return None

        # Select random untried action
        action = random.choice(node.untried_actions)
        node.untried_actions.remove(action)

        # Create new state by applying action
        new_state = self._apply_action(node.state, action)
        if new_state is None:
            return None

        # Create new node
        child_node = MCTSNode(state=new_state, parent=node, action=action)
        node.children.append(child_node)
        return child_node

    def _apply_action(self, state: MCTSState, action: Dict) -> Optional[MCTSState]:
        """Apply action to state to generate new state"""
        # TODO: Implement this, to choose what to do next
        pass

    def evaluate_state(self, state: MCTSState) -> float:
        """Evaluate the quality of a state using the existing evaluation mechanism"""
        try:
            eval_response = evaulate_task_answer(
                self.goal, self.metadata, state.final_answer, json.dumps(state.plan)
            )
            response_json_str = extract_json(eval_response)
            state.evaluation = json.loads(response_json_str)

            # Convert evaluation result to a numerical score
            base_score = 1.0 if state.evaluation.get("accept", False) else 0.0

            # TODO: Add bonus for other quality assessment

            return base_score
        except Exception as e:
            print(f"Error evaluating state: {e}")
            return 0.0

    def simulate(self, node: MCTSNode) -> float:
        """Simulate from node to get a reward"""
        # For now, directly evaluate the state
        return self.evaluate_state(node.state)

    def backpropagate(self, node: MCTSNode, reward: float):
        """Backpropagate reward through tree.

        Updates visit counts and accumulated values for all nodes
        from the given node up to the root.

        Args:
            node: The node to start backpropagation from
            reward: The reward value from simulation (0.0 to 1.3)
                    - 1.0: Basic success (answer accepted)
                    - +0.2: Comprehensive answer
                    - +0.1: Well-structured answer
        """
        while node is not None:
            node.visits += 1  # Increment visit count
            node.value += reward  # Accumulate reward value
            node = node.parent  # Move up to parent

    def optimize(self) -> Tuple[List[Dict], float]:
        """Run MCTS optimization"""
        start_time = datetime.now()

        for _ in range(self.max_iterations):
            # Check time limit
            if (datetime.now() - start_time).total_seconds() > self.time_limit_seconds:
                break

            # Selection
            selected_node = self.select_node()

            # Expansion
            new_node = self.expand_node(selected_node)
            if new_node is None:
                continue

            # Simulation
            reward = self.simulate(new_node)

            # Backpropagation
            self.backpropagate(new_node, reward)

        # Return best plan found
        best_node = max(
            [n for n in self.root.children if n.visits > 0],
            key=lambda n: n.value / n.visits,
            default=self.root,
        )

        return best_node.state.plan, best_node.value / max(best_node.visits, 1)
