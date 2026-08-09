from __future__ import annotations

from pathlib import Path

from food_label_agent.domain.models import (
    Evidence,
    ImageInput,
    LabelField,
    RiskFinding,
    UserConstraint,
)
from food_label_agent.domain.types import (
    AnalysisStatus,
    ConstraintKind,
    RiskLevel,
    WorkflowStage,
)
from food_label_agent.graph.state import create_initial_state
from food_label_agent.persistence.sqlite import (
    SQLiteCheckpointStore,
    SQLiteMemoryStore,
    deserialize_agent_state,
    serialize_agent_state,
)


def _completed_state():
    state = create_initial_state(
        request_id="checkpoint-request",
        jurisdiction="CN",
        applicable_date="2026-08-10",
        images=[ImageInput(uri="memory://private-label.jpg", side="ingredients")],
        user_constraints=[
            UserConstraint(
                kind=ConstraintKind.ALLERGY,
                canonical_value="milk",
                severity="severe",
            )
        ],
    )
    state["label_fields"] = {
        "ingredients": LabelField(
            name="ingredients",
            raw_text="乳清蛋白",
            confidence=1.0,
            confirmed_by_user=True,
            bounding_box=(10, 20, 300, 80),
        )
    }
    state["risk_findings"] = [
        RiskFinding(
            risk_level=RiskLevel.AVOID,
            constraint="milk",
            matched_text="乳清蛋白",
            reason_code="DIRECT_ALLERGEN_DERIVATIVE",
            explanation="命中乳来源成分。",
            evidence_ids=("label.ingredients.item.1",),
        )
    ]
    state["regulatory_evidence"] = [
        Evidence(
            source_id="reg-1",
            title="预包装食品标签通则",
            jurisdiction="CN",
            standard_number="GB 7718-2011",
        )
    ]
    state["status"] = AnalysisStatus.COMPLETED
    state["stage"] = WorkflowStage.COMPLETED
    return state


def test_agent_state_codec_redacts_images_and_restores_typed_values() -> None:
    serialized = serialize_agent_state(_completed_state())
    restored = deserialize_agent_state(serialized)

    assert serialized["images"] == []
    assert serialized["redactions"] == ["images"]
    assert "private-label.jpg" not in str(serialized)
    assert restored["status"] is AnalysisStatus.COMPLETED
    assert restored["stage"] is WorkflowStage.COMPLETED
    assert restored["images"] == []
    assert restored["label_fields"]["ingredients"].bounding_box == (10, 20, 300, 80)
    assert restored["user_constraints"][0].kind is ConstraintKind.ALLERGY
    assert restored["risk_findings"][0].risk_level is RiskLevel.AVOID


def test_checkpoint_store_resumes_appends_and_deletes_with_capability_token(
    tmp_path: Path,
) -> None:
    database = tmp_path / "agent.sqlite3"
    store = SQLiteCheckpointStore(database)
    state = _completed_state()

    first = store.save(state)
    assert first.sequence == 1
    assert first.resume_token
    restored = store.load_latest(state["request_id"], first.resume_token)
    assert restored["risk_findings"][0].risk_level is RiskLevel.AVOID

    second = store.save(state, resume_token=first.resume_token)
    assert second.sequence == 2
    assert second.resume_token is None
    assert len(store.history(state["request_id"], first.resume_token)) == 2
    assert database.stat().st_mode & 0o777 == 0o600

    for operation in (
        lambda: store.load_latest(state["request_id"], "wrong-token"),
        lambda: store.save(state),
    ):
        try:
            operation()
        except PermissionError:
            pass
        else:
            raise AssertionError("checkpoint access without the token was accepted")

    assert store.delete(state["request_id"], first.resume_token) == 2
    try:
        store.load_latest(state["request_id"], first.resume_token)
    except KeyError:
        pass
    else:
        raise AssertionError("deleted checkpoint remained accessible")


def test_memory_requires_consent_and_supports_view_modify_delete_revoke(
    tmp_path: Path,
) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    profile_id = "profile-12345678"

    try:
        store.grant_consent(profile_id, "保存过敏约束", explicit_consent=False)
    except PermissionError:
        pass
    else:
        raise AssertionError("memory consent was silently inferred")

    consent = store.grant_consent(
        profile_id, "跨会话保存用户明确声明的食品约束", explicit_consent=True
    )
    item = store.upsert_item(
        profile_id,
        consent.access_token,
        kind="constraint",
        value={
            "kind": "allergy",
            "canonical_value": "milk",
            "severity": "severe",
        },
    )
    assert item["value"]["source"] == "user_authorized_memory"
    assert store.list_items(profile_id, consent.access_token) == [item]

    updated = store.upsert_item(
        profile_id,
        consent.access_token,
        kind="constraint",
        memory_id=item["memory_id"],
        value={
            "kind": "allergy",
            "canonical_value": "milk",
            "severity": "moderate",
        },
    )
    assert updated["value"]["severity"] == "moderate"
    store.delete_item(profile_id, consent.access_token, item["memory_id"])
    assert store.list_items(profile_id, consent.access_token) == []

    store.upsert_item(
        profile_id,
        consent.access_token,
        kind="response_preference",
        value={"answer_style": "concise"},
    )
    assert store.revoke_consent(profile_id, consent.access_token) == 1
    try:
        store.list_items(profile_id, consent.access_token)
    except PermissionError:
        pass
    else:
        raise AssertionError("revoked memory consent remained active")


def test_memory_rejects_unconfirmed_or_private_inference_fields(tmp_path: Path) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    consent = store.grant_consent(
        "profile-private-test",
        "保存用户确认的标签修正",
        explicit_consent=True,
    )

    invalid = (
        ("label_correction", {"field": "ingredients", "confirmed_by_user": False}),
        ("response_preference", {"chain_of_thought": "private reasoning"}),
        ("constraint", {"kind": "diagnosis", "canonical_value": "unknown"}),
    )
    for kind, value in invalid:
        try:
            store.upsert_item(
                consent.profile_id,
                consent.access_token,
                kind=kind,
                value=value,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("prohibited long-term memory was accepted")
