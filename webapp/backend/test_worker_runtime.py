from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from knowledge_base import KnowledgeBaseStore
from worker_runtime import ResearchWorkerRuntime, work_item_recovery_action


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
        assert status["queued_count"] == 1
        assert status["active_work_item_count"] == 1
        assert status["user_facing_status"]["state"] == "worker_disabled"
        assert status["user_facing_status"]["next_actions"] == ["enable_worker_or_manual_tick", "monitor_queue"]
        assert "owner" not in status["user_facing_status"]["safe_default_fields"]
        assert "worker-test" not in str(status["user_facing_status"])
        assert status["queue_status_counts"]["queued"] == 1
        assert status["queue_status_counts"]["active"] == 1
        assert status["active_work_item_snapshot"]["counts"]["queued"] == 1
        assert status["active_work_item_snapshot"]["items"][0]["workflow_name"] == "workflow.test"
        assert "work_item_id" not in status["active_work_item_snapshot"]["items"][0]
        assert "arguments" not in status["active_work_item_snapshot"]["items"][0]
        runtime_status = runtime.status()
        assert runtime_status["queued_count"] == 1
        assert runtime_status["active_work_item_count"] == 1
        assert runtime_status["user_facing_status"]["state"] == "worker_disabled"
        assert runtime_status["queue_status_counts"]["queued"] == 1
        assert runtime_status["active_work_item_snapshot"]["counts"]["active"] == 1
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
        assert status["leased_count_total"] == 1
        assert status["active_work_item_count"] == 1
        assert status["user_facing_status"]["state"] == "running"
        assert status["user_facing_status"]["next_actions"] == ["monitor_progress", "view_process_summary"]
        assert "stale-worker" not in str(status["user_facing_status"])
        assert "fresh-worker" not in str(status["user_facing_status"])
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


@pytest.mark.anyio
async def test_worker_renews_lease_during_long_handler() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        item = store.enqueue_work_item(
            workflow_name="workflow.test",
            arguments={"value": "long-running"},
        )

        async def handler(work_item):
            await asyncio.sleep(1.25)
            return {"value": work_item["arguments"]["value"]}

        runtime = ResearchWorkerRuntime(
            store=store,
            handlers={"workflow.test": handler},
            owner="heartbeat-worker",
            concurrency=1,
            lease_seconds=1,
            enabled=True,
        )

        status = await runtime.tick()
        assert status["leased_count"] == 1
        results = await asyncio.gather(*runtime._running_tasks)
        assert results[0]["status"] == "complete"

        completed = store.get_work_item(item["work_item_id"])
        assert completed["status"] == "complete"
        assert completed["attempt_count"] == 1
        assert completed["result_ref"]["value"] == "long-running"


@pytest.mark.anyio
async def test_worker_skips_handler_when_running_mark_loses_lease() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        item = store.enqueue_work_item(
            workflow_name="workflow.test",
            arguments={"value": "do-not-run"},
        )
        leased = store.lease_work_items(owner="lease-conflict-worker", lease_seconds=1)
        with store._connection() as connection:
            connection.execute(
                """
                UPDATE research_work_items
                SET lease_expires_at = ?
                WHERE work_item_id = ?
                """,
                (0, leased[0]["work_item_id"]),
            )

        calls = {"count": 0}

        async def handler(_work_item):
            calls["count"] += 1
            return {"handled": True}

        runtime = ResearchWorkerRuntime(
            store=store,
            handlers={"workflow.test": handler},
            owner="lease-conflict-worker",
            concurrency=1,
            enabled=True,
        )

        result = await runtime._execute_work_item(leased[0])

        assert result["status"] == "lease_conflict"
        assert calls["count"] == 0
        stale = store.get_work_item(item["work_item_id"])
        assert stale["status"] == "leased"
        assert stale["result_ref"] == {}


@pytest.mark.anyio
async def test_worker_user_facing_status_hides_worker_internals() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        store.enqueue_work_item(
            workflow_name="workflow.test",
            arguments={"secret": "SECRET ARGUMENT"},
        )
        runtime = ResearchWorkerRuntime(
            store=store,
            handlers={"workflow.test": lambda _item: {"handled": True}},
            owner="owner-secret",
            concurrency=1,
            enabled=False,
        )

        status = runtime.status()
        user_status = status["user_facing_status"]

        assert user_status["state"] == "worker_disabled"
        assert user_status["counts"]["queued_count"] == 1
        assert user_status["counts"]["active_work_item_count"] == 1
        assert user_status["expert_fields"] == [
            "owner",
            "lease_seconds",
            "poll_seconds",
            "lease_owner",
            "lease_expires_at",
            "last_error",
            "raw work item arguments",
        ]
        assert "owner-secret" not in str(user_status)
        assert "SECRET ARGUMENT" not in str(user_status)
        assert "raw errors" in user_status["visibility_boundary"]


def test_work_item_recovery_action_maps_queue_and_checkpoint_states_without_raw_refs() -> None:
    resumable = work_item_recovery_action(
        {
            "work_item_id": "work-secret",
            "run_id": "run-secret",
            "status": "running",
            "attempt_count": 1,
            "max_attempts": 3,
            "lease_owner": "owner-secret",
            "arguments": {"provider_key": "SECRET PROVIDER KEY"},
        },
        resume_readiness={
            "status": "ready_to_resume",
            "can_resume": True,
            "should_retry": False,
            "checkpoint_id": "checkpoint-secret",
        },
    )

    assert resumable == {
        "status": "running",
        "action": "resume",
        "resume_readiness_status": "ready_to_resume",
        "can_resume": True,
        "should_retry": False,
        "attempts": {"current": 1, "max": 3, "remaining": 2},
        "next_actions": ["resume_langgraph_thread", "monitor_progress"],
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
    assert "work-secret" not in str(resumable)
    assert "run-secret" not in str(resumable)
    assert "owner-secret" not in str(resumable)
    assert "checkpoint-secret" not in str(resumable)
    assert "SECRET" not in str(resumable)

    retrying = work_item_recovery_action(
        {"status": "retrying", "attempt_count": 2, "max_attempts": 3},
        resume_readiness={"status": "metadata_guided_retry", "should_retry": True},
    )
    assert retrying["action"] == "retry"
    assert retrying["attempts"] == {"current": 2, "max": 3, "remaining": 1}
    assert retrying["next_actions"] == ["retry_or_wait_for_worker", "monitor_queue"]

    exhausted_error = work_item_recovery_action({"status": "error", "attempt_count": 3, "max_attempts": 3})
    assert exhausted_error["action"] == "escalate"
    assert exhausted_error["should_retry"] is False
    assert exhausted_error["next_actions"] == ["inspect_failure_summary", "start_new_run_or_cancel"]

    queued = work_item_recovery_action({"status": "queued", "attempt_count": 0, "max_attempts": 3})
    assert queued["action"] == "wait"
    assert queued["next_actions"] == ["monitor_queue", "check_worker_status"]
