"""Build minimal, budgeted context envelopes for individual graph nodes."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any

from food_label_agent.graph.state import AgentState


@dataclass(frozen=True, slots=True)
class NodeContext:
    node_name: str
    payload: dict[str, Any]
    included_fields: tuple[str, ...]
    excluded_fields: tuple[str, ...]
    estimated_tokens: int
    token_budget: int
    truncated: bool
    budget_exceeded: bool
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_ALLOWED_LAYERS: dict[str, tuple[str, ...]] = {
    "normalize_label": ("task", "confirmed_facts"),
    "evaluate_safety": ("task", "confirmed_facts", "user_constraints"),
    "react_orchestrator": (
        "task",
        "confirmed_facts",
        "user_constraints",
        "risk_findings",
        "retrieval_evidence",
    ),
    "final_safety_gate": (
        "task",
        "user_constraints",
        "risk_findings",
        "retrieval_evidence",
        "alternatives",
    ),
    "search_alternatives": ("task", "user_constraints", "alternative_request"),
    "revalidate_alternatives": (
        "task",
        "user_constraints",
        "alternative_request",
        "alternatives",
    ),
}

_ALL_LAYERS = frozenset(
    {
        "task",
        "confirmed_facts",
        "user_constraints",
        "risk_findings",
        "retrieval_evidence",
        "alternative_request",
        "alternatives",
    }
)


def build_node_context(
    state: AgentState,
    node_name: str,
    *,
    token_budget: int = 2_000,
) -> NodeContext:
    """Return only the context layers required by one safety workflow node."""

    if node_name not in _ALLOWED_LAYERS:
        raise ValueError(f"Unknown context profile: {node_name}")
    if token_budget < 64:
        raise ValueError("Context token budget must be at least 64")

    available = _layers(state)
    included = _ALLOWED_LAYERS[node_name]
    payload = {name: available[name] for name in included}
    payload, truncated = _fit_budget(payload, token_budget)
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return NodeContext(
        node_name=node_name,
        payload=payload,
        included_fields=included,
        excluded_fields=tuple(sorted(_ALL_LAYERS - set(included))),
        estimated_tokens=_estimate_tokens(canonical),
        token_budget=token_budget,
        truncated=truncated,
        budget_exceeded=_estimate_tokens(canonical) > token_budget,
        digest=sha256(canonical.encode()).hexdigest(),
    )


def _layers(state: AgentState) -> dict[str, Any]:
    confirmed_fields = {
        name: {
            "raw_text": field.raw_text,
            "confidence": field.confidence,
            "bounding_box": field.bounding_box,
        }
        for name, field in state["label_fields"].items()
        if field.confirmed_by_user
    }
    evidence = [
        {
            "source_id": item.source_id,
            "standard_number": item.standard_number,
            "section": item.section,
            "source_url": item.source_url,
            "effective_from": item.effective_from,
            "effective_to": item.effective_to,
            "authority_level": item.authority_level,
            "retrieval_score": item.retrieval_score,
            "retrieval_method": item.retrieval_method,
            "evidence_text": item.evidence_text,
        }
        for item in state["regulatory_evidence"]
    ]
    return {
        "task": {
            "request_id": state["request_id"],
            "jurisdiction": state["jurisdiction"],
            "applicable_date": state["applicable_date"],
            "stage": state["stage"].value,
            "unknowns": list(state["unknowns"]),
            "errors": list(state["errors"]),
        },
        "confirmed_facts": {
            "label_fields": confirmed_fields,
            "normalized_label": state["normalized_label"],
        },
        "user_constraints": [asdict(item) for item in state["user_constraints"]],
        "risk_findings": [asdict(item) for item in state["risk_findings"]],
        "retrieval_evidence": evidence,
        "alternative_request": state["alternative_request"],
        "alternatives": state["alternatives"],
    }


def _fit_budget(
    payload: dict[str, Any], token_budget: int
) -> tuple[dict[str, Any], bool]:
    fitted = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    if _payload_tokens(fitted) <= token_budget:
        return fitted, False

    truncated = False
    evidence = fitted.get("retrieval_evidence")
    if isinstance(evidence, list):
        while evidence and _payload_tokens(fitted) > token_budget:
            evidence.pop()
            truncated = True
    facts = fitted.get("confirmed_facts", {}).get("normalized_label", {})
    ingredients = facts.get("ingredients") if isinstance(facts, dict) else None
    if isinstance(ingredients, list):
        while ingredients and _payload_tokens(fitted) > token_budget:
            ingredients.pop()
            truncated = True
    task = fitted.get("task", {})
    for key in ("unknowns", "errors"):
        values = task.get(key)
        if isinstance(values, list):
            while len(values) > 1 and _payload_tokens(fitted) > token_budget:
                values.pop()
                truncated = True
    return fitted, truncated


def _payload_tokens(payload: dict[str, Any]) -> int:
    return _estimate_tokens(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _estimate_tokens(text: str) -> int:
    # Conservative approximation for mixed Chinese/Latin structured context.
    return max(1, (len(text) + 2) // 3)
