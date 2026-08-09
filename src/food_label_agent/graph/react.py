"""Bounded, policy-driven ReAct loop over approved MCP business tools.

The policy chooses the next missing evidence operation. It records decision codes
and compact observations, never private chain-of-thought. Mandatory normalization,
safety evaluation, and the final safety gate remain outside this loop.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from food_label_agent.context.builder import build_node_context
from food_label_agent.domain.models import AuditEvent, ToolTraceEvent
from food_label_agent.domain.types import AnalysisStatus, RiskLevel, WorkflowStage
from food_label_agent.mcp.business_tools import MCPToolCallError, invoke_mcp_tool

from .nodes import (
    _additive_ingredients,
    _ingredient_for_finding,
    _nutrition_values,
    _regulatory_evidence,
    _risk_finding_payload,
)
from .routing import critical_fields_needing_confirmation
from .state import AgentState

APPROVED_REACT_TOOLS = frozenset(
    {
        "search_food_regulations",
        "explain_ingredient",
        "interpret_label_claim",
        "verify_label_consistency",
    }
)


@dataclass(frozen=True, slots=True)
class ReactDecision:
    action: str
    reason_code: str
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    trace_context: dict[str, Any] | None = None


def react_orchestrator(
    state: AgentState,
    *,
    max_steps: int | None = None,
    max_tool_calls: int | None = None,
) -> dict:
    """Run a bounded tool loop and return a LangGraph-compatible state update."""

    working = _copy_state(state)
    context = build_node_context(working, "react_orchestrator")
    working["audit_events"].append(
        AuditEvent(
            event_type="node_context_built",
            actor="context_builder:react_orchestrator",
            detail={
                "node_name": "react_orchestrator",
                "included_fields": list(context.included_fields),
                "excluded_fields": list(context.excluded_fields),
                "estimated_tokens": context.estimated_tokens,
                "token_budget": context.token_budget,
                "truncated": context.truncated,
                "budget_exceeded": context.budget_exceeded,
                "context_digest": context.digest,
            },
        )
    )
    configured = state.get("react_budget", {})
    step_limit = max_steps if max_steps is not None else configured.get("max_steps", 32)
    tool_limit = (
        max_tool_calls
        if max_tool_calls is not None
        else configured.get("max_tool_calls", 32)
    )
    if step_limit < 1 or tool_limit < 1:
        raise ValueError("ReAct budgets must be positive")

    prerequisite = _prerequisite_failure(working)
    if prerequisite:
        working["status"] = prerequisite[0]
        working["stage"] = prerequisite[1]
        working["unknowns"] = list(
            dict.fromkeys([*working["unknowns"], prerequisite[2]])
        )
        working["tool_trace"].append(
            ToolTraceEvent(
                step=1,
                action="stop",
                reason_code=prerequisite[2],
                tool_name=None,
                outcome="prerequisite_failed",
                status_before=state["status"].value,
                status_after=working["status"].value,
            )
        )
        return _react_update(working, step_limit, tool_limit, 0)

    calls_used = 0
    for step in range(1, step_limit + 1):
        decision = select_next_action(working)
        if decision.action == "stop":
            working["stage"] = WorkflowStage.REACT_ORCHESTRATION
            working["tool_trace"].append(
                ToolTraceEvent(
                    step=step,
                    action="stop",
                    reason_code=decision.reason_code,
                    tool_name=None,
                    outcome="completed",
                    status_before=working["status"].value,
                    status_after=working["status"].value,
                    observation=_observation(working),
                )
            )
            break
        if calls_used >= tool_limit:
            _block_for_budget(working, step, calls_used, "react_tool_budget_exhausted")
            break
        validate_react_decision(decision)
        status_before = working["status"].value
        try:
            result = invoke_mcp_tool(decision.tool_name or "", decision.arguments or {})
        except MCPToolCallError:
            working["status"] = AnalysisStatus.BLOCKED
            working["errors"].append(f"mcp_tool_failed:{decision.tool_name}")
            working["unknowns"] = list(
                dict.fromkeys(
                    [*working["unknowns"], f"{decision.tool_name}_unavailable"]
                )
            )
            working["tool_trace"].append(
                ToolTraceEvent(
                    step=step,
                    action=decision.action,
                    reason_code=decision.reason_code,
                    tool_name=decision.tool_name,
                    outcome="failed",
                    status_before=status_before,
                    status_after=working["status"].value,
                    observation=decision.trace_context or {},
                )
            )
            break
        calls_used += 1
        _apply_tool_result(working, decision, result)
        working["tool_trace"].append(
            ToolTraceEvent(
                step=step,
                action=decision.action,
                reason_code=decision.reason_code,
                tool_name=decision.tool_name,
                outcome="succeeded",
                status_before=status_before,
                status_after=working["status"].value,
                observation={
                    **(decision.trace_context or {}),
                    **_result_observation(decision, result),
                },
            )
        )
        working["audit_events"].append(
            AuditEvent(
                event_type="react_tool_called",
                actor=f"react:mcp:{decision.tool_name}",
                detail={
                    "step": step,
                    "reason_code": decision.reason_code,
                    "outcome": "succeeded",
                },
            )
        )
        if working["status"] is AnalysisStatus.BLOCKED:
            break
    else:
        _block_for_budget(
            working, step_limit, calls_used, "react_step_budget_exhausted"
        )

    working["audit_events"].append(
        AuditEvent(
            event_type="react_loop_finished",
            actor="orchestrator:constrained_react",
            detail={
                "tool_calls_used": calls_used,
                "max_tool_calls": tool_limit,
                "trace_event_count": len(working["tool_trace"]),
                "status": working["status"].value,
            },
        )
    )
    return _react_update(working, step_limit, tool_limit, calls_used)


def select_next_action(state: AgentState) -> ReactDecision:
    """Choose one approved tool from explicit missing-evidence conditions."""

    attempted = {item.reason_code for item in state["tool_trace"]}
    allergen_findings = [
        item
        for item in state["risk_findings"]
        if item.risk_level is not RiskLevel.COMPATIBLE
        and not item.reason_code.startswith(
            ("USER_NUTRITION_", "NUTRITION_", "NUTRIENT_")
        )
    ]
    additives = _additive_ingredients(state["normalized_label"])
    claim = state["label_fields"].get("label_claims")

    if (
        allergen_findings
        and not _has_standard(state, "GB 7718")
        and "RETRIEVE_ALLERGEN_RULES" not in attempted
    ):
        terms = [
            value
            for item in allergen_findings
            for value in (item.matched_text, item.constraint)
            if value
        ]
        return _search_decision(
            state,
            "RETRIEVE_ALLERGEN_RULES",
            " ".join([*terms, "食品标签 配料表 过敏原 致敏物质"]),
            ["allergen", "ingredient_labeling"],
        )
    if (
        additives
        and not _has_standard(state, "GB 2760")
        and "RETRIEVE_ADDITIVE_RULES" not in attempted
    ):
        terms = [
            item.get("canonical_name") or item.get("raw_name") for item in additives
        ]
        return _search_decision(
            state,
            "RETRIEVE_ADDITIVE_RULES",
            " ".join([*terms, "GB 2760-2024 食品添加剂使用标准"]),
            ["food_additive"],
        )
    if (
        claim
        and claim.raw_text.strip()
        and not _has_standard(state, "GB 28050")
        and "RETRIEVE_CLAIM_RULES" not in attempted
    ):
        return _search_decision(
            state,
            "RETRIEVE_CLAIM_RULES",
            f"{claim.raw_text} 无糖 低糖 糖含量 营养声称 表C.1",
            ["nutrition_claim"],
        )

    explained_ids = {
        evidence_id
        for item in state["ingredient_explanations"]
        for evidence_id in item.get("label_evidence_ids", [])
    }
    for finding in allergen_findings:
        if set(finding.evidence_ids).intersection(explained_ids):
            continue
        ingredient = _ingredient_for_finding(state["normalized_label"], finding)
        if ingredient is not None:
            return ReactDecision(
                action="explain_ingredient",
                reason_code=f"EXPLAIN_RISK:{ingredient['evidence_id']}",
                tool_name="explain_ingredient",
                arguments={
                    "ingredient": ingredient,
                    "risk_finding": _risk_finding_payload(finding),
                    "regulatory_evidence": [
                        asdict(item) for item in state["regulatory_evidence"]
                    ],
                    "jurisdiction": state["jurisdiction"],
                    "applicable_date": state["applicable_date"],
                },
                trace_context={"target_evidence_id": ingredient["evidence_id"]},
            )
    for ingredient in additives:
        if ingredient.get("evidence_id") in explained_ids:
            continue
        return ReactDecision(
            action="explain_ingredient",
            reason_code=f"EXPLAIN_ADDITIVE:{ingredient.get('evidence_id')}",
            tool_name="explain_ingredient",
            arguments={
                "ingredient": ingredient,
                "risk_finding": None,
                "regulatory_evidence": [
                    asdict(item) for item in state["regulatory_evidence"]
                ],
                "jurisdiction": state["jurisdiction"],
                "applicable_date": state["applicable_date"],
            },
            trace_context={"target_evidence_id": ingredient.get("evidence_id")},
        )

    if claim and claim.raw_text.strip() and not state["claim_interpretations"]:
        return ReactDecision(
            action="interpret_label_claim",
            reason_code="INTERPRET_CONFIRMED_CLAIMS",
            tool_name="interpret_label_claim",
            arguments={
                "claim_text": claim.raw_text,
                "regulatory_evidence": [
                    asdict(item) for item in state["regulatory_evidence"]
                ],
                "jurisdiction": state["jurisdiction"],
                "applicable_date": state["applicable_date"],
            },
            trace_context={"source_field": "label_claims"},
        )
    if state["claim_interpretations"] and not state["consistency_findings"]:
        ingredients = state["label_fields"].get("ingredients")
        return ReactDecision(
            action="verify_label_consistency",
            reason_code="VERIFY_CLAIM_AGAINST_FACTS",
            tool_name="verify_label_consistency",
            arguments={
                "claims": state["claim_interpretations"],
                "ingredients_text": ingredients.raw_text if ingredients else None,
                "nutrition_values": _nutrition_values(state),
                "regulatory_evidence": [
                    asdict(item) for item in state["regulatory_evidence"]
                ],
                "jurisdiction": state["jurisdiction"],
                "applicable_date": state["applicable_date"],
            },
            trace_context={"claim_count": len(state["claim_interpretations"])},
        )
    return ReactDecision(action="stop", reason_code="NO_REQUIRED_TOOL_REMAINS")


def validate_react_decision(decision: ReactDecision) -> None:
    if decision.tool_name not in APPROVED_REACT_TOOLS:
        raise ValueError(f"Tool is not approved for ReAct: {decision.tool_name}")
    if decision.action != decision.tool_name:
        raise ValueError("ReAct action must match its MCP tool name")


def _search_decision(
    state: AgentState, reason_code: str, query: str, topics: list[str]
) -> ReactDecision:
    return ReactDecision(
        action="search_food_regulations",
        reason_code=reason_code,
        tool_name="search_food_regulations",
        arguments={
            "query": query,
            "jurisdiction": state["jurisdiction"],
            "applicable_date": state["applicable_date"],
            "topics": topics,
            "limit": 5,
        },
        trace_context={"topics": topics},
    )


def _apply_tool_result(
    state: AgentState, decision: ReactDecision, result: dict
) -> None:
    if decision.tool_name == "search_food_regulations":
        existing = {item.source_id: item for item in state["regulatory_evidence"]}
        for item in result["results"]:
            evidence = _regulatory_evidence(item)
            existing[evidence.source_id] = evidence
        state["regulatory_evidence"] = list(existing.values())
        state["unknowns"] = list(
            dict.fromkeys([*state["unknowns"], *result.get("unknowns", [])])
        )
        state["stage"] = WorkflowStage.REGULATORY_RETRIEVAL
    elif decision.tool_name == "explain_ingredient":
        state["ingredient_explanations"] = [*state["ingredient_explanations"], result]
        state["unknowns"] = list(
            dict.fromkeys([*state["unknowns"], *result.get("unknowns", [])])
        )
        state["stage"] = WorkflowStage.INTERPRETATION
    elif decision.tool_name == "interpret_label_claim":
        state["claim_interpretations"] = result["claims"]
        state["unknowns"] = list(
            dict.fromkeys([*state["unknowns"], *result.get("unknowns", [])])
        )
        state["stage"] = WorkflowStage.CLAIM_INTERPRETATION
    elif decision.tool_name == "verify_label_consistency":
        state["consistency_findings"] = result["findings"]
        state["unknowns"] = list(
            dict.fromkeys([*state["unknowns"], *result.get("unknowns", [])])
        )
        state["stage"] = WorkflowStage.CONSISTENCY_VERIFICATION
    state["status"] = AnalysisStatus.IN_PROGRESS


def _result_observation(decision: ReactDecision, result: dict) -> dict[str, Any]:
    if decision.tool_name == "search_food_regulations":
        return {
            "result_count": len(result.get("results", [])),
            "status": result.get("status"),
        }
    if decision.tool_name == "explain_ingredient":
        return {
            "status": result.get("status"),
            "explanation_type": result.get("explanation_type"),
        }
    if decision.tool_name == "interpret_label_claim":
        return {
            "status": result.get("status"),
            "claim_count": len(result.get("claims", [])),
        }
    return {
        "status": result.get("status"),
        "finding_count": len(result.get("findings", [])),
    }


def _has_standard(state: AgentState, prefix: str) -> bool:
    return any(
        str(item.standard_number or "").startswith(prefix)
        for item in state["regulatory_evidence"]
    )


def _prerequisite_failure(
    state: AgentState,
) -> tuple[AnalysisStatus, WorkflowStage, str] | None:
    if critical_fields_needing_confirmation(state):
        return (
            AnalysisStatus.NEEDS_CONFIRMATION,
            WorkflowStage.HUMAN_CONFIRMATION,
            "react_requires_confirmed_label",
        )
    if not state["normalized_label"]:
        return (
            AnalysisStatus.BLOCKED,
            WorkflowStage.REACT_ORCHESTRATION,
            "react_requires_normalized_label",
        )
    if len(state["risk_findings"]) != len(state["user_constraints"]):
        return (
            AnalysisStatus.BLOCKED,
            WorkflowStage.REACT_ORCHESTRATION,
            "react_requires_safety_evaluation",
        )
    return None


def _block_for_budget(state: AgentState, step: int, calls_used: int, code: str) -> None:
    state["status"] = AnalysisStatus.BLOCKED
    state["stage"] = WorkflowStage.REACT_ORCHESTRATION
    state["errors"] = list(dict.fromkeys([*state["errors"], code]))
    state["tool_trace"].append(
        ToolTraceEvent(
            step=step,
            action="stop",
            reason_code=code,
            tool_name=None,
            outcome="budget_exhausted",
            status_before=AnalysisStatus.IN_PROGRESS.value,
            status_after=AnalysisStatus.BLOCKED.value,
            observation={"tool_calls_used": calls_used},
        )
    )


def _observation(state: AgentState) -> dict[str, int]:
    return {
        "regulatory_evidence_count": len(state["regulatory_evidence"]),
        "ingredient_explanation_count": len(state["ingredient_explanations"]),
        "claim_interpretation_count": len(state["claim_interpretations"]),
        "consistency_finding_count": len(state["consistency_findings"]),
    }


def _copy_state(state: AgentState) -> AgentState:
    copied = dict(state)
    for key in (
        "regulatory_evidence",
        "ingredient_explanations",
        "claim_interpretations",
        "consistency_findings",
        "warnings",
        "unknowns",
        "errors",
        "audit_events",
        "tool_trace",
    ):
        copied[key] = list(state[key])
    return copied  # type: ignore[return-value]


def _react_update(state: AgentState, max_steps: int, max_tools: int, used: int) -> dict:
    return {
        "status": state["status"],
        "stage": state["stage"],
        "regulatory_evidence": state["regulatory_evidence"],
        "ingredient_explanations": state["ingredient_explanations"],
        "claim_interpretations": state["claim_interpretations"],
        "consistency_findings": state["consistency_findings"],
        "warnings": state["warnings"],
        "unknowns": state["unknowns"],
        "errors": state["errors"],
        "audit_events": state["audit_events"],
        "tool_trace": state["tool_trace"],
        "react_budget": {
            "max_steps": max_steps,
            "max_tool_calls": max_tools,
            "tool_calls_used": used,
        },
    }
