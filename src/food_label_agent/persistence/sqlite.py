"""SQLite persistence with capability tokens and explicit state serialization."""

from __future__ import annotations

import hmac
import json
import os
import secrets
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from food_label_agent.domain.models import (
    AuditEvent,
    Evidence,
    LabelField,
    RiskFinding,
    ToolTraceEvent,
    UserConstraint,
    WorkflowTraceEvent,
)
from food_label_agent.domain.types import (
    AnalysisStatus,
    ConstraintKind,
    RiskLevel,
    WorkflowStage,
)
from food_label_agent.graph.state import AgentState, create_initial_state

AGENT_STATE_SCHEMA_VERSION = 2


def default_database_path() -> Path:
    configured = os.getenv("FOOD_LABEL_DATA_DIR")
    base = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".local" / "share" / "food-label-health-agent"
    )
    return base / "agent-data.sqlite3"


@dataclass(frozen=True, slots=True)
class CheckpointReceipt:
    checkpoint_id: str
    request_id: str
    sequence: int
    status: str
    stage: str
    resume_token: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ConsentReceipt:
    consent_id: str
    profile_id: str
    purpose: str
    access_token: str
    granted_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SQLiteCheckpointStore:
    """Append-only, token-protected short-term AgentState checkpoints."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path = str(path)
        self._lock = threading.RLock()
        self._connection = _connect(self._path)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                token_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(request_id, sequence)
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_checkpoint_request "
            "ON workflow_checkpoints(request_id, sequence DESC)"
        )
        self._connection.commit()
        _protect_file(self._path)

    @property
    def path(self) -> str:
        """Return the configured database path without exposing its contents."""

        return self._path

    @property
    def durable(self) -> bool:
        return self._path != ":memory:"

    def healthcheck(self) -> bool:
        """Verify that the connection can read and, for files, the directory is writable."""

        with self._lock:
            self._connection.execute("SELECT 1").fetchone()
        if not self.durable:
            return True
        path = Path(self._path).expanduser()
        return path.exists() and os.access(path.parent, os.W_OK)

    def save(
        self, state: AgentState, *, resume_token: str | None = None
    ) -> CheckpointReceipt:
        request_id = state["request_id"]
        with self._lock:
            latest = self._connection.execute(
                "SELECT sequence, token_hash FROM workflow_checkpoints "
                "WHERE request_id = ? ORDER BY sequence DESC LIMIT 1",
                (request_id,),
            ).fetchone()
            issued_token: str | None = None
            if latest is None:
                token = secrets.token_urlsafe(32)
                issued_token = token
                sequence = 1
            else:
                if not resume_token or not _token_matches(
                    resume_token, latest["token_hash"]
                ):
                    raise PermissionError("A valid resume token is required")
                token = resume_token
                sequence = int(latest["sequence"]) + 1
            checkpoint_id = str(uuid4())
            created_at = _now()
            self._connection.execute(
                "INSERT INTO workflow_checkpoints VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    checkpoint_id,
                    request_id,
                    sequence,
                    _token_hash(token),
                    state["status"].value,
                    state["stage"].value,
                    json.dumps(
                        serialize_agent_state(state),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    created_at,
                ),
            )
            self._connection.commit()
        return CheckpointReceipt(
            checkpoint_id=checkpoint_id,
            request_id=request_id,
            sequence=sequence,
            status=state["status"].value,
            stage=state["stage"].value,
            resume_token=issued_token,
            created_at=created_at,
        )

    def load_latest(self, request_id: str, resume_token: str) -> AgentState:
        with self._lock:
            row = self._connection.execute(
                "SELECT token_hash, state_json FROM workflow_checkpoints "
                "WHERE request_id = ? ORDER BY sequence DESC LIMIT 1",
                (request_id,),
            ).fetchone()
        if row is None:
            raise KeyError(request_id)
        if not _token_matches(resume_token, row["token_hash"]):
            raise PermissionError("Invalid resume token")
        return deserialize_agent_state(json.loads(row["state_json"]))

    def history(self, request_id: str, resume_token: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT checkpoint_id, sequence, token_hash, status, stage, created_at "
                "FROM workflow_checkpoints WHERE request_id = ? ORDER BY sequence",
                (request_id,),
            ).fetchall()
        if not rows:
            raise KeyError(request_id)
        if not _token_matches(resume_token, rows[-1]["token_hash"]):
            raise PermissionError("Invalid resume token")
        return [
            {
                "checkpoint_id": row["checkpoint_id"],
                "sequence": row["sequence"],
                "status": row["status"],
                "stage": row["stage"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def delete(self, request_id: str, resume_token: str) -> int:
        self.load_latest(request_id, resume_token)
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM workflow_checkpoints WHERE request_id = ?", (request_id,)
            )
            self._connection.commit()
            return int(cursor.rowcount)


class SQLiteMemoryStore:
    """Long-term memory that is inaccessible until explicit consent is granted."""

    ALLOWED_KINDS = frozenset({"constraint", "response_preference", "label_correction"})

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path = str(path)
        self._lock = threading.RLock()
        self._connection = _connect(self._path)
        self._connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS memory_consents (
                consent_id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                purpose TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                granted_at TEXT NOT NULL,
                revoked_at TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_active_profile_consent
            ON memory_consents(profile_id) WHERE revoked_at IS NULL;
            CREATE TABLE IF NOT EXISTS memory_items (
                memory_id TEXT PRIMARY KEY,
                consent_id TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                value_json TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(consent_id) REFERENCES memory_consents(consent_id)
            );
            CREATE INDEX IF NOT EXISTS idx_memory_profile
            ON memory_items(profile_id, updated_at DESC);
            """
        )
        self._connection.commit()
        _protect_file(self._path)

    @property
    def path(self) -> str:
        return self._path

    @property
    def durable(self) -> bool:
        return self._path != ":memory:"

    def healthcheck(self) -> bool:
        with self._lock:
            self._connection.execute("SELECT 1").fetchone()
        if not self.durable:
            return True
        path = Path(self._path).expanduser()
        return path.exists() and os.access(path.parent, os.W_OK)

    def grant_consent(
        self, profile_id: str, purpose: str, *, explicit_consent: bool
    ) -> ConsentReceipt:
        profile_id = _validated_identifier(profile_id, "profile_id")
        purpose = purpose.strip()
        if not explicit_consent:
            raise PermissionError("Explicit consent is required")
        if not purpose or len(purpose) > 240:
            raise ValueError("A specific memory purpose is required")
        with self._lock:
            active = self._connection.execute(
                "SELECT 1 FROM memory_consents WHERE profile_id = ? AND revoked_at IS NULL",
                (profile_id,),
            ).fetchone()
            if active:
                raise ValueError("Active consent already exists; revoke it first")
            consent_id = str(uuid4())
            token = secrets.token_urlsafe(32)
            granted_at = _now()
            self._connection.execute(
                "INSERT INTO memory_consents VALUES (?, ?, ?, ?, ?, NULL)",
                (consent_id, profile_id, purpose, _token_hash(token), granted_at),
            )
            self._connection.commit()
        return ConsentReceipt(consent_id, profile_id, purpose, token, granted_at)

    def upsert_item(
        self,
        profile_id: str,
        access_token: str,
        *,
        kind: str,
        value: dict[str, Any],
        memory_id: str | None = None,
    ) -> dict[str, Any]:
        consent = self._authorize(profile_id, access_token)
        normalized = _validate_memory_value(kind, value)
        encoded = json.dumps(
            normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        now = _now()
        with self._lock:
            if memory_id:
                existing = self._connection.execute(
                    "SELECT created_at FROM memory_items "
                    "WHERE memory_id = ? AND profile_id = ? AND consent_id = ?",
                    (memory_id, profile_id, consent["consent_id"]),
                ).fetchone()
                if existing is None:
                    raise KeyError(memory_id)
                created_at = existing["created_at"]
                self._connection.execute(
                    "UPDATE memory_items SET kind = ?, value_json = ?, updated_at = ? "
                    "WHERE memory_id = ?",
                    (kind, encoded, now, memory_id),
                )
            else:
                memory_id = str(uuid4())
                created_at = now
                self._connection.execute(
                    "INSERT INTO memory_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        memory_id,
                        consent["consent_id"],
                        profile_id,
                        kind,
                        encoded,
                        "user_authorized",
                        created_at,
                        now,
                    ),
                )
            self._connection.commit()
        return {
            "memory_id": memory_id,
            "kind": kind,
            "value": normalized,
            "source": "user_authorized",
            "created_at": created_at,
            "updated_at": now,
            "revalidation_required": kind == "label_correction",
        }

    def list_items(self, profile_id: str, access_token: str) -> list[dict[str, Any]]:
        consent = self._authorize(profile_id, access_token)
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM memory_items WHERE profile_id = ? AND consent_id = ? "
                "ORDER BY updated_at DESC",
                (profile_id, consent["consent_id"]),
            ).fetchall()
        return [_memory_row(row) for row in rows]

    def delete_item(self, profile_id: str, access_token: str, memory_id: str) -> None:
        consent = self._authorize(profile_id, access_token)
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM memory_items "
                "WHERE memory_id = ? AND profile_id = ? AND consent_id = ?",
                (memory_id, profile_id, consent["consent_id"]),
            )
            self._connection.commit()
        if not cursor.rowcount:
            raise KeyError(memory_id)

    def revoke_consent(self, profile_id: str, access_token: str) -> int:
        consent = self._authorize(profile_id, access_token)
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM memory_items WHERE consent_id = ?",
                (consent["consent_id"],),
            )
            self._connection.execute(
                "UPDATE memory_consents SET revoked_at = ? WHERE consent_id = ?",
                (_now(), consent["consent_id"]),
            )
            self._connection.commit()
            return int(cursor.rowcount)

    def _authorize(self, profile_id: str, access_token: str) -> sqlite3.Row:
        profile_id = _validated_identifier(profile_id, "profile_id")
        with self._lock:
            row = self._connection.execute(
                "SELECT consent_id, token_hash FROM memory_consents "
                "WHERE profile_id = ? AND revoked_at IS NULL",
                (profile_id,),
            ).fetchone()
        if row is None or not _token_matches(access_token, row["token_hash"]):
            raise PermissionError(
                "Active consent and a valid access token are required"
            )
        return row


