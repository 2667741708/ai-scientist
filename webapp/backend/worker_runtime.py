from __future__ import annotations

import asyncio
import inspect
import socket
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional


WorkItem = Dict[str, Any]
WorkItemHandler = Callable[[WorkItem], Awaitable[Optional[Dict[str, Any]]] | Optional[Dict[str, Any]]]


def default_worker_owner() -> str:
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


@dataclass
class ResearchWorkerRuntime:
    store: Any
    handlers: Dict[str, WorkItemHandler]
    owner: str = field(default_factory=default_worker_owner)
    concurrency: int = 1
    lease_seconds: int = 300
    poll_seconds: float = 2.0
    enabled: bool = True

    _loop_task: Optional[asyncio.Task[None]] = field(default=None, init=False)
    _stop_event: Optional[asyncio.Event] = field(default=None, init=False)
    _running_tasks: set[asyncio.Task[Dict[str, Any]]] = field(default_factory=set, init=False)
    _last_tick_at: Optional[float] = field(default=None, init=False)
    _last_error: Optional[str] = field(default=None, init=False)

    async def start(self) -> None:
        if not self.enabled or self._loop_task:
            return
        self._stop_event = asyncio.Event()
        self._loop_task = asyncio.create_task(self._run_loop(), name=f"coscientist-worker:{self.owner}")

    async def stop(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        if self._loop_task:
            await self._loop_task
            self._loop_task = None
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks, return_exceptions=True)

    async def tick(self) -> Dict[str, Any]:
        self._last_tick_at = time.time()
        recovered_count = self.store.recover_expired_leases()
        self._running_tasks = {task for task in self._running_tasks if not task.done()}
        available_slots = max(0, int(self.concurrency or 1) - len(self._running_tasks))
        leased: list[WorkItem] = []
        if self.enabled and available_slots > 0:
            leased = self.store.lease_work_items(
                owner=self.owner,
                limit=available_slots,
                lease_seconds=self.lease_seconds,
            )
            for item in leased:
                task = asyncio.create_task(self._execute_work_item(item))
                self._running_tasks.add(task)
                task.add_done_callback(self._running_tasks.discard)
        return {
            "enabled": self.enabled,
            "owner": self.owner,
            "concurrency": self.concurrency,
            "lease_seconds": self.lease_seconds,
            "poll_seconds": self.poll_seconds,
            "recovered_count": recovered_count,
            "leased_count": len(leased),
            "running_count": len(self._running_tasks),
            "last_tick_at": self._last_tick_at,
            "last_error": self._last_error,
        }

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "owner": self.owner,
            "concurrency": self.concurrency,
            "lease_seconds": self.lease_seconds,
            "poll_seconds": self.poll_seconds,
            "running_count": len([task for task in self._running_tasks if not task.done()]),
            "last_tick_at": self._last_tick_at,
            "last_error": self._last_error,
        }

    async def _run_loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await self.tick()
                self._last_error = None
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                self._last_error = str(exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=max(0.1, float(self.poll_seconds)))
            except asyncio.TimeoutError:
                continue

    async def _execute_work_item(self, item: WorkItem) -> Dict[str, Any]:
        work_item_id = str(item["work_item_id"])
        workflow_name = str(item["workflow_name"])
        handler = self.handlers.get(workflow_name)
        if handler is None:
            message = f"No handler registered for workflow: {workflow_name}"
            self.store.fail_work_item(work_item_id, message, retryable=False)
            return {"work_item_id": work_item_id, "status": "error", "error": message}

        self.store.mark_work_item_running(work_item_id, self.owner)
        try:
            result = handler(item)
            if inspect.isawaitable(result):
                result = await result
            result_ref = result or {}
            self.store.complete_work_item(work_item_id, result_ref)
            return {"work_item_id": work_item_id, "status": "complete", "result_ref": result_ref}
        except asyncio.CancelledError:
            self.store.fail_work_item(work_item_id, "Worker task was cancelled.", retryable=True)
            raise
        except Exception as exc:
            self.store.fail_work_item(work_item_id, str(exc), retryable=True)
            return {"work_item_id": work_item_id, "status": "error", "error": str(exc)}
