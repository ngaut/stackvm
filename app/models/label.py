from sqlalchemy import Column, String, ForeignKey, DateTime, Text
from datetime import datetime
from sqlalchemy.orm import relationship
from app.database import Base
import uuid

"""
-- Insert Level 1 Labels with Root as Parent
INSERT INTO `labels` (`id`, `namespace`, `name`, `description`, `created_at`, `updated_at`) VALUES
(UUID(), 'default', 'Basic Knowledge', 'Queries about simple facts or common knowledge, such as Concept Explanation, Feature Support, and component architectures.', NOW(), NOW()),
(UUID(), 'default', 'Operation Guide', 'Looking for step-by-step instructions to perform specific operations. Covers topics like deployment procedures, feature configuration, and maintenance tasks.', NOW(), NOW()),
(UUID(), 'default', 'Comparative Analysis', 'Detailed analysis and comparison of different designs, different version or the same features across different products. Includes evaluating trade-offs between various approaches and comparing implementation strategies.', NOW(), NOW()),
(UUID(), 'default', 'Troubleshooting', 'Diagnostic guidance and problem-solving approaches for system issues, error conditions, or unexpected behaviors. Focuses on root cause analysis and resolution strategies for common operational challenges.', NOW(), NOW()),
(UUID(), 'default', 'Complex Task Planning', 'Strategic planning and implementation guidance for sophisticated, multi-phase technical projects. Covers system design decisions and large-scale operational changes.', NOW(), NOW()),
(UUID(), 'default', 'Other Topics', 'General technical discussions and queries that don''t fit into the above categories.', NOW(), NOW());

-- Example for a different namespace (Plan Management)
INSERT INTO `labels` (`id`, `namespace`, `name`, `description`, `created_at`, `updated_at`) VALUES
(UUID(), 'plan_management', 'Plan Generation', 'Developing and designing comprehensive marketing plans to drive campaigns and achieve business objectives.', NOW(), NOW()),
(UUID(), 'plan_management', 'Plan Update', 'Revising and optimizing existing marketing plans to adapt to market changes and improve campaign effectiveness.', NOW(), NOW());
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
