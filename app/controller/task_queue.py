import asyncio
import inspect
from datetime import datetime, timedelta
from queue import Queue
from threading import Thread
import uuid
from typing import Callable, Any
import logging
import traceback

from app.config.settings import TASK_QUEUE_TIMEOUT

logger = logging.getLogger(__name__)


class TaskQueue:
    def __init__(self, max_concurrent_tasks: int):
        self.task_queue = Queue()
        self.max_concurrent_tasks = max_concurrent_tasks
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)

    def start_workers(self):
        for _ in range(self.max_concurrent_tasks):
            Thread(target=self._worker_thread, daemon=True).start()

    def _worker_thread(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while True:
            task_id, task_request, worker_func, start_time = self.task_queue.get()
            try:
                if datetime.utcnow() - start_time <= timedelta(seconds=TASK_QUEUE_TIMEOUT):
                    loop.run_until_complete(self._run_task(worker_func, task_id, task_request))
                else:
                    logger.warning(
                        f"Task {task_id} has exceeded the timeout of {TASK_QUEUE_TIMEOUT} seconds."
                    )
            except Exception as e:
                error_stack = traceback.format_exc()
                logger.error(f"Error processing task {task_id}: {e}\n{error_stack}")
            finally:
                self.task_queue.task_done()

    async def _run_task(
        self, worker_func: Callable, task_id: uuid.UUID, task_request: dict
    ):
        async with self.semaphore:
            if inspect.iscoroutinefunction(worker_func):
                result = await worker_func(**task_request)
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, lambda: worker_func(**task_request))
            logger.info(f"Task {task_id} completed with result: {result}")
            return result

    def add_task(
        self,
        task_id: uuid.UUID,
        task_request: dict,
        worker_func: Callable,
        start_time: datetime,
    ):
        self.task_queue.put((task_id, task_request, worker_func, start_time))
