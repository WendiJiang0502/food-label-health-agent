"""Short-lived, capability-protected storage for raw conversation turns.

Conversation history is deliberately separate from consented long-term memory.
Sessions expire automatically and are never treated as health-profile facts.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import sqlite3
import threading
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

FEEDBACK_REASONS = frozenset(
    {
        "misunderstood",
        "label_fact_error",
        "unclear",
        "risk_issue",
        "evidence_gap",
        "other",
    }
)


@dataclass(frozen=True, slots=True)
class ConversationSessionReceipt:
    session_id: str
    access_token: str
    created_at: str
    expires_at: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class SQLiteConversationStore:
    """Store an explicitly bounded conversation for at most one retention window."""

    def __init__(
        self, path: str | Path = ":memory:", *, retention_hours: int = 24
    ) -> None:
        if not 1 <= retention_hours <= 168:
            raise ValueError("Conversation retention must be between 1 and 168 hours")
        self._path = str(path)
        self.retention_hours = retention_hours
        self._lock = threading.RLock()
        if self._path != ":memory:":
            Path(self._path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self._path, check_same_thread=False, timeout=5.0
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._connection.execute("PRAGMA foreign_keys = ON")
        if self._path != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = NORMAL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversation_sessions (
                session_id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversation_messages (
                message_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES conversation_sessions(session_id)
                    ON DELETE CASCADE,
                UNIQUE(session_id, sequence)
            );
            CREATE INDEX IF NOT EXISTS idx_conversation_messages
            ON conversation_messages(session_id, sequence);
            CREATE TABLE IF NOT EXISTS conversation_states (
                session_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES conversation_sessions(session_id)
                    ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS conversation_feedback (
                feedback_id TEXT PRIMARY KEY,
                session_key TEXT NOT NULL,
                message_key TEXT NOT NULL UNIQUE,
                helpful INTEGER NOT NULL,
                reason TEXT,
                retry_requested INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conversation_feedback_created
            ON conversation_feedback(created_at);
            """
        )
        self._connection.commit()
        if self._path != ":memory:" and Path(self._path).exists():
            Path(self._path).chmod(0o600)

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

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __del__(self) -> None:
        with suppress(Exception):
            self.close()

    def create_session(self) -> ConversationSessionReceipt:
        session_id = str(uuid4())
        token = secrets.token_urlsafe(32)
        now = datetime.now().astimezone()
        expires_at = now + timedelta(hours=self.retention_hours)
        with self._lock:
            self._connection.execute(
                "INSERT INTO conversation_sessions VALUES (?, ?, ?, ?, ?)",
                (
                    session_id,
                    _token_hash(token),
                    now.isoformat(),
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            self._connection.commit()
        return ConversationSessionReceipt(
            session_id=session_id,
            access_token=token,
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
        )

    def append_message(
        self,
        session_id: str,
        access_token: str,
        *,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if role not in {"user", "assistant"}:
            raise ValueError("Conversation role must be user or assistant")
        content = content.strip()
        if not content or len(content) > 12_000:
            raise ValueError("Conversation message must contain 1 to 12000 characters")
        metadata = metadata or {}
        encoded_metadata = json.dumps(
            metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        if len(encoded_metadata) > 8_192:
            raise ValueError("Conversation metadata is too large")
        session = self._authorize(session_id, access_token)
        now = datetime.now().astimezone()
        expires_at = now + timedelta(hours=self.retention_hours)
        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) AS sequence "
                "FROM conversation_messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            sequence = int(row["sequence"]) + 1
            message_id = str(uuid4())
            self._connection.execute(
                "INSERT INTO conversation_messages VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    message_id,
                    session_id,
                    sequence,
                    role,
                    content,
                    encoded_metadata,
                    now.isoformat(),
                ),
            )
            self._connection.execute(
                "UPDATE conversation_sessions SET updated_at = ?, expires_at = ? "
                "WHERE session_id = ?",
                (now.isoformat(), expires_at.isoformat(), session["session_id"]),
            )
            self._connection.commit()
        return {
            "message_id": message_id,
            "sequence": sequence,
            "role": role,
            "content": content,
            "metadata": metadata,
            "created_at": now.isoformat(),
        }

    def messages(
        self, session_id: str, access_token: str, *, limit: int = 24
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("Conversation message limit must be between 1 and 100")
        self._authorize(session_id, access_token)
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM (SELECT message_id, sequence, role, content, "
                "metadata_json, created_at FROM conversation_messages "
                "WHERE session_id = ? ORDER BY sequence DESC LIMIT ?) "
                "ORDER BY sequence",
                (session_id, limit),
            ).fetchall()
        return [
            {
                "message_id": row["message_id"],
                "sequence": row["sequence"],
                "role": row["role"],
                "content": row["content"],
                "metadata": json.loads(row["metadata_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def session(self, session_id: str, access_token: str) -> dict[str, Any]:
        row = self._authorize(session_id, access_token)
        return {
            "session_id": row["session_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "expires_at": row["expires_at"],
            "messages": self.messages(session_id, access_token),
            "structured_state": self.structured_state(session_id, access_token),
            "feedback": self.feedback(session_id, access_token),
        }

    def structured_state(
        self, session_id: str, access_token: str
    ) -> dict[str, Any] | None:
        self._authorize(session_id, access_token)
        with self._lock:
            row = self._connection.execute(
                "SELECT state_json FROM conversation_states WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return json.loads(row["state_json"]) if row else None

    def save_structured_state(
        self,
        session_id: str,
        access_token: str,
        state: dict[str, Any],
    ) -> None:
        self._authorize(session_id, access_token)
        encoded = json.dumps(
            state, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        if len(encoded) > 64_000:
            raise ValueError("Conversation structured state is too large")
        now = datetime.now().astimezone().isoformat()
        with self._lock:
            self._connection.execute(
                "INSERT INTO conversation_states(session_id, state_json, updated_at) "
                "VALUES (?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET "
                "state_json = excluded.state_json, updated_at = excluded.updated_at",
                (session_id, encoded, now),
            )
            self._connection.commit()

    def record_feedback(
        self,
        session_id: str,
        access_token: str,
        *,
        message_id: str,
        helpful: bool,
        reason: str | None = None,
        retry_requested: bool = False,
    ) -> dict[str, Any]:
        """Persist categorical feedback without conversation or label text."""

        self._authorize(session_id, access_token)
        normalized_reason = str(reason or "").strip() or None
        if normalized_reason not in FEEDBACK_REASONS | {None}:
            raise ValueError("Unsupported conversation feedback reason")
        if not helpful and normalized_reason is None:
            raise ValueError("Negative feedback requires a reason")
        with self._lock:
            message = self._connection.execute(
                "SELECT role FROM conversation_messages "
                "WHERE session_id = ? AND message_id = ?",
                (session_id, str(message_id).strip()),
            ).fetchone()
        if message is None:
            raise KeyError(str(message_id))
        if message["role"] != "assistant":
            raise ValueError("Feedback can only target an assistant message")
        now = datetime.now().astimezone()
        expires_at = now + timedelta(days=30)
        session_key = _token_hash(session_id)[:24]
        message_key = _token_hash(message_id)[:24]
        feedback_id = str(uuid4())
        with self._lock:
            self._connection.execute(
                "INSERT INTO conversation_feedback "
                "(feedback_id, session_key, message_key, helpful, reason, "
                "retry_requested, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(message_key) DO UPDATE SET helpful = excluded.helpful, "
                "reason = excluded.reason, retry_requested = excluded.retry_requested, "
                "created_at = excluded.created_at, expires_at = excluded.expires_at",
                (
                    feedback_id,
                    session_key,
                    message_key,
                    int(helpful),
                    normalized_reason,
                    int(retry_requested),
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            self._connection.commit()
            saved = self._connection.execute(
                "SELECT feedback_id FROM conversation_feedback WHERE message_key = ?",
                (message_key,),
            ).fetchone()
        return {
            "feedback_id": saved["feedback_id"],
            "message_id": message_id,
            "helpful": helpful,
            "reason": normalized_reason,
            "retry_requested": retry_requested,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

    def feedback(self, session_id: str, access_token: str) -> list[dict[str, Any]]:
        self._authorize(session_id, access_token)
        self.purge_expired_feedback()
        session_key = _token_hash(session_id)[:24]
        message_ids = {
            _token_hash(row["message_id"])[:24]: row["message_id"]
            for row in self.messages(session_id, access_token)
            if row["role"] == "assistant"
        }
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM conversation_feedback WHERE session_key = ? "
                "ORDER BY created_at",
                (session_key,),
            ).fetchall()
        return [
            {
                "feedback_id": row["feedback_id"],
                "message_id": message_ids.get(row["message_key"]),
                "helpful": bool(row["helpful"]),
                "reason": row["reason"],
                "retry_requested": bool(row["retry_requested"]),
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
            }
            for row in rows
            if row["message_key"] in message_ids
        ]

    def feedback_summary(self) -> dict[str, Any]:
        """Return aggregate pilot metrics; never return message or session content."""

        self.purge_expired_feedback()
        with self._lock:
            rows = self._connection.execute(
                "SELECT helpful, reason, retry_requested, session_key "
                "FROM conversation_feedback"
            ).fetchall()
        total = len(rows)
        helpful_count = sum(bool(row["helpful"]) for row in rows)
        reason_counts = {
            reason: sum(row["reason"] == reason for row in rows)
            for reason in sorted(FEEDBACK_REASONS)
            if any(row["reason"] == reason for row in rows)
        }
        return {
            "feedback_count": total,
            "helpful_count": helpful_count,
            "helpful_rate": round(helpful_count / total, 4) if total else None,
            "negative_reason_counts": reason_counts,
            "retry_requested_count": sum(bool(row["retry_requested"]) for row in rows),
            "unique_session_count": len({row["session_key"] for row in rows}),
            "raw_conversation_stored": False,
            "retention_days": 30,
        }

    def delete(self, session_id: str, access_token: str) -> int:
        self._authorize(session_id, access_token)
        session_key = _token_hash(session_id)[:24]
        with self._lock:
            self._connection.execute(
                "DELETE FROM conversation_feedback WHERE session_key = ?",
                (session_key,),
            )
            cursor = self._connection.execute(
                "DELETE FROM conversation_sessions WHERE session_id = ?",
                (session_id,),
            )
            self._connection.commit()
            return int(cursor.rowcount)

    def purge_expired_feedback(self) -> int:
        now = datetime.now().astimezone().isoformat()
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM conversation_feedback WHERE expires_at < ?", (now,)
            )
            self._connection.commit()
            return int(cursor.rowcount)

    def purge_expired(self) -> int:
        now = datetime.now().astimezone().isoformat()
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM conversation_sessions WHERE expires_at < ?", (now,)
            )
            self._connection.commit()
            return int(cursor.rowcount)

    def _authorize(self, session_id: str, access_token: str) -> sqlite3.Row:
        normalized = str(session_id).strip()
        if not normalized or len(normalized) > 128:
            raise ValueError("Invalid conversation session ID")
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM conversation_sessions WHERE session_id = ?",
                (normalized,),
            ).fetchone()
        if row is None:
            raise KeyError(normalized)
        if datetime.fromisoformat(row["expires_at"]) < datetime.now().astimezone():
            with self._lock:
                self._connection.execute(
                    "DELETE FROM conversation_sessions WHERE session_id = ?",
                    (normalized,),
                )
                self._connection.commit()
            raise KeyError(normalized)
        if not hmac.compare_digest(_token_hash(access_token), row["token_hash"]):
            raise PermissionError("Invalid conversation access token")
        return row


def _token_hash(token: str) -> str:
    return sha256(str(token).encode()).hexdigest()
