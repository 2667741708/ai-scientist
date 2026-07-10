from __future__ import annotations

import pytest

from research_autopilot import (
    LOOP_STAGES,
    AutopilotValidationError,
    advance_loop_state,
    begin_next_cycle,
    build_experiment_protocol,
    build_loop_state,
    consume_exact_grant,
    evaluate_experiment_result,
    exact_grant,
    execution_scope,
    normalize_policy,
    parse_result_json_marker,
    request_loop_approval,
    resolve_loop_approval,
    update_loop_stage,
)


def test_policy_is_bounded_and_grants_are_exact() -> None:
    policy = normalize_policy(
        {
            "mode": "autonomous_compute",
            "max_cycles": 999,
            "compute": {"kind": "ssh", "server_id": "gpu-a", "workdir": "/research"},
            "evaluation": {
                "metric_path": "metrics.validation.accuracy",
                "operator": ">=",
                "threshold": 0.8,
            },
            "grants": [
                {
                    "confirmed": True,
                    "scope": "ssh.training_command",
                    "server_id": "gpu-a",
                    "reason": "Run preregistered experiment",
                    "max_uses": 2,
                },
                {"confirmed": True, "scope": "*"},
            ],
        }
    )

    assert policy["mode"] == "autonomous_compute"
    assert policy["max_cycles"] == 12
    assert all(policy[key] for key in ("auto_evidence", "auto_plan", "auto_execute"))
    assert policy["compute"]["kind"] == "ssh"
    assert policy["compute"]["server_id"] == "gpu-a"
    assert policy["compute"]["workdir"] == "/research"
    assert policy["evaluation"]["threshold"] == 0.8
    assert len(policy["grants"]) == 1
    assert execution_scope(policy["compute"]) == "ssh.training_command"
    assert exact_grant(policy, "ssh.training_command", "gpu-a") is True
    assert exact_grant(policy, "ssh.training_command", "gpu-b") is False
    assert exact_grant(policy, "ssh.training") is False

    consumed = consume_exact_grant(policy, "ssh.training_command", "gpu-a")
    assert consumed["grants"][0]["used"] == 1
    consumed = consume_exact_grant(consumed, "ssh.training_command", "gpu-a")
    assert consumed["grants"][0]["used"] == 2
    assert exact_grant(consumed, "ssh.training_command", "gpu-a") is False


def test_manual_policy_disables_automation_and_expiring_grant_needs_clock() -> None:
    policy = normalize_policy(
        {
            "mode": "manual",
            "auto_execute": True,
            "continue_on_limited_evidence": True,
            "compute": "local",
            "grants": [
                {
                    "confirmed": True,
                    "scope": "experiment.background_job",
                    "expires_at": 200.0,
                }
            ],
        }
    )
    assert all(policy[key] is False for key in (
        "auto_evidence",
        "auto_plan",
        "auto_execute",
        "auto_interpret",
        "auto_rerank",
    ))
    assert policy["continue_on_limited_evidence"] is True
    assert execution_scope(policy["compute"]) == "experiment.background_job"
    assert exact_grant(policy, "experiment.background_job") is False
    assert exact_grant(policy, "experiment.background_job", now=199.0) is True
    assert exact_grant(policy, "experiment.background_job", now=200.0) is False


def test_ssh_compute_only_binds_the_ssh_execution_grant_to_a_server() -> None:
    policy = normalize_policy(
        {
            "mode": "autonomous_compute",
            "compute": {"kind": "ssh", "server_id": "gpu-a", "command": "python train.py"},
            "grants": [
                {"confirmed": True, "scope": "mcp.literature_review"},
                {"confirmed": True, "scope": "experiment.feedback"},
                {
                    "confirmed": True,
                    "scope": "ssh.training_command",
                    "server_id": "gpu-a",
                },
            ],
        }
    )

    assert exact_grant(policy, "mcp.literature_review") is True
    assert exact_grant(policy, "experiment.feedback") is True
    assert exact_grant(policy, "ssh.training_command") is True
    assert exact_grant(policy, "ssh.training_command", "gpu-b") is False


def test_loop_state_has_ordered_stages_and_pure_transitions() -> None:
    initial = build_loop_state(
        normalize_policy({"mode": "guarded", "max_cycles": 2}),
        run_id="run_1",
    )
    assert [item["id"] for item in initial["stages"]] == list(LOOP_STAGES)
    assert initial["current_stage"] == "discover"
    assert initial["status"] == "ready"
    assert initial["policy"]["mode"] == "guarded"

    running = update_loop_stage(initial, "discover", "running", at=10.0)
    assert running["status"] == "running"
    assert running["stages"][0]["attempts"] == 1
    assert initial["stages"][0]["status"] == "ready"

    acquired = advance_loop_state(running, message="Discovery snapshot saved", at=11.0)
    assert acquired["stages"][0]["status"] == "complete"
    assert acquired["current_stage"] == "acquire_parse"
    assert acquired["stages"][1]["status"] == "running"

    blocked = request_loop_approval(
        acquired,
        scope="pdf.parse_to_knowledge_base",
        stage="acquire_parse",
        reason="PDF acquisition writes to the knowledge base.",
        at=12.0,
    )
    assert blocked["status"] == "waiting_approval"
    assert blocked["pending_approvals"][0]["scope"] == "pdf.parse_to_knowledge_base"

    resumed = resolve_loop_approval(
        blocked,
        scope="pdf.parse_to_knowledge_base",
        granted=True,
        reason="Approved for this run.",
        at=13.0,
    )
    assert resumed["status"] == "ready"
    assert resumed["pending_approvals"] == []
    assert resumed["approval_history"][0]["status"] == "granted"


