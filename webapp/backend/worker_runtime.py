from __future__ import annotations

import asyncio
import inspect
import socket
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional


WorkItem = Dict[str, Any]
WorkItemHandler = Callable[[WorkItem], Awaitable[Optional[Dict[str, Any]]] | Optional[Dict[str, Any]]]


def default_worker_owner() -> str:
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


def work_item_recovery_action(
    work_item: WorkItem | None,
    *,
    resume_readiness: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    item = dict(work_item or {})
    readiness = dict(resume_readiness or {})
    status = str(item.get("status") or "unknown").strip().lower()
    attempts = int(item.get("attempt_count") or 0)
    max_attempts = int(item.get("max_attempts") or 0)
    attempts_remaining = max(0, max_attempts - attempts) if max_attempts > 0 else None
    readiness_status = str(readiness.get("status") or "").strip()
    can_resume = bool(readiness.get("can_resume"))
    should_retry = bool(readiness.get("should_retry"))

    if can_resume:
        action = "resume"
        next_actions = ["resume_langgraph_thread", "monitor_progress"]
    elif status in {"queued", "leased", "running"}:
        action = "wait"
        next_actions = ["monitor_queue", "check_worker_status"]
    elif status == "retrying" or should_retry:
        action = "retry"
        next_actions = ["retry_or_wait_for_worker", "monitor_queue"]
    elif status == "blocked":
        action = "unblock"
        next_actions = ["inspect_blocking_condition", "edit_or_cancel_work_item"]
    elif status in {"error", "failed"}:
        action = "retry" if _work_item_attempts_available(attempts_remaining) else "escalate"
        next_actions = (
            ["retry_work_item", "inspect_failure_summary"]
            if action == "retry"
            else ["inspect_failure_summary", "start_new_run_or_cancel"]
        )
    elif status in {"complete", "completed"}:
        action = "none"
        next_actions = ["inspect_results"]
    elif status == "cancelled":
        action = "none"
        next_actions = ["start_new_run"]
    else:
        action = "inspect"
        next_actions = ["inspect_queue_state"]

    return {
        "status": status,
        "action": action,
        "resume_readiness_status": readiness_status or None,
        "can_resume": can_resume,
        "should_retry": should_retry or action == "retry",
        "attempts": {
            "current": attempts,
            "max": max_attempts,
            "remaining": attempts_remaining,
        },
        "next_actions": next_actions,
        "safe_default_fields": [
            "status",
            "action",
            "resume_readiness_status",
            "can_resume",
            "should_retry",
            "attempts",
            "next_actions",
        ],
        "visibility_boundary": (
            "Work item recovery action summarizes queue status, checkpoint readiness, retry budget, "
            "and user-safe next actions; raw arguments, result refs, lease owners, internal IDs, "
            "and provider payloads require expert disclosure."
        ),
    }


def _work_item_attempts_available(attempts_remaining: Optional[int]) -> bool:
    return attempts_remaining is None or attempts_remaining > 0


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
        active_work_item_snapshot = self._active_work_item_snapshot()
        queue_status_counts = dict(active_work_item_snapshot.get("counts") or self._queue_status_counts())
        recovery_action_counts = dict(active_work_item_snapshot.get("recovery_action_counts") or {})
        queue_count_summary = self._queue_count_summary(queue_status_counts)
        running_count = len(self._running_tasks)
        return {
            "enabled": self.enabled,
            "owner": self.owner,
            "concurrency": self.concurrency,
            "lease_seconds": self.lease_seconds,
            "poll_seconds": self.poll_seconds,
            "recovered_count": recovered_count,
            "leased_count": len(leased),
            "running_count": running_count,
            "queue_status_counts": queue_status_counts,
            "active_work_item_snapshot": active_work_item_snapshot,
            **queue_count_summary,
            "user_facing_status": self._user_facing_status(
                queue_status_counts,
                running_count=running_count,
                recovery_action_counts=recovery_action_counts,
            ),
            "last_tick_at": self._last_tick_at,
            "last_error": self._last_error,
        }

    def status(self) -> Dict[str, Any]:
        active_work_item_snapshot = self._active_work_item_snapshot()
        queue_status_counts = dict(active_work_item_snapshot.get("counts") or self._queue_status_counts())
        recovery_action_counts = dict(active_work_item_snapshot.get("recovery_action_counts") or {})
        running_count = len([task for task in self._running_tasks if not task.done()])
        return {
            "enabled": self.enabled,
            "owner": self.owner,
            "concurrency": self.concurrency,
            "lease_seconds": self.lease_seconds,
            "poll_seconds": self.poll_seconds,
            "running_count": running_count,
            "queue_status_counts": queue_status_counts,
            "active_work_item_snapshot": active_work_item_snapshot,
            **self._queue_count_summary(queue_status_counts),
            "user_facing_status": self._user_facing_status(
                queue_status_counts,
                running_count=running_count,
                recovery_action_counts=recovery_action_counts,
            ),
            "last_tick_at": self._last_tick_at,
            "last_error": self._last_error,
        }

    def _active_work_item_snapshot(self) -> Dict[str, Any]:
        snapshotter = getattr(self.store, "active_work_item_snapshot", None)
        if not callable(snapshotter):
            return {
                "counts": self._queue_status_counts(),
                "items": [],
                "visibility_boundary": "Store does not expose active work item snapshots.",
            }
        try:
            return dict(snapshotter(limit=max(1, min(50, int(self.concurrency or 1) * 10))))
        except Exception as exc:  # pragma: no cover - defensive status reporting
            self._last_error = str(exc)
            return {
                "counts": self._queue_status_counts(),
                "items": [],
                "visibility_boundary": "Active work item snapshot unavailable.",
            }

    def _queue_status_counts(self) -> Dict[str, int]:
        counter = getattr(self.store, "work_item_status_counts", None)
        if not callable(counter):
            return {}
        try:
            return dict(counter())
        except Exception as exc:  # pragma: no cover - defensive status reporting
            self._last_error = str(exc)
            return {}

    def _queue_count_summary(self, counts: Dict[str, int]) -> Dict[str, int]:
        return {
            "queued_count": int(counts.get("queued", 0)),
            "leased_count_total": int(counts.get("leased", 0)),
            "retrying_count": int(counts.get("retrying", 0)),
            "active_work_item_count": int(counts.get("active", 0)),
            "error_count": int(counts.get("error", 0)),
        }

    def _user_facing_status(
        self,
        counts: Dict[str, int],
        *,
        running_count: int = 0,
        recovery_action_counts: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        queue_summary = self._queue_count_summary(counts)
        recovery_counts = {
            action: int((recovery_action_counts or {}).get(action, 0))
            for action in ("wait", "retry", "unblock", "escalate", "inspect", "none")
        }
        state = self._user_facing_state(counts, running_count=running_count)
        return {
            "state": state,
            "label": self._user_facing_label(state),
            "next_actions": self._user_facing_next_actions(state),
            "counts": queue_summary,
            "recovery_action_counts": recovery_counts,
            "safe_default_fields": [
                "state",
                "label",
                "next_actions",
                "counts.queued_count",
                "counts.retrying_count",
                "counts.active_work_item_count",
                "counts.error_count",
                "recovery_action_counts",
            ],
            "expert_fields": [
                "owner",
                "lease_seconds",
                "poll_seconds",
                "lease_owner",
                "lease_expires_at",
                "last_error",
                "raw work item arguments",
            ],
            "visibility_boundary": (
                "Worker status exposes user-facing queue state, counts, and next actions by default; "
                "owner identity, lease timing, worker internals, raw errors, and work item arguments "
                "require expert disclosure."
            ),
        }

    def _user_facing_state(self, counts: Dict[str, int], *, running_count: int = 0) -> str:
        active_count = int(counts.get("active", 0))
        if not self.enabled and active_count > 0:
            return "worker_disabled"
        if not self.enabled:
            return "disabled"
        if int(counts.get("error", 0)) > 0 or int(counts.get("blocked", 0)) > 0:
            return "needs_attention"
        if int(counts.get("retrying", 0)) > 0:
            return "retrying"
        if running_count > 0 or int(counts.get("running", 0)) > 0 or int(counts.get("leased", 0)) > 0:
            return "running"
        if int(counts.get("queued", 0)) > 0:
            return "queued"
        return "ready"

    def _user_facing_label(self, state: str) -> str:
        return {
            "ready": "Background research worker is ready.",
            "disabled": "Background worker is disabled.",
            "worker_disabled": "Research work is queued but the worker is disabled.",
            "queued": "Research work is queued.",
            "running": "Research work is running.",
            "retrying": "Research work is waiting for retry.",
            "needs_attention": "Research work needs attention.",
        }.get(state, "Inspect worker status.")

    def _user_facing_next_actions(self, state: str) -> list[str]:
        return {
            "ready": ["start_or_continue_research_run"],
            "disabled": ["enable_worker_or_use_manual_tick"],
            "worker_disabled": ["enable_worker_or_manual_tick", "monitor_queue"],
            "queued": ["wait_for_worker", "check_worker_status"],
            "running": ["monitor_progress", "view_process_summary"],
            "retrying": ["wait_for_retry", "inspect_queue_if_stuck"],
            "needs_attention": ["inspect_queue", "retry_or_cancel_work_item"],
        }.get(state, ["inspect_worker_status"])

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

    def _lease_heartbeat_interval(self) -> float:
        return max(0.1, min(30.0, float(self.lease_seconds or 1) / 3.0))

    def _start_lease_heartbeat(self, work_item_id: str) -> Optional[asyncio.Task[None]]:
        renew = getattr(self.store, "renew_work_item_lease", None)
        if not callable(renew):
            return None
        return asyncio.create_task(
            self._lease_heartbeat_loop(work_item_id),
            name=f"coscientist-lease-heartbeat:{work_item_id}",
        )

    async def _lease_heartbeat_loop(self, work_item_id: str) -> None:
        while True:
            await asyncio.sleep(self._lease_heartbeat_interval())
            renewed = self.store.renew_work_item_lease(
                work_item_id,
                self.owner,
                lease_seconds=self.lease_seconds,
            )
            if not renewed:
                return

    def _owns_active_lease(self, work_item_id: str) -> bool:
        current = self.store.get_work_item(work_item_id)
        if not current:
            return False
        if current.get("lease_owner") != self.owner:
            return False
        if current.get("status") not in {"leased", "running"}:
            return False
        lease_expires_at = current.get("lease_expires_at")
        if lease_expires_at is not None and float(lease_expires_at) <= time.time():
            return False
        return True

    async def _execute_work_item(self, item: WorkItem) -> Dict[str, Any]:
        work_item_id = str(item["work_item_id"])
        workflow_name = str(item["workflow_name"])
        handler = self.handlers.get(workflow_name)
        if handler is None:
            message = f"No handler registered for workflow: {workflow_name}"
            self.store.fail_work_item(work_item_id, message, retryable=False)
            return {"work_item_id": work_item_id, "status": "error", "error": message}

        if not self.store.mark_work_item_running(work_item_id, self.owner):
            return {"work_item_id": work_item_id, "status": "lease_conflict"}
        heartbeat_task = self._start_lease_heartbeat(work_item_id)
        try:
            result = handler(item)
            if inspect.isawaitable(result):
                result = await result
            result_ref = result or {}
            if not self._owns_active_lease(work_item_id):
                return {"work_item_id": work_item_id, "status": "stale_lease"}
            self.store.complete_work_item(work_item_id, result_ref)
            return {"work_item_id": work_item_id, "status": "complete", "result_ref": result_ref}
        except asyncio.CancelledError:
            if self._owns_active_lease(work_item_id):
                self.store.fail_work_item(work_item_id, "Worker task was cancelled.", retryable=True)
            raise
        except Exception as exc:
            if self._owns_active_lease(work_item_id):
                self.store.fail_work_item(work_item_id, str(exc), retryable=True)
            return {"work_item_id": work_item_id, "status": "error", "error": str(exc)}
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task
