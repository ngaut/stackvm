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


def get_labels_tree() -> List[Dict]:
    """
    Retrieves and structures the labels into a hierarchical tree format.

    Returns:
        List[Dict]: A list representing the hierarchical labels tree.
    """
    with SessionLocal() as session:
        labels = session.query(Label).all()
        label_map = {
            label.id: {
                "name": label.name,
                "description": label.description,
                "children": [],
            }
            for label in labels
        }

        root_labels = []

        for label in labels:
            if label.parent_id:
                parent = label_map.get(label.parent_id)
                if parent:
                    parent["children"].append(label_map[label.id])
            else:
                root_labels.append(label_map[label.id])

    return root_labels


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


def find_longest_matching_node(
    tree: List[Dict], path: List[Dict], current_depth: int = 0
) -> Dict:
    """
    Finds the longest matching node in the tree for the given path.
    """
    if current_depth >= len(path) or not tree:
        return None

    current_label = path[current_depth]

    # find the matching node at the root level
    matching_node = None
    for node in tree:
        if node["name"] == current_label["label"]:
            matching_node = copy.deepcopy(node)
            break

    if not matching_node:
        return None

    # if there are more levels in the path, search for the next level in the children
    if current_depth < len(path) - 1 and matching_node.get("children"):
        child_match = find_longest_matching_node(
            matching_node["children"], path, current_depth + 1
        )
        return child_match if child_match else matching_node

    return matching_node


def get_nearest_best_practices(label_path: List[Dict]) -> str:
    """
    Finds the nearest best practices along the label path.

    Args:
        label_path (List[str]): A list of label names from root to the given label.

    Returns:
        List[BestPractice]: A list of best practices associated with the nearest label.
    """
    with SessionLocal() as session:
        # Fetch all labels in the label_path with their best practices in a single query
        labels = (
            session.query(Label)
            .filter(Label.name.in_([label["label"] for label in label_path]))
            .all()
        )

        # Create a mapping from label name to label object
        label_map = {label.name: label for label in labels}

        # Iterate over label_path in reverse order to find the nearest label with best practices
        for label_name in reversed(label_path):
            label = label_map.get(label_name["label"])
            if label and label.best_practices:
                return label.best_practices

        # If no best practices found, return an empty list
        return None


def get_all_tasks_under_node(node: Dict) -> List[str]:
    """
    Recursively retrieves all tasks under the given node
    """
    tasks = []
    tasks.extend(node.get("tasks", []))

    # recursively get tasks from children
    for child in node.get("children", []):
        tasks.extend(get_all_tasks_under_node(child))

    return tasks


def find_most_similar_task(task: str, candidates: List[Dict]) -> Optional[str]:
    """
    Finds the most similar task in the list of candidates
    """

    candidate = candidates[0]
    for c in candidates:
        if c["goal"] == task:
            candidate = c
            break

    # find the task best plan
    with SessionLocal() as session:
        task = session.query(Task).filter(Task.id == candidate.get("id")).first()
        if not task or task.best_plan is None:
            return None

        return {
            "goal": task.goal,
            "best_plan": task.best_plan,
            "response_format": task.meta.get("response_format") if task.meta else None,
        }


def remove_label_id_from_tree(tree: List[Dict]):
    for label in tree:
        label.pop("id", None)
        label.pop("parent_id", None)
        if len(label["children"]) > 0:
            remove_label_id_from_tree(label["children"])
    return tree


def remove_task_id_from_tree(tree: List[Dict]):
    tree_json = json.dumps(tree, ensure_ascii=False)
    new_tree = json.loads(tree_json)

    def remove_task_id_recursive(node: Dict[str, Any]):
        if "tasks" in node:
            tasks = []
            for task in node["tasks"]:
                tasks.append(task["goal"])
            node["tasks"] = tasks
        if len(node["children"]) > 0:
            for child in node["children"]:
                remove_task_id_recursive(child)

    for label in new_tree:
        remove_task_id_recursive(label)

    return new_tree


def remove_task_from_tree(tree: List[Dict]):
    tree_json = json.dumps(tree, ensure_ascii=False)
    new_tree = json.loads(tree_json)

    def remove_task_recursive(node: Dict[str, Any]):
        node.pop("tasks", None)
        if len(node["children"]) > 0:
            for child in node["children"]:
                remove_task_recursive(child)

    for label in new_tree:
        remove_task_recursive(label)

    return new_tree


def extract_task_from_label_tree(tree: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
        node: Dict[str, Any], current_path: List[str]
    ) -> List[Dict[str, Any]]:
        results = []

        # Add current node's label name to the path
        path = current_path + [node["name"]]
        # Extract tasks from current node
        for task in node.get("tasks", []):
            results.append(
                {
                    "task_goal": task["goal"],
                    "labels": path.copy(),  # Create a copy of the path for each task
                }
            )

        # Recursively process children
        for child in node.get("children", []):
            results.extend(extract_tasks_recursive(child, path))

        return results

    # Process all root nodes
    all_tasks = []
    for root_node in tree:
        all_tasks.extend(extract_tasks_recursive(root_node, []))

    return all_tasks


