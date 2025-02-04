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
from app.models.task import TaskORM
from app.controller.task import Task
from sqlalchemy import select
from app.config.settings import REASON_LLM_PROVIDER, REASON_FAST_LLM_MODEL
from app.services.llm_interface import LLMInterface

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from notebooks.optimize_plan import (
    get_task_answer,
    evaulate_task_answer,
)

llm_client = LLMInterface(REASON_LLM_PROVIDER, REASON_FAST_LLM_MODEL)


def get_task(task_id: str) -> Tuple[str, str, str]:
    """Get the task details"""
    with SessionLocal() as session:
        task = session.execute(
            select(TaskORM).where(TaskORM.id == task_id)
        ).scalar_one()
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


def get_branch_commits(
    task_id: str, from_commit_hash: str, branch_name: str
) -> Dict[str, Dict]:
    commits_dict = {}  # hash -> commit data

    with SessionLocal() as session:
        # First, get all commits for this task
        branch = (
            session.execute(
                select(Branch).where(
                    Branch.task_id == task_id, Branch.name == branch_name
                )
            )
            .scalars()
            .first()
        )

        latest_commit = branch.head_commit
        while latest_commit.commit_hash != from_commit_hash:
            commits_dict[latest_commit.commit_hash] = {
                "commit_hash": latest_commit.commit_hash,
                "parent_hash": latest_commit.parent_hash,
                "message": latest_commit.message,
                "vm_state": latest_commit.vm_state,
                "committed_at": latest_commit.committed_at.isoformat(),
                "children": [],
            }

        for commit_hash, commit_data in commits_dict.items():
            parent_hash = commit_data["parent_hash"]
            if parent_hash and parent_hash in commits_dict:
                commits_dict[parent_hash]["children"].append(commit_hash)

    return commits_dict


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
        self.untried_optimization_suggestions = self._get_optimization_suggestions()

    def _get_optimization_suggestions(self) -> List[Dict]:
        """Get list of valid actions from current state using LLM."""

        # TODO: Implement this, to choose what to optimize next
        return []

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

    def reflect_on_final_answer(
        self, goal: str, final_answer: str, metadata: Dict
    ) -> Dict:
        """Reflect on the current step and suggest optimizations for remaining steps.

        Args:
            goal: The original task goal
            final_answer: The final answer produced by the plan
            metadata: Additional task metadata

        Returns:
            Dict containing:
            {
                "should_optimize": bool,  # Whether optimization is possible
                "suggestion": str,     # Optimization suggestion explanation
            }
        """
        current_step_index = self.state.seq_no
        if current_step_index < 0 or not self.state.plan:
            return {
                "should_optimize": False,
                "suggestion": "No current step to analyze",
            }

        # Prepare the reflection prompt
        prompt = f"""
        Goal: {goal} 

        The supplementary information for Goal:
        {metadata.get('response_format')}

        Final Answer: {final_answer}
        
        Current Step ({current_step_index}):
        {json.dumps(self.state.plan[current_step_index], indent=2)}
        
        Remaining Steps:
        {json.dumps(self.state.plan[current_step_index + 1:], indent=2)}

        Based on the current step's execution and the final answer:
        1. Can the remaining steps be optimized to improve the final answer? Answer with yes or no.
        2. If yes, explain how to optimize the remaining steps.

        Format your response as JSON:
        {{
            "should_optimize": boolean,
            "suggestion": "string",
        }}
        """

        try:
            # Get reflection from LLM
            reflection_response = llm_client.generate(prompt)
            reflection = json.loads(extract_json(reflection_response))

            if reflection.get("should_optimize", False):
                reflection["suggestion"] = (
                    reflection.get("suggestion", "")
                    + f"\nPlease keep all steps up to and including the step ({current_step_index}) unchanged."
                )
                self.untried_optimization_suggestions.append(reflection)

            return reflection
        except Exception as e:
            print(f"Error during reflection: {e}")
            return {
                "can_optimize": False,
                "suggestion": f"Error during reflection: {str(e)}",
            }


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

            need_backprop, reward = self.simulate(child_node)
            if need_backprop:
                self.backpropagate(child_node, reward)

            # Recursively build tree for this child
            self._build_tree_recursive(child_node, child_hash, commits_dict)

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
        """Select a node for expansion using UCB1."""
        node = self.root

        while node.children:
            if node.untried_optimization_suggestions:
                return node

            # Otherwise, select best child using UCB
            node = max(
                node.children, key=lambda n: n.get_ucb_score(self.exploration_weight)
            )

        # If we reach here, we're at a leaf node with no untried actions
        # Let's analyze the execution path and get optimization suggestions
        if node.untried_optimization_suggestions:
            return node

        return None

    def expand_node(self, node: MCTSNode) -> Optional[MCTSNode]:
        """Expand selected node with a new child"""
        if not node.untried_optimization_suggestions:
            return None

        # Select random untried action
        reflection = random.choice(node.untried_optimization_suggestions)
        node.untried_optimization_suggestions.remove(reflection)

        # Create new state by applying action
        new_state = self._apply_reflection(node, reflection)
        if new_state is None:
            return None

        # Create new node
        child_node = MCTSNode(state=new_state, parent=node)
        return child_node

    def _apply_reflection(self, node: MCTSNode, reflection: Dict) -> Optional[MCTSNode]:
        """Apply an optimization suggestion to create a new state."""

        current_commit_hash = node.state.commit_hash
        branch_name = f"mcts_optimized_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        with SessionLocal() as session:
            taskORM = session.execute(
                select(TaskORM).where(TaskORM.id == self.task_id)
            ).scalar_one()
            task = Task(taskORM, llm_client)

        res = task.update(
            new_branch_name=branch_name,
            commit_hash=current_commit_hash,
            suggestion=reflection["suggestion"],
        )

        if res.get("success", False) is False:
            return None

        current_branch = res.get("current_branch")
        # find the node from current_commit_hash to the current branch
        commits_dict = get_branch_commits(
            self.task_id, current_commit_hash, current_branch
        )

        # Find root commit (commit with no parent)
        root_commit_hash = next(
            hash for hash, data in commits_dict.items() if not data["parent_hash"]
        )
        commits_dict[root_commit_hash]["parent_hash"] = current_commit_hash
        commits_dict[current_commit_hash] = {"children": [root_commit_hash]}

        # Build tree recursively
        self._build_tree_recursive(node, root_commit_hash, commits_dict)

        return None

    def evaluate_state(self, node: MCTSNode) -> Tuple[bool, float]:
        """Evaluate the quality of a state using the existing evaluation mechanism

        Returns:
            Tuple of (need_backprop, reward)
            - need_backprop: Whether to backpropagate the reward
            - reward: The reward value from simulation (0.0 to 1.0)
        """
        try:

            if node.state.final_answer is None:
                eval_response = evaulate_task_answer(
                    self.goal,
                    self.metadata,
                    node.state.final_answer,
                    json.dumps(node.state.plan),
                )
                response_json_str = extract_json(eval_response)
                node.state.evaluation = json.loads(response_json_str)

                # Convert evaluation result to a numerical score
                base_score = 1.0 if node.state.evaluation.get("accept", False) else 0.0

                # TODO: Add bonus for other quality assessment

                return True, base_score
        except Exception as e:
            print(f"Error evaluating state: {e}")

        return False, 0

    def simulate(self, node: MCTSNode) -> Tuple[bool, float]:
        """Simulate from node to get a reward"""
        # For now, directly evaluate the state
        return self.evaluate_state(node)

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
        if node.state.final_answer is None:
            return

        final_answer = node.state.final_answer

        while node is not None:
            node.visits += 1  # Increment visit count
            node.value += reward  # Accumulate reward value
            node.reflect_on_final_answer(self.goal, final_answer, self.metadata)
            node = node.parent  # Move up to parent

    def optimize(self) -> List[MCTSNode]:
        """Run MCTS optimization"""
        start_time = datetime.now()

        for _ in range(self.max_iterations):
            # Check time limit
            if (datetime.now() - start_time).total_seconds() > self.time_limit_seconds:
                break

            # Selection
            selected_node = self.select_node()
            if selected_node is None:
                print("No expandable nodes found in tree")
                break  # Or implement some tree reset/regeneration logic

            # Expansion
            new_node = self.expand_node(selected_node)
            if new_node is None:
                continue

            # Simulation
            """
            need_backprop, reward = self.simulate(new_node)
            if need_backprop:
                # Backpropagation
                self.backpropagate(new_node, reward)
            """

        def get_leaf_nodes(node: MCTSNode) -> List[MCTSNode]:
            if not node.children:
                return [node]

            leaves = []
            for child in node.children:
                leaves.extend(get_leaf_nodes(child))
            return leaves

        # Get all leaf nodes
        leaf_nodes = get_leaf_nodes(self.root)

        # Filter visited leaf nodes and sort by score
        scored_leaves = sorted(
            [node for node in leaf_nodes if node.visits > 0],
            key=lambda node: node.value / node.visits,
            reverse=True,
        )

        return scored_leaves
