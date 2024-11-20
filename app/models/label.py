from sqlalchemy import Column, String, ForeignKey, DateTime, Text
from datetime import datetime
from sqlalchemy.orm import relationship
from app.database import Base
import uuid

"""
-- Insert Level 1 Labels with Root as Parent
INSERT INTO `labels` (`id`, `name`, `description`, `created_at`, `updated_at`) VALUES
(UUID(), 'Basic Knowledge', 'Queries about simple facts or common knowledge, such as Concept Explanation, Feature Support, and component architectures.', NOW(), NOW()),
(UUID(), 'Operation Guide', 'Looking for step-by-step instructions to perform specific operations. Covers topics like deployment procedures, feature configuration, and maintenance tasks.', NOW(), NOW()),
(UUID(), 'Comparative Analysis', 'Detailed analysis and comparison of different designs, different version or the same features across different products. Includes evaluating trade-offs between various approaches and comparing implementation strategies.', NOW(), NOW()),
(UUID(), 'Troubleshooting', 'Diagnostic guidance and problem-solving approaches for system issues, error conditions, or unexpected behaviors. Focuses on root cause analysis and resolution strategies for common operational challenges.', NOW(), NOW()),
(UUID(), 'Complex Task Planning', 'Strategic planning and implementation guidance for sophisticated, multi-phase technical projects. Covers system design decisions and large-scale operational changes.', NOW(), NOW()),
(UUID(), 'Other Topics', 'General technical discussions and queries that don''t fit into the above categories.', NOW(), NOW());
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
