import logging
import json
from flask import Flask
import click
from datetime import datetime

from app.api.api_routes import api_blueprint, main_blueprint
from app.core.task.manager import TaskService
from app.instructions import global_tools_hub
from app.config.database import SessionLocal
from app.storage.models import Namespace

# Initialize Flask app
app = Flask(__name__)
app.register_blueprint(api_blueprint)
app.register_blueprint(main_blueprint)


# Initialize logger
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


def parse_json(value):
    """Parse JSON string to dict."""
    if value is None:
        return {}
    try:
        parsed_value = json.loads(value)
        if not isinstance(parsed_value, dict):
            raise click.BadParameter("Must be a JSON string representing a dictionary.")
        return parsed_value
    except json.JSONDecodeError:
        raise click.BadParameter("Must be a valid JSON string.")


# CLI Commands
@app.cli.group()
def stackvm():
    """CLI commands for the stackvm."""
    pass


@stackvm.command("execute")
@click.option("--goal", required=True, help="Set a goal for the VM to achieve")
@click.option(
    "--response-format",
    default="{}",
    help="Specify the response format for the task as a JSON string",
    callback=lambda ctx, param, value: parse_json(value),
)
@click.option(
    "--namespace-name",
    help="Specify the namespace name for the task",
    default=None,
)
def execute_task(goal, response_format, namespace_name):
    """Execute the VM with a specified goal."""
    ts = TaskService()
    with SessionLocal() as session:
        # Get namespace if specified
        namespace = None
        if namespace_name:
            namespace = session.query(Namespace).filter_by(name=namespace_name).first()
            if not namespace:
                logger.warning(
                    f"Namespace '{namespace_name}' not found. Using all tools."
                )

        task = ts.create_task(
            session,
            goal,
            datetime.now().strftime("%Y%m%d%H%M%S"),
            {"response_format": response_format},
            namespace_name,
        )
    task.execute()
    logger.info("VM execution completed")


# Namespace management commands
@app.cli.group()
def namespace():
    """Manage namespaces."""
    pass


@namespace.command("create")
@click.argument("name")
@click.option(
    "--allowed-tools",
    multiple=True,
    help="Allowed tools for the namespace. Can specify multiple times.",
)
@click.option("--description", help="Description of the namespace")
def create_namespace(name, allowed_tools, description):
    """Create a new namespace."""
    session = SessionLocal()
    try:
        existing = session.query(Namespace).filter_by(name=name).first()
        if existing:
            click.echo(f"Error: Namespace '{name}' already exists.")
            return

        namespace = Namespace(
            name=name,
            allowed_tools=list(allowed_tools) if allowed_tools else None,
            description=description,
        )
        session.add(namespace)
        session.commit()
        click.echo(f"Successfully created namespace '{name}'")
    except Exception as e:
        click.echo(f"Error creating namespace: {str(e)}")
    finally:
        session.close()


@namespace.command("delete")
@click.argument("name")
def delete_namespace(name):
    """Delete a namespace."""
    session = SessionLocal()
    try:
        namespace = session.query(Namespace).filter_by(name=name).first()
        if not namespace:
            click.echo(f"Error: Namespace '{name}' not found.")
            return

        session.delete(namespace)
        session.commit()
        click.echo(f"Successfully deleted namespace '{name}'")
    except Exception as e:
        click.echo(f"Error deleting namespace: {str(e)}")
    finally:
        session.close()


@namespace.command("update")
@click.argument("name")
@click.option(
    "--allowed-tools",
    multiple=True,
    help="New allowed tools for the namespace. Can specify multiple times.",
)
@click.option("--description", help="New description of the namespace")
def update_namespace(name, allowed_tools, description):
    """Update a namespace."""
    session = SessionLocal()
    try:
        namespace = session.query(Namespace).filter_by(name=name).first()
        if not namespace:
            click.echo(f"Error: Namespace '{name}' not found.")
            return

        if allowed_tools:
            namespace.allowed_tools = list(allowed_tools)
        if description is not None:
            namespace.description = description

        session.commit()
        click.echo(f"Successfully updated namespace '{name}'")
    except Exception as e:
        click.echo(f"Error updating namespace: {str(e)}")
    finally:
        session.close()


@namespace.command("list")
def list_namespaces():
    """List all namespaces."""
    session = SessionLocal()
    try:
        namespaces = session.query(Namespace).all()
        if not namespaces:
            click.echo("No namespaces found.")
            return

        for ns in namespaces:
            click.echo(f"\nNamespace: {ns.name}")
            click.echo(f"Description: {ns.description or 'N/A'}")
            click.echo(
                f"Allowed Tools: {', '.join(ns.allowed_tools) if ns.allowed_tools else 'All'}"
            )
    except Exception as e:
        click.echo(f"Error listing namespaces: {str(e)}")
    finally:
        session.close()


@namespace.command("show")
@click.argument("name")
def show_namespace(name):
    """Show details of a specific namespace."""
    session = SessionLocal()
    try:
        namespace = session.query(Namespace).filter_by(name=name).first()
        if not namespace:
            click.echo(f"Error: Namespace '{name}' not found.")
            return

        click.echo(f"\nNamespace: {namespace.name}")
        click.echo(f"Description: {namespace.description or 'N/A'}")
        click.echo(
            f"Allowed Tools: {', '.join(namespace.allowed_tools) if namespace.allowed_tools else 'All'}"
        )
        click.echo(f"Created At: {namespace.created_at}")
        click.echo(f"Updated At: {namespace.updated_at}")
    except Exception as e:
        click.echo(f"Error showing namespace: {str(e)}")
    finally:
        session.close()
