import sys
import os
import math
import json
import random
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from app.utils.json import extract_json
from app.database import SessionLocal
from app.models.branch import Branch, Commit
from app.models.task import Task as TaskORM
from app.controller.task import Task
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from app.config.settings import REASON_LLM_PROVIDER, REASON_FAST_LLM_MODEL
from app.services.llm_interface import LLMInterface
from app.services.utils import parse_commit_message

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from notebooks.optimize_plan import evaulate_task_answer

logger = logging.getLogger(__name__)

llm_client = LLMInterface(REASON_LLM_PROVIDER, REASON_FAST_LLM_MODEL)


def get_branch(task_id: str, head_commit_hash: str) -> str:
    with SessionLocal() as session:
        branch = session.execute(
            select(Branch).where(
                Branch.task_id == task_id, Branch.head_commit_hash == head_commit_hash
            )
        ).scalar_one()
        return branch.name


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


def get_task_commit_tree(task_id: str) -> Dict[str, Dict]:
    """Query all commits and branches for a specific task, organizing commits in a tree structure.

    Args:
        task_id: The ID of the task to query

    Returns: Dict of all commits indexed by commit_hash

    Example:
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
    }
    """

    commits_dict = {}  # hash -> commit data

    with SessionLocal() as session:
        # First, get all commits for this task
        commits = (
            session.execute(select(Commit).where(Commit.task_id == task_id))
            .scalars()
            .all()
        )

        # Build the commit dictionary and establish parent-child relationships
        for commit in commits:
            seq_no, title, details, commit_type = parse_commit_message(commit.message)
            commits_dict[commit.commit_hash] = {
                "commit_hash": commit.commit_hash,
                "parent_hash": commit.parent_hash,
                "vm_state": commit.vm_state,
                "committed_at": commit.committed_at.isoformat(),
                "children": [],  # Will be populated in next step
                "seq_no": seq_no,
                "title": title,
                "details": details,
                "commit_type": commit_type,
            }

        # Populate children lists
        for commit_hash, commit_data in commits_dict.items():
            parent_hash = commit_data["parent_hash"]
            if parent_hash and parent_hash in commits_dict:
                commits_dict[parent_hash]["children"].append(commit_hash)

    return commits_dict


