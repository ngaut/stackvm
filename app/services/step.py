from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Tuple
from threading import Lock
import time
import logging
from concurrent.futures import Future


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    FAILED = "failed"
    SUCCESSFUL = "successful"


class Step(ABC):
    """Abstract base class for all execution steps."""

    def __init__(
        self, handler: callable, seq_no: str, step_type: str, parameters: Dict[str, Any]
    ):
        self.seq_no = seq_no
        self.step_type = step_type
        self.handler = handler
        self.parameters = parameters
        self.status = StepStatus.PENDING
        self.result: Optional[Any] = None
        self.error: Optional[str] = None
        self._lock = Lock()
        self._future: Optional[Future] = None
        self.logger = logging.getLogger(__name__)
        self.start_execution_time = None
        self.end_execution_time = None

    def run(self, **kwargs) -> None:
        """
        Start step execution. This method is non-blocking and changes the step status.
        """
        with self._lock:
            if self.status != StepStatus.PENDING:
                return
            self.status = StepStatus.RUNNING
            self.start_execution_time = datetime.utcnow()

        try:
            success, output = self.handler(self.parameters, **kwargs)
            with self._lock:
                if success:
                    self.status = StepStatus.SUCCESSFUL
                    self.result = output
                else:
                    self.status = StepStatus.FAILED
                    self.error = str(output)
                self.end_execution_time = datetime.utcnow()
        except Exception as e:
            with self._lock:
                self.status = StepStatus.FAILED
                self.error = str(e)
                self.end_execution_time = datetime.utcnow()
            self.logger.error(f"Error executing step {self.seq_no}: {str(e)}")

    def get_result(self) -> Tuple[bool, Any]:
        """
        Get the result of the step execution.
        Returns (success, result/error)
        """
        if self.status == StepStatus.SUCCESSFUL:
            return True, self.result
        elif self.status == StepStatus.FAILED:
            return False, self.error
        elif self.status == StepStatus.RUNNING:
            raise RuntimeError("Step is still running")
        else:
            raise RuntimeError("Step has not been started")

    def get_status(self) -> StepStatus:
        """Get the status of the step."""
        return self.status

    def set_future(self, future: Future) -> None:
        """Set the future object for this step when executed in thread pool."""
        self._future = future

    def get_future(self) -> Optional[Future]:
        """Get the future object if step is executed in thread pool."""
        return self._future

    def __str__(self) -> str:
        return f"Step(seq_no={self.seq_no}, type={self.step_type}, status={self.status.value})"
