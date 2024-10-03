from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional  # Add Optional to the import
import datetime

@dataclass
class Milestone:
    name: str
    variables: Dict[str, Any]
    program_counter: int
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    description: Optional[str] = None
    status: str = "active"  # e.g., active, completed, failed
    dependencies: List[str] = field(default_factory=list)  # Names of dependent milestones