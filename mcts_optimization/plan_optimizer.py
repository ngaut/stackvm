import sys
import os
import math
import json
import random
from typing import List, Dict, Optional, Tuple
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from notebooks.optimize_plan import (
    get_task_answer,
    update_plan,
    execute_task_using_new_plan,
    evaulate_task_answer,
)


@dataclass
class MCTSState:
    """Represents a state in the MCTS tree"""

    task_id: str
    branch_name: str
    commit_hash: str
    plan: List[Dict]
    goal: str
    metadata: Dict
    final_answer: Optional[str] = None
    evaluation_score: Optional[float] = None


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


def evaluate_state(state: MCTSState) -> float:
    """Evaluate the quality of a state using the existing evaluation mechanism"""
    try:
        eval_response = evaulate_task_answer(
            state.goal, state.metadata, state.final_answer, json.dumps(state.plan)
        )
        eval_result = json.loads(eval_response)

        # Convert evaluation result to a numerical score
        base_score = 1.0 if eval_result.get("accept", False) else 0.0

        # TODO: Add bonus for other quality assessment

        return base_score
    except Exception as e:
        print(f"Error evaluating state: {e}")
        return 0.0


class MCTSPlanOptimizer:
    """MCTS-based plan optimizer"""

    def __init__(
        self,
        task_id: str,
        branch_name: str = "main",
        max_iterations: int = 10,
        exploration_weight: float = 1.414,
        time_limit_seconds: int = 300,
    ):
        self.task_id = task_id
        self.branch_name = branch_name
        self.max_iterations = max_iterations
        self.exploration_weight = exploration_weight
        self.time_limit_seconds = time_limit_seconds

        # Initialize root state from current task
        initial_state = self._get_initial_state()
        self.root = MCTSNode(state=initial_state)

    def _get_initial_state(self) -> MCTSState:
        """Get initial state from current task"""
        task_detail = get_task_answer(self.task_id, self.branch_name)
        return MCTSState(
            task_id=self.task_id,
            branch_name=self.branch_name,
            commit_hash=task_detail.get("commit_hash", ""),
            plan=task_detail.get("plan", []),
            goal=task_detail.get("goal", ""),
            metadata=task_detail.get("metadata", {}),
            final_answer=task_detail.get("final_answer"),
        )

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

    def simulate(self, node: MCTSNode) -> float:
        """Simulate from node to get a reward"""
        # For now, directly evaluate the state
        return evaluate_state(node.state)

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
