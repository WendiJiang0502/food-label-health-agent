from __future__ import annotations

from food_label_agent.evaluation.pilot import (
    evaluate_pilot_readiness,
    load_pilot_tasks,
)


def _conversation_report() -> dict:
    return {
        "evaluation_passed": True,
        "safety_metrics": {
            "hard_risk_downgrade_count": 0,
            "unconfirmed_fact_leak_count": 0,
            "unauthorized_tool_execution_count": 0,
            "prompt_injection_breakthrough_count": 0,
            "emergency_recall": 1.0,
            "tool_failure_fabrication_count": 0,
            "evidence_grounding_rate": 1.0,
        },
    }


def test_m9_system_can_be_ready_without_faking_human_validation() -> None:
    report = evaluate_pilot_readiness(
        conversation_report=_conversation_report(),
        feedback_summary={"raw_conversation_stored": False, "feedback_count": 0},
    )

    assert report["ready_for_closed_pilot"] is True
    assert report["pilot_outcome_validated"] is False
    assert report["status"] == "ready_for_closed_pilot"
    assert report["release_blockers"] == ["human_closed_pilot_not_run"]
    assert len(load_pilot_tasks()) == 12


def test_m9_rejects_synthetic_or_under_threshold_human_claims() -> None:
    report = evaluate_pilot_readiness(
        conversation_report=_conversation_report(),
        feedback_summary={"raw_conversation_stored": False},
        human_results={
            "evidence_type": "synthetic",
            "review_attested": True,
            "participant_count": 20,
            "completed_task_count": 200,
            "task_completion_rate": 1.0,
            "helpful_rate": 1.0,
            "severe_safety_incident_count": 0,
            "first_token_p95_ms": 500,
            "complete_latency_p95_ms": 2000,
        },
    )

    assert report["ready_for_closed_pilot"] is True
    assert report["pilot_outcome_validated"] is False
    assert "attested_human_evidence" in report["release_blockers"]


def test_m9_accepts_attested_human_results_at_all_thresholds() -> None:
    report = evaluate_pilot_readiness(
        conversation_report=_conversation_report(),
        feedback_summary={"raw_conversation_stored": False},
        human_results={
            "evidence_type": "human_closed_pilot",
            "review_attested": True,
            "participant_count": 10,
            "completed_task_count": 100,
            "task_completion_rate": 0.85,
            "helpful_rate": 0.80,
            "severe_safety_incident_count": 0,
            "first_token_p95_ms": 1500,
            "complete_latency_p95_ms": 7000,
        },
    )

    assert report["status"] == "pilot_validated"
    assert report["pilot_outcome_validated"] is True
    assert report["release_blockers"] == []
