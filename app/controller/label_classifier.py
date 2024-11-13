import json
from typing import List, Dict
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session
from collections import defaultdict
import uuid

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

def get_label_path(session: Session, label: Label) -> List[str]:
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


class LabelClassifier:
    """
    Service responsible for generating and validating label paths based on task goals.
    """

    def __init__(self):
        self.llm_interface = LLMInterface(LLM_PROVIDER, LLM_MODEL)

    def generate_label_path(self, task_id: str, task_goal: str) -> List[str]:
        """
        Generates a label path for the given task goal.

        Args:
            task_goal (str): The goal of the task.

        Returns:
            List[str]: A list of label names from root to leaf.
        """
        # Generate enhanced classification prompt
        labels_tree = self.get_labels_tree_with_task_goals()
        prompt = get_label_classification_prompt(task_goal, labels_tree)

        # Call LLM to get classification
        response = self.llm_interface.generate(prompt)

        # Parse the LLM response to extract label path
        label_path_str = extract_json(response)

        try:
            label_path = json.loads(label_path_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse label path JSON: {e}")

        return label_path

    def insert_label_path(self, task_id: str, label_path: List[str]) -> None:
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
                for label_name in label_path:
                    # Query if the label exists with the current parent_id
                    label = (
                        session.query(Label)
                        .filter_by(name=label_name, parent=parent)
                        .first()
                    )

                    if not label:
                        # Create a new Label instance
                        label = Label(
                            id=str(uuid.uuid4()), name=label_name, parent=parent
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

    def get_labels_tree_with_task_goals(self) -> List[Dict]:
        """
        Queries tasks with corresponding labels and assigns task goals to the respective leaf labels.

        Returns:
            List[Dict]: A list representing the hierarchical labels tree with task goals assigned to leaf labels.
        """
        labels_tree = get_labels_tree()

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
                .filter(Task.label_id != None)
                .subquery()
            )

            limited_tasks = (
                session.query(task_subquery.c.goal, task_subquery.c.label_id)
                .filter(task_subquery.c.rn <= 3)
                .limit(50)
                .all()
            )

            label_to_tasks = defaultdict(list)
            for goal, label_id in limited_tasks:
                label_to_tasks[label_id].append(goal)

        def insert_goals(tree: List[Dict]):
            for label in tree:
                label_id = label.get("id")
                if label_id and label_id in label_to_tasks:
                    label["tasks"] = label_to_tasks[label_id]
                if label.get("children"):
                    insert_goals(label["children"])

        insert_goals(labels_tree)

        return remove_label_id_from_tree(labels_tree)
