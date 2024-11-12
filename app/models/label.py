from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
import uuid

class Label(Base):
    __tablename__ = "labels"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    name = Column(String(255), nullable=False, unique=True)
    parent_id = Column(String(36), ForeignKey("labels.id"), nullable=True)

    parent = relationship("Label", remote_side=[id], backref="children")
    tasks = relationship("Task", secondary="task_labels", back_populates="labels")

    def __repr__(self):
        return f"<Label(name={self.name}, parent_id={self.parent_id})>"

    @property
    def is_leaf(self):
        """Determine if the label is a leaf node (no children)."""
        return len(self.children) == 0