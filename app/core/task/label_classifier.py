import json
import logging
import copy
from typing import List, Dict, Tuple, Optional, Any
from sqlalchemy.exc import IntegrityError
import uuid

from app.llm.prompts import (
    get_label_classification_prompt,
    get_label_classification_prompt_wo_description,
)
from app.llm.interface import LLMInterface
from app.storage.models import Label, Task
from app.database import SessionLocal
from app.config.settings import LLM_PROVIDER, LLM_MODEL
from app.utils import extract_json

logger = logging.getLogger(__name__)


def get_label_path(label: Label) -> List[str]:
    """
    Retrieves the label path from the given label up to the root label.

    Args:
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
        self.label_map: Dict[str, Dict] = {}
        self.tree: Dict[str, List] = {}
        self.build_label_map()
        self.construct_tree()
        self.fill_tasks()
        self.light_trees = self._construct_light_tree()
        self.task_lists = self._construct_task_list()

    def build_label_map(self) -> None:
        """
        Constructs the label_map from the database.
        """
        with SessionLocal() as session:
            labels = session.query(Label).all()
            self.label_map = {
                label.id: {
                    "id": label.id,
                    "label": label.name,
                    "description": label.description,
                    "best_practices": label.best_practices,
                    "parent_id": label.parent_id,
                    "namespace_name": label.namespace_name,
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
                namespace_name = label.get("namespace_name")
                if namespace_name is None:
                    continue

                if self.tree.get(namespace_name, None) is None:
                    self.tree[namespace_name] = []
                self.tree[namespace_name].append(label)

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
        self, namespace_name: str, path: List[Dict]
    ) -> Optional[Dict]:
        """
        Finds the longest matching node in the tree for the given path.

        Args:
            path (List[Dict]): A list of dictionaries with label information.
            current_depth (int): The current depth in the path.

        Returns:
            Optional[Dict]: The matching node or None if no match is found.
        """

        if self.tree.get(namespace_name, None) is None:
            return None

        def _find_longest_matching_label_recursive(root_labels, path, depth):
            if depth >= len(path) or not root_labels:
                return None

            current_label = path[depth]["label"]

            # Find the matching node at the current tree level
            matching_node = None
            for node in root_labels:
                if node["label"] == current_label:
                    matching_node = copy.deepcopy(node)
                    break

            if not matching_node:
                return None

            # If there are more levels in the path, search within the children
            if depth < len(path) - 1 and matching_node.get("children"):
                child_match = _find_longest_matching_label_recursive(
                    matching_node["children"], path, depth + 1
                )
                return child_match if child_match else matching_node

            return matching_node

        return _find_longest_matching_label_recursive(
            self.tree.get(namespace_name), path, 0
        )

    def get_nearest_best_practices(
        self, namespace_name: str, label_path: List[Dict]
    ) -> Optional[str]:
        """
        Finds the nearest best practices along the label path.

        Args:
            label_path (List[Dict]): A list of label dictionaries from root to the given label.

        Returns:
            Optional[str]: The best practices string associated with the nearest label, or None.
        """
        # Iterate over label_path in reverse order to find the nearest label with best practices
        for label_dict in reversed(label_path):
            label_name = label_dict["label"]
            # Find the label in label_map by name
            label = next(
                (
                    lbl
                    for lbl in self.label_map.values()
                    if lbl["label"] == label_name
                    and lbl["namespace_name"] == namespace_name
                ),
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

    def _construct_task_list(self) -> Dict[str, List[Dict[str, Any]]]:
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
            path = current_path + [label["label"]]
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
        all_tasks = {}
        for namespace_name, lt in self.tree.items():
            tasks_in_ns = []
            for root_node in lt:
                tasks_in_ns.extend(extract_tasks_recursive(root_node, []))
            all_tasks[namespace_name] = tasks_in_ns

        return all_tasks

    def _construct_light_tree(self) -> List[Dict[str, Any]]:
        """
        Generates a simplified version of the label tree.

        Returns:
            List[Dict[str, Any]]: A list representing the hierarchical labels tree in a clean format,
            where each label includes its name, description, list of task goals, and child labels.
        """

        def copy_tree_recursive(label: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "label": label.get("label", "Unnamed Label"),
                "description": label.get("description", ""),
                "tasks": [task.get("goal", "") for task in label.get("tasks", [])],
                "children": [
                    copy_tree_recursive(child) for child in label.get("children", [])
                ],
            }

        light_trees = {}
        for namespace_name, lt in self.tree.items():
            light_trees[namespace_name] = [
                copy_tree_recursive(root_label) for root_label in lt
            ]

        return light_trees

    def get_light_tree(self, namespace_name: str):
        return self.light_trees.get(namespace_name)

    def get_task_list(self, namespace_name: str):
        return self.task_lists.get(namespace_name)


class LabelClassifier:
    """
    Service responsible for generating and validating label paths based on task goals.
    """

    def __init__(self):
        self.llm_interface = LLMInterface(LLM_PROVIDER, LLM_MODEL)
        self.label_tree = LabelTree()

    def generate_label_path(
        self, namespace_name: str, task_goal: str
    ) -> Tuple[List[str], Optional[Dict], Optional[str]]:
        """
        Generates a label path for the given task goal.

        Args:
            task_goal (str): The goal of the task.

        Returns:
            List[str]: A list of label names from root to leaf.
        """
        logger.info(f"Using {LLM_MODEL} for label classification")
        # Generate enhanced classification prompt
        prompt = get_label_classification_prompt_wo_description(
            task_goal,
            self.label_tree.get_light_tree(namespace_name),
            self.label_tree.get_task_list(namespace_name),
        )

        # Call LLM to get classification
        response = self.llm_interface.generate(prompt)

        try:
            label_path_str = extract_json(response)
            label_path = json.loads(label_path_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse label path JSON: {e}. Data {response}")

        if not label_path or not isinstance(label_path, list):
            raise ValueError(f"Invalid label path format. {label_path}")

        if len(label_path) > 0 and isinstance(label_path[-1], str):
            label_path = [{"label": item} for item in label_path]

        # find the most similar example in the label tree
        matching_node = self.label_tree.find_longest_matching_label(
            namespace_name, label_path
        )
        if not matching_node:
            return label_path, None, None

        # get all tasks under the matching node
        tasks = self.label_tree.get_all_tasks_under_label(matching_node)
        if len(tasks) == 0:
            return label_path, None, None

        best_practices = self.label_tree.get_nearest_best_practices(
            namespace_name, label_path
        )

        return (
            label_path,
            self.label_tree.find_most_similar_task(task_goal, tasks),
            best_practices,
        )

    def generate_label_description(
        self, namespace_name: str, task_goal: str
    ) -> List[str]:
        """
        Generates a label path for the given task goal.

        Args:
            task_goal (str): The goal of the task.

        Returns:
            List[str]: A list of label names from root to leaf.
        """

        prompt = get_label_classification_prompt(
            task_goal, self.label_tree.get_light_tree(namespace_name)
        )

        # Call LLM to get classification
        response = self.llm_interface.generate(prompt)
        # Parse the LLM response to extract label path
        label_path_str = extract_json(response)

        try:
            label_path = json.loads(label_path_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse label path JSON: {e}")

        return label_path

    def insert_label_path(
        self, namespace_name: str, task_id: str, label_path: List[Dict]
    ) -> None:
        """
        Validates the label path and creates any missing labels using SQLAlchemy ORM.
        Finally, updates the task's label_id.

        Args:
            task_id (str): The ID of the task to update.
            label_path (List[str]): The label path to validate and create.
        """
        parent = None
        final_label = None

        with SessionLocal() as session:
            try:
                for current_label in label_path:
                    # Query if the label exists with the current parent_id
                    label_name = current_label.get("label", None)
                    label_description = current_label.get("description", None)
                    if not label_name or not label_description:
                        raise ValueError("Label name and description are required.")

                    label = (
                        session.query(Label)
                        .filter_by(
                            name=label_name,
                            parent=parent,
                            namespace_name=namespace_name,
                        )
                        .first()
                    )

                    if not label:
                        # Create a new Label instance
                        label = Label(
                            id=str(uuid.uuid4()),
                            name=label_name,
                            parent=parent,
                            namespace_name=namespace_name,
                            description=label_description,
                        )
                        session.add(label)
                        session.flush()  # Flush to assign an ID if needed

                    # Update the parent for the next label in the path
                    parent = label
                    final_label = label  # Keep track of the final label

                # Retrieve the task and update its label_id
                task = session.query(Task).filter_by(id=task_id).first()
                if not task:
                    raise ValueError(f"Task with id {task_id} does not exist.")

                task.label = final_label  # Assuming relationship is set up
                session.commit()

            except IntegrityError as e:
                session.rollback()
                raise ValueError(f"Failed to create or retrieve labels: {e}")
            except Exception as e:
                session.rollback()
                raise e
