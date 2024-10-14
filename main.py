import os
import logging
from flask import Flask
import argparse
from datetime import datetime

from app.controller.api_routes import api_blueprint
from app.controller.engine import run_vm_with_goal
from app.config.settings import GIT_REPO_PATH


# Initialize Flask app
app = Flask(__name__)
app.register_blueprint(api_blueprint)

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

# Setup logging
setup_logging(app)


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
        repo_path = os.path.join(GIT_REPO_PATH, datetime.now().strftime("%Y%m%d%H%M%S"))
        run_vm_with_goal(args.goal, repo_path)
        logging.info("VM execution completed")
    elif args.server:
        logging.info("Starting visualization server...")
        app.run(debug=True, port=args.port)
    else:
        logging.info(
            "Please specify --goal to run the VM with a goal or --server to start the visualization server"
        )