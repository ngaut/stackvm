from sqlalchemy import Column, String, JSON, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid


class Namespace(Base):
    __tablename__ = "namespaces"

    id = Column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name = Column(String(100), unique=True, index=True, nullable=False)
    allowed_tools = Column(JSON, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Namespace(name={self.name})>"
