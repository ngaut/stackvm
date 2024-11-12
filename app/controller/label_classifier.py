import json
from typing import List, Dict
from app.services.prompts import get_label_classification_prompt
from app.services.llm_interface import LLMInterface
from app.models.label import Label
from app.database import SessionLocal
from sqlalchemy.exc import IntegrityError


def get_labels_tree() -> List[Dict]:
    """
    Retrieves and structures the labels into a hierarchical tree format.

    Returns:
        List[Dict]: A list representing the hierarchical labels tree.
    """
    with SessionLocal() as session:
        labels = session.query(Label).all()
        label_map = {label.id: {"name": label.name, "children": []} for label in labels}

        root_labels = []

        for label in labels:
            if label.parent_id:
                parent = label_map.get(label.parent_id)
                if parent:
                    parent["children"].append(label_map[label.id])
            else:
                root_labels.append(label_map[label.id])

    return root_labels

class LabelClassifier:
    """
    Service responsible for generating and validating label paths based on task goals.
    """

    def __init__(self):
        self.llm_interface = LLMInterface()

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
        label_path = self.parse_llm_response(response)

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
                label = session.query(Label).filter_by(name=label_name, parent_id=parent_id).first()
                if not label:
                    # Create new label
                    new_label = Label(name=label_name, parent_id=parent_id)
                    session.add(new_label)
                    try:
                        session.commit()
                        parent_id = new_label.id
                    except IntegrityError:
                        session.rollback()
                        raise ValueError(f"Failed to create or retrieve label '{label_name}'.")
                else:
                    parent_id = label.id

    def parse_llm_response(self, response: str) -> List[str]:
        """
        Parses the LLM response to extract the label path.

        Args:
            response (str): The response string from the LLM.

        Returns:
            List[str]: A list of label names.
        """
        try:
            # Attempt to parse the response as JSON
            label_path = json.loads(response)
            if isinstance(label_path, list):
                return label_path
            else:
                raise ValueError("LLM response is not a list.")
        except json.JSONDecodeError:
            # Fallback: Parse each line as a label
            lines = response.strip().split("\n")
            label_path = [line.strip() for line in lines if line.strip()]
            return label_path
