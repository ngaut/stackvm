from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
import uuid

"""
How to initialize the label table, take tidb bot as an example:

-- Insert Root Node
INSERT INTO `labels` (`id`, `name`, `parent_id`) VALUES
(UUID(), 'TiDB Bot Labels', NULL);

-- Get the ID of the Root Node
SET @root_id = (SELECT `id` FROM `labels` WHERE `name` = 'TiDB Bot Labels');

-- Insert Level 1 Labels with Root as Parent
INSERT INTO `labels` (`id`, `name`, `parent_id`) VALUES
(UUID(), 'Basic Knowledge', @root_id),
(UUID(), 'Operation Guide', @root_id),
(UUID(), 'Comparative Analysis', @root_id),
(UUID(), 'Troubleshooting', @root_id),
(UUID(), 'Complex Task Planning', @root_id),
(UUID(), 'Other Topics', @root_id);
"""

class Label(Base):
    __tablename__ = "labels"

    id = Column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True
    )
    name = Column(String(255), nullable=False, unique=True)
    parent_id = Column(String(36), ForeignKey("labels.id"), nullable=True)

    parent = relationship("Label", remote_side=[id], backref="children")

    def __repr__(self):
        return f"<Label(name={self.name}, parent_id={self.parent_id})>"

    @property
    def is_leaf(self):
        """Determine if the label is a leaf node (no children)."""
        return len(self.children) == 0
