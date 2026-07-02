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
        assert status["queue_status_counts"]["queued"] == 1
        assert status["queue_status_counts"]["active"] == 1
        assert runtime.status()["queue_status_counts"]["queued"] == 1
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
        assert status["queue_status_counts"]["leased"] == 1
        assert status["queue_status_counts"]["active"] == 1
        await asyncio.gather(*runtime._running_tasks)

        completed = store.get_work_item(item["work_item_id"])
        assert completed["status"] == "complete"
        assert completed["result_ref"]["value"] == "recover"


@pytest.mark.anyio
async def test_worker_does_not_complete_after_lease_expires_during_handler() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        item = store.enqueue_work_item(
            workflow_name="workflow.test",
            arguments={"value": "late"},
        )

        async def handler(work_item):
            with store._connection() as connection:
                connection.execute(
                    """
                    UPDATE research_work_items
                    SET lease_expires_at = ?
                    WHERE work_item_id = ?
                    """,
                    (0, work_item["work_item_id"]),
                )
            return {"value": work_item["arguments"]["value"]}

        runtime = ResearchWorkerRuntime(
            store=store,
            handlers={"workflow.test": handler},
            owner="late-worker",
            concurrency=1,
            enabled=True,
        )

        status = await runtime.tick()
        assert status["leased_count"] == 1
        results = await asyncio.gather(*runtime._running_tasks)
        assert results[0]["status"] == "stale_lease"

        stale = store.get_work_item(item["work_item_id"])
        assert stale["status"] == "running"
        assert stale["result_ref"] == {}

        recovered_count = store.recover_expired_leases()
        assert recovered_count == 1
        assert store.get_work_item(item["work_item_id"])["status"] == "retrying"


@pytest.mark.anyio
async def test_worker_retries_and_completes_after_stale_lease_tick() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        item = store.enqueue_work_item(
            workflow_name="workflow.test",
            arguments={"value": "recover-late"},
            max_attempts=3,
        )
        calls = {"count": 0}

        async def handler(work_item):
            calls["count"] += 1
            if calls["count"] == 1:
                with store._connection() as connection:
                    connection.execute(
                        """
                        UPDATE research_work_items
                        SET lease_expires_at = ?
                        WHERE work_item_id = ?
                        """,
                        (0, work_item["work_item_id"]),
                    )
                return {"value": "stale"}
            return {"value": work_item["arguments"]["value"], "attempt": calls["count"]}

        runtime = ResearchWorkerRuntime(
            store=store,
            handlers={"workflow.test": handler},
            owner="recover-worker",
            concurrency=1,
            enabled=True,
        )

        first_status = await runtime.tick()
        assert first_status["leased_count"] == 1
        first_results = await asyncio.gather(*runtime._running_tasks)
        assert first_results[0]["status"] == "stale_lease"

        stale = store.get_work_item(item["work_item_id"])
        assert stale["status"] == "running"
        assert stale["attempt_count"] == 1

        second_status = await runtime.tick()
        assert second_status["recovered_count"] == 1
        assert second_status["leased_count"] == 1
        second_results = await asyncio.gather(*runtime._running_tasks)
        assert second_results[0]["status"] == "complete"

        completed = store.get_work_item(item["work_item_id"])
        assert completed["status"] == "complete"
        assert completed["attempt_count"] == 2
        assert completed["result_ref"]["value"] == "recover-late"
        assert completed["result_ref"]["attempt"] == 2
