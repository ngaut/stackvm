import json
import copy
from typing import List, Dict, Tuple, Optional, Any
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session
from collections import defaultdict
import uuid

from app.services.prompts import (
    get_label_classification_prompt,
    get_label_classification_prompt_wo_description,
)
from app.services.llm_interface import LLMInterface
from app.models.label import Label
from app.database import SessionLocal
from app.config.settings import LLM_PROVIDER, FAST_LLM_MODEL
from app.utils import extract_json
from app.models.task import Task


def get_label_path(label: Label) -> List[str]:
    """
    Retrieves the label path from the given label up to the root label.

    Args:
        session (Session): SQLAlchemy session.
        label (Label): The label for which to retrieve the path.

    Returns:
        List[str]: A list of label names from root to the given label.
    """
    path = []
    current_label = label
    while current_label:
        path.insert(0, current_label.name)
        current_label = current_label.parent
    return path


class LabelTree:
    """
    Manages and manipulates a hierarchical tree of labels and associated tasks.
    Provides functionalities to retrieve, modify, and query label data efficiently.
    """

    def __init__(self):
        """
        Initializes the LabelTree instance by setting up the label map and constructing the tree.
        """
        self.label_map: Dict[int, Dict] = {}
        self.tree: List[Dict] = []
        self.build_label_map()
        self.construct_tree()
        self.fill_tasks()

    def build_label_map(self) -> None:
        """
        Constructs the label_map from the database.
        """
        with SessionLocal() as session:
            labels = session.query(Label).all()
            self.label_map = {
                label.id: {
                    "id": label.id,
                    "name": label.name,
                    "description": label.description,
                    "best_practices": label.best_practices,
                    "parent_id": label.parent_id,
                    "children": [],
                    "tasks": [],
                }
                for label in labels
            }

    def construct_tree(self) -> None:
        """
        Builds the hierarchical tree structure using the label_map.
        """
        for label in self.label_map.values():
            parent_id = label.get("parent_id")
            if parent_id:
                parent = self.label_map.get(parent_id)
                if parent:
                    parent["children"].append(label)
            else:
                self.tree.append(label)

    def fill_tasks(self) -> None:
        with SessionLocal() as session:
            tasks = (
                session.query(Task)
                .filter(Task.best_plan.isnot(None), Task.label_id.isnot(None))
                .all()
            )

            for task in tasks:
                label = self.label_map.get(task.label_id)
                if label is None:
                    continue

                label["tasks"].append(
                    {
                        "id": task.id,
                        "goal": task.goal,
                        "best_plan": task.best_plan,
                        "response_format": (
                            task.meta.get("response_format") if task.meta else None
                        ),
                    }
                )

    def find_longest_matching_label(
        self, path: List[Dict], current_depth: int = 0
    ) -> Optional[Dict]:
        """
        Finds the longest matching node in the tree for the given path.

        Args:
            path (List[Dict]): A list of dictionaries with label information.
            current_depth (int): The current depth in the path.

        Returns:
            Optional[Dict]: The matching node or None if no match is found.
        """
        if current_depth >= len(path) or not self.tree:
            return None

        current_label = path[current_depth]["name"]

        # Find the matching node at the current tree level
        matching_node = None
        for node in self.tree:
            if node["name"] == current_label:
                matching_node = copy.deepcopy(node)
                break

        if not matching_node:
            return None

        # If there are more levels in the path, search within the children
        if current_depth < len(path) - 1 and matching_node.get("children"):
            child_match = self.find_longest_matching_label(
                matching_node["children"], path, current_depth + 1
            )
            return child_match if child_match else matching_node

        return matching_node

    def get_nearest_best_practices(self, label_path: List[Dict]) -> Optional[str]:
        """
        Finds the nearest best practices along the label path.

        Args:
            label_path (List[Dict]): A list of label dictionaries from root to the given label.

        Returns:
            Optional[str]: The best practices string associated with the nearest label, or None.
        """
        # Iterate over label_path in reverse order to find the nearest label with best practices
        for label_dict in reversed(label_path):
            label_name = label_dict["name"]
            # Find the label in label_map by name
            label = next(
                (lbl for lbl in self.label_map.values() if lbl["name"] == label_name),
                None,
            )
            if label and label["best_practices"]:
                return label["best_practices"]

        return None

    def get_all_tasks_under_label(self, label: Dict) -> List[str]:
        """
        Recursively retrieves all tasks under the given node
        """
        tasks = []
        tasks.extend(label.get("tasks", []))

        # recursively get tasks from children
        for child in label.get("children", []):
            tasks.extend(self.get_all_tasks_under_label(child))

        return tasks

    def find_most_similar_task(
        self, goal: str, candidates: List[Dict]
    ) -> Optional[str]:
        """
        Finds the most similar task in the list of candidates
        """

        candidate = candidates[0]
        for c in candidates:
            if c["goal"] == goal:
                candidate = c
                break

        return candidate

    def get_task_list(self) -> List[Dict[str, Any]]:
        """
        Extracts all tasks from the label tree, including the complete label path for each task.

        Args:
            tree (List[Dict]): A hierarchical tree structure of labels with tasks

        Returns:
            List[Dict]: A list of dictionaries containing task goals and their label paths
            Example:
            [
                {
                    "task_goal": "How to configure replication?",
                    "label_path": ["Operation Guide", "Replication", "Configuration"]
                }
            ]
        """

        def extract_tasks_recursive(
            label: Dict[str, Any], current_path: List[str]
        ) -> List[Dict[str, Any]]:
            results = []

            # Add current node's label name to the path
            path = current_path + [label["name"]]
            # Extract tasks from current node
            for task in label.get("tasks", []):
                results.append(
                    {
                        "task_goal": task["goal"],
                        "labels": path.copy(),  # Create a copy of the path for each task
                    }
                )

            # Recursively process children
            for child in label.get("children", []):
                results.extend(extract_tasks_recursive(child, path))

            return results

        # Process all root nodes
        all_tasks = []
        for root_node in self.tree:
            all_tasks.extend(extract_tasks_recursive(root_node, []))

        return all_tasks

    def get_light_tree(self) -> List[Dict[str, Any]]:
        """
        Generates a simplified version of the label tree.

        Returns:
            List[Dict[str, Any]]: A list representing the hierarchical labels tree in a clean format,
            where each label includes its name, description, list of task goals, and child labels.
        """

        def copy_tree_recursive(label: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "name": label.get("name", "Unnamed Label"),
                "description": label.get("description", ""),
                "tasks": [task.get("goal", "") for task in label.get("tasks", [])],
                "children": [
                    copy_tree_recursive(child) for child in label.get("children", [])
                ],
            }

        return [copy_tree_recursive(root_label) for root_label in self.tree]
