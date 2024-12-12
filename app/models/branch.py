from sqlalchemy import Column, String, DateTime, ForeignKey, BigInteger, JSON, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid

class Commit(Base):
    __tablename__ = "commits"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    commit_hash = Column(String(40), unique=True, nullable=False)
    parent_hash = Column(String(40), nullable=True)
    message = Column(JSON, nullable=False)
    vm_state = Column(JSON, nullable=False)
    committed_at = Column(DateTime, default=datetime.utcnow)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False)

    # Relationships
    task = relationship("Task", back_populates="commits")

    __table_args__ = (
        Index('idx_commit_hash', 'commit_hash'),
        Index('idx_commit_parent', 'parent_hash'),
        Index('idx_commit_task_time', 'task_id', 'committed_at'),
    )

    def __repr__(self):
        return f"<Commit(hash={self.commit_hash}, task_id={self.task_id})>"

class Branch(Base):
    __tablename__ = "branches"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False)
    head_commit_hash = Column(String(40), ForeignKey("commits.commit_hash"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    task = relationship("Task", back_populates="branches")
    head_commit = relationship("Commit", foreign_keys=[head_commit_hash])

    __table_args__ = (
        UniqueConstraint('name', 'task_id', name='uk_branch_name_task'),
        Index('idx_branch_task_id', 'task_id'),
        Index('idx_branch_name_task', 'name', 'task_id'),
    )

    def __repr__(self):
        return f"<Branch(name={self.name}, task_id={self.task_id})>"