def serialize_agent_state(state: AgentState) -> dict[str, Any]:
    """Serialize AgentState without persisting original image data or private CoT."""

    return {
        "schema_version": AGENT_STATE_SCHEMA_VERSION,
        "request_id": state["request_id"],
        "jurisdiction": state["jurisdiction"],
        "applicable_date": state["applicable_date"],
        "status": state["status"].value,
        "stage": state["stage"].value,
        "images": [],
        "redactions": ["images"],
        "label_fields": {
            key: asdict(value) for key, value in state["label_fields"].items()
        },
        "ocr_evidence": state["ocr_evidence"],
        "normalized_label": state["normalized_label"],
        "user_constraints": [asdict(value) for value in state["user_constraints"]],
        "risk_findings": [asdict(value) for value in state["risk_findings"]],
        "regulatory_evidence": [
            asdict(value) for value in state["regulatory_evidence"]
        ],
        "ingredient_explanations": state["ingredient_explanations"],
        "claim_interpretations": state["claim_interpretations"],
        "consistency_findings": state["consistency_findings"],
        "alternative_request": state["alternative_request"],
        "alternatives": state["alternatives"],
        "alternative_comparison": state["alternative_comparison"],
        "warnings": state["warnings"],
        "unknowns": state["unknowns"],
        "errors": state["errors"],
        "audit_events": [asdict(value) for value in state["audit_events"]],
        "tool_trace": [asdict(value) for value in state["tool_trace"]],
        "workflow_trace": [asdict(value) for value in state["workflow_trace"]],
        "react_budget": state["react_budget"],
    }