def test_loop_cycle_limit_is_enforced() -> None:
    state = build_loop_state(normalize_policy({"mode": "guarded", "max_cycles": 2}))
    state = update_loop_stage(state, "rerank", "running")
    second = begin_next_cycle(state)
    assert second["cycle"] == 2
    assert second["current_stage"] == "ground"
    second = update_loop_stage(second, "rerank", "running")
    with pytest.raises(AutopilotValidationError, match="maximum"):
        begin_next_cycle(second)


def _protocol(operator_name: str = ">=", threshold: float = 0.8):
    return build_experiment_protocol(
        {
            "id": "hyp_1",
            "text": "Retrieval-grounded generation improves citation precision.",
            "experiment_plan": {"steps": ["freeze corpus", "run benchmark"]},
        },
        {
            "snapshot_id": "snapshot_1",
            "items": [
                {
                    "evidence_id": "ev_1",
                    "paper_id": "paper_1",
                    "chunk_id": "chunk_4",
                    "parse_run_id": "parse_2",
                    "title": "Citation benchmark",
                    "relationship": "support",
                }
            ],
        },
        {
            "mode": "guarded",
            "compute": {"kind": "local_python"},
            "evaluation": {
                "metric_path": "metrics.validation[0].accuracy",
                "operator": operator_name,
                "threshold": threshold,
            },
        },
    )


def test_protocol_links_sources_and_evaluates_nested_metric() -> None:
    protocol = _protocol()
    assert protocol["status"] == "preregistered"
    assert protocol["source_refs"][0]["paper_id"] == "paper_1"
    assert protocol["source_refs"][0]["chunk_id"] == "chunk_4"
    assert protocol["required_approval_scope"] == "experiment.background_job"
    assert "not proof" in protocol["scientific_boundary"]

    support = evaluate_experiment_result(
        protocol,
        {"metrics": {"validation": [{"accuracy": 0.84}]}},
    )
    assert support["verdict"] == "support"
    assert support["metric_value"] == 0.84

    contradict = evaluate_experiment_result(
        protocol,
        {"metrics": {"validation": [{"accuracy": 0.7}]}},
    )
    assert contradict["verdict"] == "contradict"

    boundary = evaluate_experiment_result(
        _protocol(operator_name=">", threshold=0.8),
        {"metrics": {"validation": [{"accuracy": 0.8}]}},
    )
    assert boundary["verdict"] == "inconclusive"


def test_protocol_identity_changes_with_procedure_and_compute_contract() -> None:
    base_hypothesis = {
        "id": "hyp_1",
        "text": "A fixed benchmark tests the claim.",
        "experiment": {"steps": ["run baseline"]},
    }
    packet = {"snapshot_id": "snapshot_1", "items": []}
    policy = {
        "mode": "autonomous_compute",
        "compute": {"kind": "local_python", "script_path": "baseline.py"},
        "evaluation": {"metric_path": "score", "operator": ">=", "threshold": 1},
    }
    baseline = build_experiment_protocol(base_hypothesis, packet, policy)
    changed_procedure = build_experiment_protocol(
        {**base_hypothesis, "experiment": {"steps": ["run ablation"]}},
        packet,
        policy,
    )
    changed_compute = build_experiment_protocol(
        base_hypothesis,
        packet,
        {**policy, "compute": {"kind": "local_python", "script_path": "ablation.py"}},
    )

    assert baseline["protocol_id"] != changed_procedure["protocol_id"]
    assert baseline["protocol_id"] != changed_compute["protocol_id"]


@pytest.mark.parametrize(
    "result",
    [
        {"metrics": {"validation": []}},
        {"metrics": {"validation": [{"accuracy": "0.9"}]}},
        {"metrics": {"validation": [{"accuracy": True}]}},
    ],
)
def test_protocol_rejects_missing_or_non_numeric_metric(result) -> None:
    with pytest.raises(AutopilotValidationError):
        evaluate_experiment_result(_protocol(), result)


def test_parse_remote_result_marker_requires_one_json_object() -> None:
    parsed = parse_result_json_marker(
        "training complete\n  __RESULT_JSON__{\"metrics\": {\"accuracy\": 0.91}}\n"
    )
    assert parsed["metrics"]["accuracy"] == 0.91

    with pytest.raises(AutopilotValidationError, match="missing"):
        parse_result_json_marker("training complete")
    with pytest.raises(AutopilotValidationError, match="multiple"):
        parse_result_json_marker("__RESULT_JSON__{}\n__RESULT_JSON__{}")
    with pytest.raises(AutopilotValidationError, match="object"):
        parse_result_json_marker("__RESULT_JSON__[1, 2]")
