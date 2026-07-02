from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from knowledge_base import KnowledgeBaseStore
from worker_runtime import ResearchWorkerRuntime


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_worker_tick_executes_leased_work_item() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        item = store.enqueue_work_item(
            workflow_name="workflow.test",
            arguments={"value": 42},
        )

        async def handler(work_item):
            assert work_item["arguments"]["value"] == 42
            return {"handled": True}

        runtime = ResearchWorkerRuntime(
            store=store,
            handlers={"workflow.test": handler},
            owner="worker-test",
            concurrency=1,
            enabled=True,
        )
        status = await runtime.tick()
        assert status["leased_count"] == 1

        await asyncio.gather(*runtime._running_tasks)
        completed = store.get_work_item(item["work_item_id"])
        assert completed["status"] == "complete"
        assert completed["result_ref"]["handled"] is True


@pytest.mark.anyio
async def test_worker_tick_fails_missing_handler_without_retry() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        item = store.enqueue_work_item(
            workflow_name="workflow.missing",
            arguments={},
            max_attempts=3,
        )
        runtime = ResearchWorkerRuntime(
            store=store,
            handlers={},
            owner="worker-test",
            concurrency=1,
            enabled=True,
        )

        await runtime.tick()
        await asyncio.gather(*runtime._running_tasks)

        failed = store.get_work_item(item["work_item_id"])
        assert failed["status"] == "error"
        assert "No handler registered" in failed["error_message"]


@pytest.mark.anyio
async def test_worker_tick_respects_disabled_mode() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        item = store.enqueue_work_item(
            workflow_name="workflow.test",
            arguments={},
        )
        runtime = ResearchWorkerRuntime(
            store=store,
            handlers={"workflow.test": lambda _item: {"handled": True}},
            owner="worker-test",
            concurrency=1,
            enabled=False,
        )

        status = await runtime.tick()
        assert status["leased_count"] == 0
        assert store.get_work_item(item["work_item_id"])["status"] == "queued"


@pytest.mark.anyio
async def test_worker_tick_recovers_expired_leases_before_leasing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        item = store.enqueue_work_item(
            workflow_name="workflow.test",
            arguments={"value": "recover"},
        )
        leased = store.lease_work_items(owner="stale-worker", lease_seconds=1)
        assert leased[0]["work_item_id"] == item["work_item_id"]
        with store._connection() as connection:
            connection.execute(
                """
                UPDATE research_work_items
                SET lease_expires_at = ?
                WHERE work_item_id = ?
                """,
                (leased[0]["lease_expires_at"] - 10, item["work_item_id"]),
            )

        async def handler(work_item):
            return {"value": work_item["arguments"]["value"]}

        runtime = ResearchWorkerRuntime(
            store=store,
            handlers={"workflow.test": handler},
            owner="fresh-worker",
            concurrency=1,
            enabled=True,
        )

        status = await runtime.tick()
        assert status["recovered_count"] == 1
        assert status["leased_count"] == 1
        await asyncio.gather(*runtime._running_tasks)

        completed = store.get_work_item(item["work_item_id"])
        assert completed["status"] == "complete"
        assert completed["result_ref"]["value"] == "recover"
