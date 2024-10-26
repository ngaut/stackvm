from sqlalchemy import Column, Integer, String, Text, Enum, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Task(Base):
    __tablename__ = 'tasks'
    
    id = Column(Integer, primary_key=True, index=True)
    goal = Column(Text, nullable=False)
    status = Column(Enum('pending', 'in_progress', 'completed', 'failed', name='task_status'), default='pending')
    repo_path = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    branches = relationship("Branch", back_populates="task", cascade="all, delete-orphan")
