"""Privacy-preserving operational metrics for the conversation agent."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

CONVERSATION_METRIC_SCHEMA_VERSION = "conversation_metric_v1"


@dataclass(frozen=True, slots=True)
class ConversationMetric:
    outcome: str
    session_key: str
    model: str | None
    boundary: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    request_count: int = 0
    tool_events: tuple[dict[str, Any], ...] = ()
    trusted_label_attached: bool = False
    error_code: str | None = None
    retryable: bool = False
    event_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["schema_version"] = CONVERSATION_METRIC_SCHEMA_VERSION
        value["tool_events"] = [
            {
                "name": str(item.get("name") or "unknown")[:120],
                "status": str(item.get("status") or "unknown")[:80],
            }
            for item in self.tool_events
        ]
        return value


class ConversationObserver(Protocol):
    def record(self, metric: ConversationMetric) -> None: ...


class NullConversationObserver:
    def record(self, metric: ConversationMetric) -> None:
        del metric


class JsonlConversationObserver:
    """Append metrics without message text, label text, or raw session identifiers."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._lock = threading.RLock()

    def record(self, metric: ConversationMetric) -> None:
        payload = json.dumps(
            metric.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(payload + "\n")
            self.path.chmod(0o600)


def create_conversation_observer(
    source: dict[str, str] | None = None,
) -> ConversationObserver:
    values = source if source is not None else os.environ
    path = values.get("FOOD_LABEL_CHAT_METRICS_PATH", "").strip()
    return JsonlConversationObserver(path) if path else NullConversationObserver()


def anonymize_session_id(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
