from sqlalchemy import (
    Column,
    String,
    ForeignKey,
    DateTime,
    Text,
    ForeignKeyConstraint,
    Index,
)
from datetime import datetime
from sqlalchemy.orm import relationship
from app.database import Base
import uuid


class Label(Base):
    __tablename__ = "labels"

    id = Column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True
    )
    namespace_name = Column(String(100), nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    best_practices = Column(Text, nullable=True)
    parent_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    namespace = relationship("Namespace")
    parent = relationship("Label", remote_side=[id], backref="children")

    __table_args__ = (
        ForeignKeyConstraint(
            ["namespace_name"], ["namespaces.name"], name="fk_label_namespace"
        ),
        ForeignKeyConstraint(["parent_id"], ["labels.id"], name="fk_label_parent"),
    )

    def __repr__(self):
        return f"<Label(namespace={self.namespace.name}, name={self.name}, parent_id={self.parent_id})>"

    @property
    def is_leaf(self):
        """Determine if the label is a leaf node (no children)."""
        return len(self.children) == 0