def get_branch_commits(
    task_id: str, from_commit_hash: str, branch_name: str
) -> Dict[str, Dict]:
    commits_dict = get_task_commit_tree(task_id)
    branch_commits = {}

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

        current_commit = branch.head_commit
        current_commit_hash = current_commit.commit_hash

        while current_commit_hash != from_commit_hash:
            branch_commits[current_commit_hash] = commits_dict[current_commit_hash]
            current_commit_hash = commits_dict[current_commit_hash]["parent_hash"]

    return branch_commits


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
    ):
        self.state = state
        self.parent = parent
        self.children: List[MCTSNode] = []
        self.visits = 0
        self.value = 0.0
        self.optimization_suggestions = []

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
        self, goal: str, final_answer: str, metadata: Dict, branch_name: str
    ) -> Dict:
        """Reflect on the current step and suggest optimizations for remaining steps.

        Args:
            goal: The original task goal
            final_answer: The final answer produced by the plan
            metadata: Additional task metadata

        Returns:
            {
                "should_optimize": bool,  # Whether optimization is possible
                "suggestion": str,     # Optimization suggestion explanation
            }
        """
        current_step_no = self.state.seq_no
        if current_step_no < 0 or not self.state.plan:
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
        
        Current Step ({current_step_no}):
        {json.dumps(self.state.plan[current_step_no], indent=2)}

        Current Execution State:
        {json.dumps(self.state.vm_state, indent=2)}

        Remaining Steps:
        {json.dumps(self.state.plan[current_step_no + 1:], indent=2)}

        Analyze the current execution and final answer:
        1. Could the remaining steps be improved to generate a better final answer? Answer with yes or no.
        2. If yes, suggest specific improvements focusing on:
           - Adding new steps that could provide additional relevant information
           - Modifying existing steps to gather more comprehensive or accurate data
           - Enhancing the reasoning process using llm_generate to produce a more complete or accurate answer

        Note: Focus on improving answer quality rather than execution efficiency.

        Format your response as JSON:
        ```json
        {{
            "should_optimize": boolean,
            "suggestion": "string",
        }}
        ```
        """

        try:
            # Get reflection from LLM
            response = llm_client.generate(prompt)
            response_json_str = extract_json(response)
            reflection = json.loads(response_json_str)

            if reflection.get("should_optimize", False):
                reflection["suggestion"] = (
                    reflection.get("suggestion", "")
                    + f"\nPlease keep all steps up to and including the step ({current_step_no}) unchanged."
                )
                reflection["branch_name"] = branch_name
                self.optimization_suggestions.append(reflection)

            logger.info(
                "reflect on final answer: %s for %s(%s)",
                reflection,
                branch_name,
                self.state.commit_hash,
            )
            return reflection
        except Exception as e:
            logger.error("Error during reflection: %s", e)
            return {
                "should_optimize": False,
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
        commits_dict = get_task_commit_tree(self.task_id)

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
        # enable it later
        # self.find_and_extend_leaves(self.root)

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

            if child_commit["commit_type"] == "StepExecution":
                # Create child state
                child_state = MCTSState(
                    commit_hash=child_hash,
                    seq_no=child_commit["seq_no"],
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
                logger.info(
                    "add child node: %s(%s) ---> %s(%s)",
                    parent_node.state.commit_hash,
                    parent_node.state.seq_no,
                    child_node.state.commit_hash,
                    child_node.state.seq_no,
                )

                need_backprop, reward = self.simulate(child_node)
                if need_backprop:
                    self.backpropagate(child_node, reward)

                # Recursively build tree for this child
                self._build_tree_recursive(child_node, child_hash, commits_dict)
            else:
                self._build_tree_recursive(parent_node, child_hash, commits_dict)

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
        all_nodes = []

        def collect_nodes(node: MCTSNode):
            if node.optimization_suggestions:
                all_nodes.append(node)
            for child in node.children:
                collect_nodes(child)

        # Collect all nodes starting from root
        collect_nodes(self.root)

        if not all_nodes:
            return None

        # Return node with highest UCB score
        selected_node = max(
            all_nodes, key=lambda n: n.get_ucb_score(self.exploration_weight)
        )

        if not selected_node.optimization_suggestions:
            return None

        logger.info(
            "selected node: %s(%s)",
            selected_node.state.commit_hash,
            selected_node.state.seq_no,
        )
        return selected_node

    def expand_node(self, node: MCTSNode) -> Optional[MCTSNode]:
        """Expand selected node with a new child"""
        if not node.optimization_suggestions:
            return None

        # Select random untried action
        reflection = random.choice(node.optimization_suggestions)
        node.optimization_suggestions.remove(reflection)

        # Create new state by applying action
        self._apply_reflection(node, reflection)

    def _apply_reflection(self, node: MCTSNode, reflection: Dict):
        """Apply an optimization suggestion to create a new state."""

        current_commit_hash = node.state.commit_hash
        branch_name = f"mcts_optimized_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        with SessionLocal() as session:
            taskORM = session.execute(
                select(TaskORM)
                .options(joinedload(TaskORM.namespace))
                .where(TaskORM.id == self.task_id)
            ).scalar_one()
            task = Task(taskORM, llm_client)

        res = task.update(
            new_branch_name=branch_name,
            commit_hash=current_commit_hash,
            suggestion=reflection["suggestion"],
            source_branch=reflection["branch_name"],
        )

        logger.info(
            "task update result: %s for %s(%s)", res, branch_name, current_commit_hash
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
            hash
            for hash, data in commits_dict.items()
            if data["parent_hash"] == current_commit_hash
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

            if node.state.final_answer is not None:
                eval_response = evaulate_task_answer(
                    self.goal,
                    self.metadata,
                    node.state.final_answer,
                    json.dumps(node.state.plan),
                )
                logger.info(
                    "evaluate answer: %s(%s) response: %s",
                    node.state.commit_hash,
                    node.state.seq_no,
                    eval_response,
                )
                response_json_str = extract_json(eval_response)
                node.state.evaluation = json.loads(response_json_str)

                # Convert evaluation result to a numerical score
                base_score = 1.0 if node.state.evaluation.get("accept", False) else 0.0

                # TODO: Add bonus for other quality assessment

                return True, base_score
            elif not node.children:
                return True, 0
        except Exception as e:
            logger.error("Error evaluating state: %s", e)

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

        logger.info("backpropagate: %s(%s)", node.state.commit_hash, node.state.seq_no)

        final_answer = node.state.final_answer
        branch_name = get_branch(self.task_id, node.state.commit_hash)

        while node is not None:
            node.visits += 1  # Increment visit count
            node.value += reward  # Accumulate reward value
            node.reflect_on_final_answer(
                self.goal, final_answer, self.metadata, branch_name
            )
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
                logger.info("No expandable nodes found in tree")
                break  # Or implement some tree reset/regeneration logic

            # Expansion
            self.expand_node(selected_node)

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
