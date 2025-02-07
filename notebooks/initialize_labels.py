import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

import uuid
from datetime import datetime

from app.database import SessionLocal
from app.storage.models import Namespace, Label

# Create a new session
session = SessionLocal()

# Create Namespaces
problem_resolving = Namespace(
    id=str(uuid.uuid4()),
    name="Default",
    description="Default Namespace for the best practices applicable to general scenarios",
    created_at=datetime.utcnow(),
    updated_at=datetime.utcnow(),
)

# Add namespaces to the session
session.add(problem_resolving)

# Create Labels
labels = [
    Label(
        id=str(uuid.uuid4()),
        namespace_name="Default",
        name="Basic Knowledge",
        description="Queries about simple facts or common knowledge, such as Concept Explanation, Feature Support, and component architectures.",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    ),
    Label(
        id=str(uuid.uuid4()),
        namespace_name="Default",
        name="Operation Guide",
        description="Looking for step-by-step instructions to perform specific operations. Covers topics like deployment procedures, feature configuration, and maintenance tasks.",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    ),
    Label(
        id=str(uuid.uuid4()),
        namespace_name="Default",
        name="Troubleshooting",
        description="Diagnostic guidance and problem-solving approaches for system issues, error conditions, or unexpected behaviors. Focuses on root cause analysis and resolution strategies for common operational challenges",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    ),
    Label(
        id=str(uuid.uuid4()),
        namespace_name="Default",
        name="Complex Task Planning",
        description="Strategic planning and implementation guidance for sophisticated, multi-phase technical projects. Covers system design decisions and large-scale operational changes.",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    ),
    Label(
        id=str(uuid.uuid4()),
        namespace_name="Default",
        name="Other Topics",
        description="General technical discussions and queries that don"
        "t fit into the above categories.",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    ),
]

# Add labels to the session
session.add_all(labels)
session.commit()

# Close the session
session.close()