def get_labels_tree_with_task_goals() -> List[Dict]:
    """
    Retrieves and structures the labels into a hierarchical tree format with task goals assigned
    to the respective leaf labels, using a single optimized SQL query.

    Returns:
        List[Dict]: A list representing the hierarchical labels tree with task goals.
    """
    with SessionLocal() as session:
        # Subquery to get up to 3 tasks per label using window function
        task_subquery = (
            session.query(
                Task.id.label("task_id"),
                Task.goal.label("task_goal"),
                Task.label_id.label("task_label_id"),
                func.row_number()
                .over(
                    partition_by=Task.label_id,
                    order_by=Task.updated_at.desc(),
                )
                .label("rn"),
            )
            .filter(Task.label_id.isnot(None))
            .subquery()
        )

        # Main query: join labels with the limited tasks
        labels_with_tasks = (
            session.query(
                Label.id.label("label_id"),
                Label.name.label("label_name"),
                Label.description.label("label_description"),
                Label.parent_id.label("label_parent_id"),
                task_subquery.c.task_id,
                task_subquery.c.task_goal,
            )
            .outerjoin(
                task_subquery,
                (Label.id == task_subquery.c.task_label_id) & (task_subquery.c.rn <= 2),
            )
            .order_by(Label.id)
            .all()
        )

    # Build a mapping from label ID to label details
    label_map = {}
    for row in labels_with_tasks:
        label_id = row.label_id
        if label_id not in label_map:
            label_map[label_id] = {
                "id": label_id,
                "name": row.label_name,
                "description": row.label_description,
                "parent_id": row.label_parent_id,
                "children": [],
                "tasks": [],
            }
        # Add task if present
        if row.task_id:
            label_map[label_id]["tasks"].append(
                {"id": row.task_id, "goal": row.task_goal}
            )

    # Build the hierarchical tree
    root_labels = []
    for label in label_map.values():
        parent_id = label_map[label["id"]].get("parent_id", None)
        if parent_id:
            parent = label_map.get(parent_id)
            if parent:
                parent["children"].append(label)
        else:
            root_labels.append(label)

    return remove_label_id_from_tree(root_labels)


def get_task_plans(task_ids: list) -> List[Dict]:
    """
    Retrieves all tasks with their best plans.
    """
    with SessionLocal() as session:
        # Subquery to get up to 3 tasks per label using window function

        results = (
            session.query(
                Task.id.label("task_id"),
                Task.goal.label("task_goal"),
                Task.best_plan.label("best_plan"),
            )
            .filter(Task.best_plan.isnot(None), Task.id.in_(task_ids))
            .all()
        )

    task_plans = {}
    for row in results:
        task_plans[row.task_id] = {
            "goal": row.task_goal,
            "best_plan": row.best_plan,
        }

    return task_plans


class LabelClassifier:
    """
    Service responsible for generating and validating label paths based on task goals.
    """

    def __init__(self):
        self.llm_interface = LLMInterface(LLM_PROVIDER, FAST_LLM_MODEL)

    def generate_label_path(
        self, task_goal: str
    ) -> Tuple[List[str], Optional[Dict], Optional[str]]:
        """
        Generates a label path for the given task goal.

        Args:
            task_goal (str): The goal of the task.

        Returns:
            List[str]: A list of label names from root to leaf.
        """
        # Generate enhanced classification prompt
        labels_tree_with_task = get_labels_tree_with_task_goals()
        tasks = extract_task_from_label_tree(labels_tree_with_task)

        prompt = get_label_classification_prompt_wo_description(
            task_goal, remove_task_id_from_tree(labels_tree_with_task), tasks
        )

        # Call LLM to get classification
        response = self.llm_interface.generate(prompt)

        # Parse the LLM response to extract label path
        label_path_str = extract_json(response)

        try:
            label_path = json.loads(label_path_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse label path JSON: {e}. Data {response}")

        if not label_path or not isinstance(label_path, list):
            raise ValueError(f"Invalid label path format. {label_path}")

        if len(label_path) > 0 and isinstance(label_path[-1], str):
            label_path = [{"name": item} for item in label_path]

        # find the most similar example in the label tree
        matching_node = find_longest_matching_node(labels_tree_with_task, label_path)
        if not matching_node:
            return label_path, None, None

        # get all tasks under the matching node
        tasks = get_all_tasks_under_node(matching_node)
        if len(tasks) == 0:
            return label_path, None, None

        best_practices = get_nearest_best_practices(label_path)

        return label_path, find_most_similar_task(task_goal, tasks), best_practices

    def generate_label_description(self, task_goal: str) -> List[str]:
        """
        Generates a label path for the given task goal.

        Args:
            task_goal (str): The goal of the task.

        Returns:
            List[str]: A list of label names from root to leaf.
        """
        # Generate enhanced classification prompt
        labels_tree_with_task = get_labels_tree_with_task_goals()

        prompt = get_label_classification_prompt(
            task_goal, remove_task_id_from_tree(labels_tree_with_task)
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

    def insert_label_path(self, task_id: str, label_path: List[Dict]) -> None:
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
                        .filter_by(name=label_name, parent=parent)
                        .first()
                    )

                    if not label:
                        # Create a new Label instance
                        label = Label(
                            id=str(uuid.uuid4()),
                            name=label_name,
                            parent=parent,
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
