import difflib
import re
import logging

from app.database import SessionLocal
from app.models.task import Task

logger = logging.getLogger(__name__)


def normalize_goal(goal):
    if goal is None:
        return None

    # Trim whitespace and remove all trailing punctuation
    # Remove trailing punctuation (one or more of '.', ',', '!', '?')
    goal = re.sub(r"[.,!?]+$", "", goal.strip())

    # Convert to lowercase
    return goal.lower()


class SimpleCache:
    def __init__(self, items: list = []):
        self.cache = {}
        self.goals_in_cache = []
        for item in items:
            self.add(item["goal"], item["response_format"], item["best_plan"])

    def add(self, goal, response_format, best_plan):
        """
        Adds goal and its plan to the cache.
        """
        clean_goal = normalize_goal(goal)
        if goal is None or goal in self.goals_in_cache:
            return
        self.cache[clean_goal] = {
            "goal": goal,
            "response_format": response_format,
            "best_plan": best_plan,
        }
        self.goals_in_cache.append(clean_goal)

    def get(self, goal, response_format):
        """
        Retrieves the best plan for a given goal using simple string matching.
        """
        goal = normalize_goal(goal)
        if goal is None:
            return None

        closest_matches = difflib.get_close_matches(
            goal, self.goals_in_cache, cutoff=0.95
        )

        if not closest_matches:
            return None

        for goal in closest_matches:
            candidate = self.cache[goal]
            candidate_response_format = candidate["response_format"]
            if candidate_response_format:
                goal_lang = response_format.get("Lang") or response_format.get("lang")
                candidate_lang = candidate_response_format.get(
                    "Lang"
                ) or candidate_response_format.get("lang")

                if goal_lang and candidate_lang and candidate_lang == goal_lang:
                    logger.info("Reusing the cache plan of goal %s", goal)
                    return {"matched": True, "cached_goal": candidate}

        return {
            "matched": False,
            "reference_goal": (
                self.cache[closest_matches[0]] if len(closest_matches) > 0 else None
            ),
        }


def initialize_cache() -> SimpleCache:
    with SessionLocal() as session:
        tasks = session.query(Task).filter(Task.best_plan.isnot(None)).all()
        candidates = []
        for task in tasks:
            candidates.append(
                {
                    "goal": task.goal,
                    "best_plan": task.best_plan,
                    "response_format": (
                        task.meta.get("response_format") if task.meta else None
                    ),
                }
            )

        return SimpleCache(candidates)
