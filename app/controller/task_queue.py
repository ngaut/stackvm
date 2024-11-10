import asyncio
from datetime import datetime
from queue import Queue
from threading import Thread
import uuid
from typing import Callable, Any
import logging
import traceback

from app.config.settings import TASK_QUEUE_WORKERS, TASK_QUEUE_TIMEOUT

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
                if datetime.utcnow() - start_time <= datetime.timedelta(
                    seconds=settings.TASK_QUEUE_TIMEOUT
                ):
                    asyncio.run(self._run_task(worker_func, task_id, task_request))
                else:
                    logger.warning(
                        f"Task {task_id} has exceeded the timeout of {settings.TASK_QUEUE_TIMEOUT} seconds."
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
            await worker_func(**task_request)

    def add_task(
        self,
        task_id: uuid.UUID,
        task_request: dict,
        worker_func: Callable,
        start_time: datetime,
    ):
        self.task_queue.put((task_id, task_request, worker_func, start_time))
