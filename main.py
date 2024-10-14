import os
import logging
from flask import Flask
import argparse
from datetime import datetime

from app.config.settings import GIT_REPO_PATH
from app.controller import llm_interface, git_manager
from app.controller.plan import generate_plan
from app.controller.api import register_routes
from app.services import PlanExecutionVM
from app.utils import commit_vm_changes

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

# Initialize Flask app
print(os.getcwd())
app = Flask(__name__)

# Setup logging
setup_logging(app)

# Register routes
register_routes(app, git_manager, llm_interface)


def run_vm_with_goal(goal, repo_path):
    vm = PlanExecutionVM(repo_path, llm_interface)
    vm.set_goal(goal)

    plan = generate_plan(goal, llm_interface)
    if plan:
        logging.info("Generated Plan:")
        vm.state["current_plan"] = plan

        while True:
            success = vm.step()
            commit_vm_changes(vm, git_manager)
            if not success:
                break

            if vm.state.get("goal_completed"):
                logging.info("Goal completed during plan execution.")
                break

        if vm.state.get("goal_completed"):
            final_answer = vm.get_variable("final_answer")
            if final_answer:
                logging.info(f"\nfinal_answer: {final_answer}")
            else:
                logging.info("\nNo result was generated.")
        else:
            logging.warning("Plan execution failed or did not complete.")
            logging.error(vm.state.get("errors"))
    else:
        logging.error("Failed to generate plan.")

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