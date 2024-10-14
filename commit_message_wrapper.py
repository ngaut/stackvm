import json
from typing import Optional, Dict, Any
from utils import StepType
from utils import get_commit_message_schema

class CommitMessageWrapper:
    def __init__(self):
        self.commit_message: Optional[str] = None

    def set_commit_message(self, step_type: StepType, seq_no: str, description: str, input_parameters: Dict[str, Any], output_variables: Dict[str, Any]) -> None:
        commit_info = {
            "type": step_type.value,
            "seq_no": seq_no,
            "description": description,
            "input_parameters": input_parameters,
            "output_variables": output_variables
        }
        # Set the commit message using the commit_info dictionary
        self.commit_message = json.dumps(commit_info)

    def get_commit_message(self) -> Optional[str]:
        return self.commit_message

    def clear_commit_message(self) -> None:
        self.commit_message = None

commit_message_wrapper = CommitMessageWrapper()
