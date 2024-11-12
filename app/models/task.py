import uuid
from sqlalchemy import Column, String, Text, Enum, DateTime, JSON
from datetime import datetime
from app.database import Base
from sqlalchemy.orm import relationship
from .task_label import task_labels


class Task(Base):
    __tablename__ = "tasks"

    id = Column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True
    )
    goal = Column(Text, nullable=False)
    status = Column(
        Enum(
            "pending",
            "in_progress",
            "completed",
            "failed",
            "deleted",
            name="task_status",
        ),
        default="pending",
    )
    repo_path = Column(String(255), nullable=False)
    logs = Column(Text, nullable=True)
    tenant_id = Column(String(36), nullable=True)
    project_id = Column(String(36), nullable=True)
    best_plan = Column(JSON, nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    labels = relationship("Label", secondary=task_labels, back_populates="tasks")

    def __repr__(self):
        return f"<Task(goal={self.goal}, status={self.status})>"

    @property
    def has_best_plan(self):
        """Check if the task has a best_plan."""
        return self.best_plan is not None
