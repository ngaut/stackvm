from typing import Optional
from utils import StepType
from utils import get_commit_message_schema

class CommitMessageWrapper:
    def __init__(self):
        self.commit_message: Optional[str] = None

    def set_commit_message(self, step_type: StepType, seq_no: str, description: str) -> None:
        self.commit_message = get_commit_message_schema(step_type.value, seq_no, description, {}, {})

    def get_commit_message(self) -> Optional[str]:
        return self.commit_message

    def clear_commit_message(self) -> None:
        self.commit_message = None

commit_message_wrapper = CommitMessageWrapper()