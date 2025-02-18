import logging
from datetime import datetime, timedelta
from typing import Optional, List
import requests

from app.config.database import SessionLocal
from app.core.task.manager import TaskService
from app.storage.models import Task, EvaluationStatus

ts = TaskService()


def get_evaluation_pending_tasks(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    statuses: Optional[List[str]] = None,
):
    if not end_time:
        end_time = datetime.utcnow()

    if not start_time:
        start_time = end_time - timedelta(days=2)

    evaluation_statuses = [EvaluationStatus.NOT_EVALUATED]

    if statuses:
        # Split by comma in case of multiple statuses
        stautus_strs = [status.strip() for status in statuses]
        evaluation_statuses = []
        for status_str in stautus_strs:
            try:
                evaluation_status = EvaluationStatus(status_str.upper())
                evaluation_statuses.append(evaluation_status)
            except ValueError:
                valid_statuses = [status.value for status in EvaluationStatus]
                raise ValueError(
                    f"Invalid 'evaluation_status' value: '{status_str}'. "
                    f"Must be one of {valid_statuses}.",
                )

    with SessionLocal() as session:
        tasks_orm = ts.list_tasks_evaluation(
            session, start_time, end_time, evaluation_statuses
        )

        return [
            {
                "id": task.id,
                "goal": task.goal,
                "status": task.status.value,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "logs": task.logs,
                "best_plan": task.best_plan,
                "metadata": task.meta,
                "evaluation_status": task.evaluation_status.value,
                "human_evaluation_status": task.human_evaluation_status.value,
            }
            for task in tasks_orm
        ]


def record_evaluation(
    task_id: str,
    evaluation_status: str,
    evaluation_reason: Optional[str] = "",
):
    with SessionLocal() as session:
        try:
            task = session.query(Task).filter(Task.id == task_id).first()
            if not task:
                raise ValueError(f"Task with ID {task_id} not found.")

            task.evaluation_status = evaluation_status.upper()
            task.evaluation_reason = evaluation_reason
            session.commit()
        except Exception as e:
            logging.error(f"Failed to record evaluation for task {task_id}: {e}")
            session.rollback()
            return False

    return True


def record_human_evaluation(
    task_id: str, evaluation_status: str, feedback: Optional[str] = ""
):
    with SessionLocal() as session:
        try:
            task = session.query(Task).filter(Task.id == task_id).first()
            if not task:
                raise ValueError(f"Task with ID {task_id} not found.")

            task.human_evaluation_status = evaluation_status.upper()
            task.human_feedback = feedback
            session.commit()
        except Exception as e:
            logging.error(f"Failed to record human evaluation for task {task_id}: {e}")
            session.rollback()
            return False

        return True


def save_best_plan_from_url(
    task_id: Optional[str] = None,
    commit_hash: Optional[str] = None,
    url: Optional[str] = None,
):
    try:
        if task_id is None and commit_hash is None and url is None:
            raise ValueError("Either task_id, commit_hash, or url must be provided")

        if url is not None:
            # Split URL by '/' and extract components
            parts = url.split("/")

            # Find index of 'tasks' and extract task_id and commit_hash
            if "tasks" in parts:
                tasks_index = parts.index("tasks")
                if (
                    len(parts) < tasks_index + 4
                ):  # Ensure we have enough parts after 'tasks'
                    raise ValueError("Invalid URL format")

                task_id = parts[tasks_index + 1]
                commit_hash = parts[tasks_index + 3]

        url = f"https://stackvm.tidb.ai/api/tasks/{task_id}/commits/{commit_hash}/save_best_plan"
        response = requests.post(url)
        if response.status_code != 200:
            raise ValueError("Failed to save best plan")

    except Exception as e:
        print(e)
        return False

    return True