def deserialize_agent_state(value: dict[str, Any]) -> AgentState:
    if value.get("schema_version") not in {1, AGENT_STATE_SCHEMA_VERSION}:
        raise ValueError("Unsupported AgentState checkpoint schema")
    state = create_initial_state(
        request_id=value["request_id"],
        jurisdiction=value["jurisdiction"],
        applicable_date=value["applicable_date"],
    )
    state.update(
        status=AnalysisStatus(value["status"]),
        stage=WorkflowStage(value["stage"]),
        images=[],
        label_fields={
            key: LabelField(
                **{
                    **item,
                    "bounding_box": tuple(item["bounding_box"])
                    if item.get("bounding_box")
                    else None,
                }
            )
            for key, item in value["label_fields"].items()
        },
        ocr_evidence=value["ocr_evidence"],
        normalized_label=value["normalized_label"],
        user_constraints=[
            UserConstraint(**{**item, "kind": ConstraintKind(item["kind"])})
            for item in value["user_constraints"]
        ],
        risk_findings=[
            RiskFinding(
                **{
                    **item,
                    "risk_level": RiskLevel(item["risk_level"]),
                    "evidence_ids": tuple(item.get("evidence_ids", ())),
                }
            )
            for item in value["risk_findings"]
        ],
        regulatory_evidence=[Evidence(**item) for item in value["regulatory_evidence"]],
        ingredient_explanations=value["ingredient_explanations"],
        claim_interpretations=value["claim_interpretations"],
        consistency_findings=value["consistency_findings"],
        alternative_request=value.get("alternative_request", {}),
        alternatives=value["alternatives"],
        alternative_comparison=value.get("alternative_comparison", {}),
        warnings=value["warnings"],
        unknowns=value["unknowns"],
        errors=value["errors"],
        audit_events=[AuditEvent(**item) for item in value["audit_events"]],
        tool_trace=[ToolTraceEvent(**item) for item in value["tool_trace"]],
        workflow_trace=[
            WorkflowTraceEvent(**item) for item in value.get("workflow_trace", [])
        ],
        react_budget=value["react_budget"],
    )
    return state


