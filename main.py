import os
import logging
from flask import Flask, url_for
import argparse
from datetime import datetime
from typing import Optional

from app.controller.api_routes import api_blueprint, main_blueprint
from app.config.settings import (
    GIT_REPO_PATH,
    GENERATED_FILES_DIR,
    LLM_PROVIDER,
    LLM_MODEL,
)
from app.services import LLMInterface
from app.controller.task import TaskService
from app.instructions import global_tools_hub, tool
from app.database import SessionLocal

# Initialize Flask app
app = Flask(__name__)
app.register_blueprint(api_blueprint)
app.register_blueprint(main_blueprint)


# Setup logging
def setup_logging(app):
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    )
    app.logger.setLevel(logging.INFO)
    for handler in app.logger.handlers:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
            )
        )


setup_logging(app)
logger = logging.getLogger(__name__)


# Register the tool after its definition
global_tools_hub.load_tools("tools")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the VM with a specified goal or start the visualization server."
    )
    parser.add_argument("--goal", help="Set a goal for the VM to achieve")
    parser.add_argument(
        "--server", action="store_true", help="Start the visualization server"
    )
    parser.add_argument(
        "--port", type=int, default=5000, help="Port to run the visualization server on"
    )

    args = parser.parse_args()

    if args.goal:
        ts = TaskService()
        with SessionLocal() as session: 
            task = ts.create_task(session, args.goal, datetime.now().strftime("%Y%m%d%H%M%S"))
        task.execute()
        logger.info("VM execution completed")
    elif args.server:
        logger.info("Starting visualization server...")
        app.run(debug=True, port=args.port)
    else:
        logger.info(
            "Please specify --goal to run the VM with a goal or --server to start the visualization server"
        )
