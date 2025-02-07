from sqlalchemy import (
    Column,
    String,
    DateTime,
    BigInteger,
    JSON,
    UniqueConstraint,
    Index,
    ForeignKeyConstraint,
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.config.database import Base


class Commit(Base):
    __tablename__ = "commits"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    commit_hash = Column(String(40), unique=True, nullable=False)
    parent_hash = Column(String(40), nullable=True)
    message = Column(JSON, nullable=False)
    vm_state = Column(JSON, nullable=False)
    committed_at = Column(DateTime, default=datetime.utcnow)
    task_id = Column(String(36), nullable=False)

    # Relationships
    task = relationship("Task", back_populates="commits")

    __table_args__ = (
        Index("idx_commit_hash", "commit_hash"),
        Index("idx_commit_parent", "parent_hash"),
        Index("idx_commit_task_time", "task_id", "committed_at"),
        ForeignKeyConstraint(["task_id"], ["tasks.id"], name="fk_commit_task"),
    )

    def __repr__(self):
        return f"<Commit(hash={self.commit_hash}, task_id={self.task_id})>"


class Branch(Base):
    __tablename__ = "branches"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    task_id = Column(String(36), nullable=False)
    head_commit_hash = Column(String(40), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    task = relationship("Task", back_populates="branches")
    head_commit = relationship("Commit", foreign_keys=[head_commit_hash])

    __table_args__ = (
        UniqueConstraint("name", "task_id", name="uk_branch_name_task"),
        ForeignKeyConstraint(["task_id"], ["tasks.id"], name="fk_branch_task"),
        ForeignKeyConstraint(
            ["head_commit_hash"], ["commits.commit_hash"], name="fk_branch_commit"
        ),
    )

    def __repr__(self):
        return f"<Branch(name={self.name}, task_id={self.task_id})>"
