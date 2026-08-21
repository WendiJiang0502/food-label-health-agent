"""Stable, JSON-serializable trace schema shared by all evaluation lanes."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from statistics import mean
from typing import Any


TRACE_SCHEMA_VERSION = "food_label_trace_v1"


@dataclass
class TraceSpan:
    name: str
    started_at: float
    ended_at: float | None = None
    status: str = "running"
    metadata: dict[str, Any] = field(default_factory=dict)

    def finish(self, *, status: str = "completed", **metadata: Any) -> None:
        self.ended_at = time.perf_counter()
        self.status = status
        self.metadata.update(metadata)

    def to_dict(self) -> dict[str, Any]:
        duration = None if self.ended_at is None else round((self.ended_at - self.started_at) * 1000, 3)
        return {"name": self.name, "status": self.status, "duration_ms": duration, "metadata": self.metadata}


@dataclass
class RunTrace:
    run_id: str
    lane: str
    case_id: str
    started_at: float = field(default_factory=time.perf_counter)
    ended_at: float | None = None
    status: str = "running"
    spans: list[TraceSpan] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    token_usage: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0, "total": 0})
    cost_usd: float = 0.0
    outcome: dict[str, Any] = field(default_factory=dict)

    def span(self, name: str) -> TraceSpan:
        value = TraceSpan(name=name, started_at=time.perf_counter())
        self.spans.append(value)
        return value

    def increment(self, name: str, amount: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + amount

    def finish(self, *, status: str, outcome: dict[str, Any] | None = None) -> None:
        self.ended_at = time.perf_counter()
        self.status = status
        if outcome:
            self.outcome.update(outcome)

    def to_dict(self) -> dict[str, Any]:
        duration = None if self.ended_at is None else round((self.ended_at - self.started_at) * 1000, 3)
        return {
            "schema_version": TRACE_SCHEMA_VERSION,
            "run_id": self.run_id,
            "lane": self.lane,
            "case_id": self.case_id,
            "status": self.status,
            "duration_ms": duration,
            "spans": [item.to_dict() for item in self.spans],
            "counters": self.counters,
            "token_usage": self.token_usage,
            "cost_usd": round(self.cost_usd, 8),
            "outcome": self.outcome,
        }


def aggregate_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    durations = sorted(float(item["duration_ms"]) for item in traces if item.get("duration_ms") is not None)
    p95_index = max(0, min(len(durations) - 1, int((len(durations) * 0.95 + 0.999999)) - 1)) if durations else 0
    total_cost = sum(float(item.get("cost_usd", 0.0)) for item in traces)
    total_tokens = sum(int(item.get("token_usage", {}).get("total", 0)) for item in traces)
    return {
        "run_count": len(traces),
        "average_latency_ms": round(mean(durations), 3) if durations else 0.0,
        "p95_latency_ms": round(durations[p95_index], 3) if durations else 0.0,
        "total_cost_usd": round(total_cost, 8),
        "average_cost_usd": round(total_cost / len(traces), 8) if traces else 0.0,
        "total_tokens": total_tokens,
        "cost_rates": {
            "input_usd_per_1k": float(os.getenv("FOOD_LABEL_INPUT_USD_PER_1K", "0")),
            "output_usd_per_1k": float(os.getenv("FOOD_LABEL_OUTPUT_USD_PER_1K", "0")),
        },
    }
