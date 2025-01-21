import uuid
from enum import Enum as PyEnum
from sqlalchemy import (
    Column,
    String,
    Text,
    Enum,
    DateTime,
    JSON,
    ForeignKey,
    Boolean,
    ForeignKeyConstraint,
    Index,
)
from datetime import datetime
from app.database import Base
from sqlalchemy.orm import relationship
from sqlalchemy import Enum as SQLAlchemyEnum
from .label import Label


# Define Python Enums for task status and evaluation status
class TaskStatus(PyEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    deleted = "deleted"


class EvaluationStatus(PyEnum):
    NOT_EVALUATED = "NOT_EVALUATED"
    WAITINT_FOR_EVALUATION = "WAITTING_FOR_EVALUATION"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True
    )
    goal = Column(Text, nullable=False)
    status = Column(
        SQLAlchemyEnum(TaskStatus, name="task_status"),
        default=TaskStatus.pending,
        server_default="pending",
    )
    repo_path = Column(String(255), nullable=False)
    logs = Column(Text, nullable=True)
    tenant_id = Column(String(36), nullable=True)
    project_id = Column(String(36), nullable=True)
    best_plan = Column(JSON, nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    evaluation_status = Column(
        SQLAlchemyEnum(EvaluationStatus, name="evaluation_status"),
        default=EvaluationStatus.NOT_EVALUATED,
        server_default="NOT_EVALUATED",
        comment="The evaluation status of the task by the LLM.",
    )
    evaluation_reason = Column(
        Text, nullable=True, comment="Reason for rejection if the task is not approved."
    )
    human_evaluation_status = Column(
        SQLAlchemyEnum(EvaluationStatus, name="human_evaluation_status"),
        default=EvaluationStatus.NOT_EVALUATED,
        server_default="NOT_EVALUATED",
        comment="The evaluation status of the task by the Human.",
    )
    human_feedback = Column(
        Text, nullable=True, comment="Reason for rejection if the task is not approved."
    )

    label_id = Column(String(36), nullable=True)
    namespace_name = Column(String(100), index=True, nullable=True)

    # Relationships
    label = relationship("Label")
    namespace = relationship("Namespace")
    commits = relationship("Commit", back_populates="task", cascade="all, delete-orphan")
    branches = relationship("Branch", back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        ForeignKeyConstraint(
            ["label_id"], ["labels.id"],
            name="fk_task_label"
        ),
        ForeignKeyConstraint(
            ["namespace_name"], ["namespaces.name"],
            name="fk_task_namespace"
        ),
        Index("idx_task_label", "label_id"),
        Index("idx_task_namespace", "namespace_name")
    )

    def __repr__(self):
        return f"<Task(goal={self.goal}, status={self.status})>"

    @property
    def has_best_plan(self):
        """Check if the task has a best_plan."""
        return self.best_plan is not None