def _connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    if path != ":memory:":
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
    return connection


def _protect_file(path: str) -> None:
    if path != ":memory:" and Path(path).exists():
        Path(path).chmod(0o600)


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _token_hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def _token_matches(token: str, expected_hash: str) -> bool:
    return bool(token) and hmac.compare_digest(_token_hash(token), expected_hash)


def _validated_identifier(value: str, label: str) -> str:
    normalized = value.strip()
    if not 8 <= len(normalized) <= 128:
        raise ValueError(f"{label} must contain 8 to 128 characters")
    return normalized


def _validate_memory_value(kind: str, value: dict[str, Any]) -> dict[str, Any]:
    if kind not in SQLiteMemoryStore.ALLOWED_KINDS:
        raise ValueError("Unsupported memory kind")
    if not isinstance(value, dict):
        raise TypeError("Memory value must be an object")
    encoded = json.dumps(value, ensure_ascii=False)
    if len(encoded) > 4_096:
        raise ValueError("Memory item is too large")
    forbidden = {
        "chain_of_thought",
        "raw_messages",
        "conversation",
        "diagnosis",
        "health_inference",
        "image",
        "image_data",
    }
    if forbidden.intersection(value):
        raise ValueError("Memory contains a prohibited field")
    if kind == "constraint":
        if value.get("kind") not in {item.value for item in ConstraintKind}:
            raise ValueError("Memory constraint kind is invalid")
        if not str(value.get("canonical_value", "")).strip():
            raise ValueError("Memory constraint requires a canonical value")
        value = {**value, "source": "user_authorized_memory"}
    elif kind == "label_correction":
        if value.get("confirmed_by_user") is not True:
            raise ValueError("Label corrections must be confirmed by the user")
        value = {**value, "requires_current_label_recheck": True}
    return value


def _memory_row(row: sqlite3.Row) -> dict[str, Any]:
    kind = row["kind"]
    return {
        "memory_id": row["memory_id"],
        "kind": kind,
        "value": json.loads(row["value_json"]),
        "source": row["source"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "revalidation_required": kind == "label_correction",
    }
