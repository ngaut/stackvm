import uuid
from sqlalchemy import Column, String, Text, Enum, DateTime
from datetime import datetime
from app.database import Base


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
    best_plan = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
