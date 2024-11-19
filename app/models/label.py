from sqlalchemy import Column, String, ForeignKey, DateTime, Text
from datetime import datetime
from sqlalchemy.orm import relationship
from app.database import Base
import uuid

"""
How to initialize the label table, take tidb bot as an example:

-- Insert Level 1 Labels with Root as Parent
INSERT INTO `labels` (`id`, `name`, `description`, `created_at`, `updated_at`) VALUES
(UUID(), 'Basic Knowledge', 'Queries about simple facts or common knowledge regarding TiDB, such as configuration parameters and component design.', NOW(), NOW()),
(UUID(), 'Operation Guide', 'Looking for step-by-step instructions to perform specific operations in TiDB, such as setting up replication or configuring a feature.', NOW(), NOW()),
(UUID(), 'Comparative Analysis', 'Analysis comparing TiDB features, performance, or configurations with other database systems.', NOW(), NOW()),
(UUID(), 'Troubleshooting', 'Troubleshooting issues like error messages or unexpected behavior in TiDB, aiming to identify causes and solutions.', NOW(), NOW()),
(UUID(), 'Complex Task Planning', 'Planning and executing multi-step, complex goals related to TiDB, requiring comprehensive guidance or strategies.', NOW(), NOW()),
(UUID(), 'Other Topics', 'Discussing miscellaneous topics unrelated to TiDB, or general database-related queries.', NOW(), NOW());
"""


class Label(Base):
    __tablename__ = "labels"

    id = Column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    best_practices = Column(Text, nullable=True)
    parent_id = Column(String(36), ForeignKey("labels.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    parent = relationship("Label", remote_side=[id], backref="children")

    def __repr__(self):
        return f"<Label(name={self.name}, parent_id={self.parent_id})>"

    @property
    def is_leaf(self):
        """Determine if the label is a leaf node (no children)."""
        return len(self.children) == 0
