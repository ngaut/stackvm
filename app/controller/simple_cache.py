import difflib
import re
import logging
import threading
import time
from types import MappingProxyType
import datetime

from app.database import SessionLocal
from app.models.task import Task

from apscheduler.schedulers.background import BackgroundScheduler

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
    _instance = None
    _instance_lock = threading.Lock()  # Lock for thread-safe singleton creation

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "_instance"):
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super(SimpleCache, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Avoid re-initialization in subsequent calls
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.cache_state = None  # Combined cache state
        self.lock = threading.Lock()  # Lock for updating the cache
        self.scheduler = BackgroundScheduler()

        # Schedule the cache to refresh every 24 hours, first run after 10 seconds
        next_run_time = datetime.datetime.now() + datetime.timedelta(seconds=10)
        self.scheduler.add_job(
            self.refresh_cache, "interval", hours=24, next_run_time=next_run_time
        )
        self.scheduler.start()
        logger.info("Started cache refresh scheduler to run every 24 hours.")

        self.refresh_cache()  # Initial cache population

        self._initialized = True  # Mark the instance as initialized

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_periodic_refresh()

    def get(self, goal, response_format):
        """
        Retrieves the best plan for a given goal using simple string matching.
        """
        normalized_goal = normalize_goal(goal)
        if normalized_goal is None:
            logger.warning("Attempted to get plan for a None goal.")
            return None

        # Access the cache without locking for read operations
        cache, goals_in_cache = self.cache_state if self.cache_state else ({}, [])

        closest_matches = difflib.get_close_matches(
            normalized_goal, goals_in_cache, cutoff=0.95
        )

        if not closest_matches:
            logger.info("No close matches found for goal: %s", normalized_goal)
            return None

        for matched_goal in closest_matches:
            candidate = cache.get(matched_goal)
            if candidate and candidate["response_format"]:
                goal_lang = (
                    response_format.get("Lang") or response_format.get("lang")
                    if response_format
                    else None
                )
                candidate_response = candidate.get("response_format")
                candidate_lang = (
                    candidate_response.get("Lang") or candidate_response.get("lang")
                    if candidate_response
                    else None
                )

                if goal_lang and candidate_lang and goal_lang == candidate_lang:
                    logger.info("Reusing the cache plan of goal %s", matched_goal)
                    return {"matched": True, "cached_goal": candidate}

        logger.info("No matching language found for goal: %s", normalized_goal)
        return {
            "matched": False,
            "reference_goal": (
                cache.get(closest_matches[0]) if closest_matches else None
            ),
        }

    def refresh_cache(self):
        """
        Refreshes the cache by reloading data from the database.
        """
        try:
            logger.info("Starting cache refresh...")
            with SessionLocal() as session:
                tasks = session.query(Task).filter(Task.best_plan.isnot(None)).all()
                candidates = [
                    {
                        "goal": task.goal,
                        "best_plan": task.best_plan,
                        "response_format": (
                            task.meta.get("response_format") if task.meta else None
                        ),
                    }
                    for task in tasks
                ]

            new_cache = {}
            new_goals_in_cache = []
            for item in candidates:
                clean_goal = normalize_goal(item["goal"])
                if clean_goal is None or clean_goal in new_goals_in_cache:
                    continue
                new_cache[clean_goal] = {
                    "goal": item["goal"],
                    "response_format": item["response_format"],
                    "best_plan": item["best_plan"],
                }
                new_goals_in_cache.append(clean_goal)

            # Convert to immutable structures
            immutable_cache = MappingProxyType(new_cache)
            immutable_goals_in_cache = tuple(new_goals_in_cache)
            immutable_cache_state = (immutable_cache, immutable_goals_in_cache)

            with self.lock:
                self.cache_state = immutable_cache_state
                logger.info("Cache refresh completed successfully.")
        except Exception as e:
            logger.exception("Failed to refresh cache.")

    def stop_periodic_refresh(self):
        """
        Stops the background scheduler.
        """
        if self.scheduler.state != 0:  # STATE_STOPPED
            self.scheduler.shutdown()
            logger.info("Stopped cache refresh scheduler.")


def initialize_cache() -> SimpleCache:
    """
    Initializes SimpleCache and starts the periodic refresh.
    """
    return SimpleCache()
