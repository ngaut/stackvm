import json
from typing import List, Dict
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session
from collections import defaultdict

from app.services.prompts import get_label_classification_prompt
from app.services.llm_interface import LLMInterface
from app.models.label import Label
from app.database import SessionLocal
from app.config.settings import LLM_PROVIDER, LLM_MODEL
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
            label.id: {"id": label.id, "name": label.name, "children": []}
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


def remove_label_id_from_tree(tree: List[Dict]):
    for label in tree:
        label.pop("id", None)
        if len(label["children"]) > 0:
            remove_label_id_from_tree(label["children"])
    return tree


class LabelClassifier:
    """
    Service responsible for generating and validating label paths based on task goals.
    """

    def __init__(self):
        self.llm_interface = LLMInterface(LLM_PROVIDER, LLM_MODEL)

    def generate_label_path(self, task_goal: str) -> List[str]:
        """
        Generates a label path for the given task goal.

        Args:
            task_goal (str): The goal of the task.

        Returns:
            List[str]: A list of label names from root to leaf.
        """
        # Generate enhanced classification prompt
        labels_tree = get_labels_tree()
        prompt = get_label_classification_prompt(task_goal, labels_tree)

        # Call LLM to get classification
        response = self.llm_interface.generate(prompt)

        # Parse the LLM response to extract label path
        label_path = extract_json(response)

        print("prompt:\n", prompt)
        print("response:\n", response)

        return label_path

        # Validate and create the label path
        self.validate_and_create_label_path(label_path)
        return label_path

    def validate_and_create_label_path(self, label_path: List[str]) -> None:
        """
        Validates the label path and creates any missing labels.

        Args:
            label_path (List[str]): The label path to validate and create.
        """
        with SessionLocal() as session:
            parent_id = None
            for label_name in label_path:
                label = (
                    session.query(Label)
                    .filter_by(name=label_name, parent_id=parent_id)
                    .first()
                )
                if not label:
                    # Create new label
                    new_label = Label(name=label_name, parent_id=parent_id)
                    session.add(new_label)
                    try:
                        session.commit()
                        parent_id = new_label.id
                    except IntegrityError:
                        session.rollback()
                        raise ValueError(
                            f"Failed to create or retrieve label '{label_name}'."
                        )
                else:
                    parent_id = label.id

    def assign_task_goals_to_leaf_labels(self) -> List[Dict]:
        """
        Queries tasks with corresponding labels and assigns task goals to the respective leaf labels.

        Returns:
            List[Dict]: A list representing the hierarchical labels tree with task goals assigned to leaf labels.
        """
        labels_tree = get_labels_tree()
        leaf_labels = self._get_leaf_labels(labels_tree)
        label_ids = [label["id"] for label in leaf_labels]

        with SessionLocal() as session:
            task_subquery = (
                session.query(
                    Task.goal,
                    Task.label_id,
                    func.row_number()
                    .over(
                        partition_by=Task.label_id,
                        order_by=Task.id,
                    )
                    .label("rn"),
                )
                .filter(Task.label_id.in_(label_ids))
                .subquery()
            )

            limited_tasks = (
                session.query(task_subquery.c.goal, task_subquery.c.label_id)
                .filter(task_subquery.c.rn <= 3)
                .limit(50)
                .all()
            )

            label_to_goals = defaultdict(list)
            for goal, label_id in limited_tasks:
                label_to_goals[label_id].append(goal)

            for label in leaf_labels:
                label["task_goals"] = label_to_goals.get(label["id"], [])

        return remove_label_id_from_tree(labels_tree)

    def _get_leaf_labels(self, labels: List[Dict]) -> List[Dict]:
        """
        Recursively retrieves all leaf labels from the labels tree.

        Args:
            labels (List[Dict]): The hierarchical labels tree.

        Returns:
            List[Dict]: A list of leaf labels.
        """
        leaf_labels = []
        for label in labels:
            if not label["children"]:
                leaf_labels.append(label)
            else:
                leaf_labels.extend(self._get_leaf_labels(label["children"]))
        return leaf_labels
