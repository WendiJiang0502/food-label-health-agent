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
from .planner import (
    ActionProposer,
    ModelPlannerError,
    PlannerProposal,
    create_action_proposer,
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


@dataclass(frozen=True, slots=True)
class PlannerSelection:
    decision: ReactDecision
    mode: str
    outcome: str
    candidate_count: int
    provider: str | None = None
    model: str | None = None
    response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_code: str | None = None

    def observation(self) -> dict[str, Any]:
        return {
            "planner_mode": self.mode,
            "planner_outcome": self.outcome,
            "planner_candidate_count": self.candidate_count,
            **({"planner_provider": self.provider} if self.provider else {}),
            **({"planner_model": self.model} if self.model else {}),
            **({"planner_response_id": self.response_id} if self.response_id else {}),
            **(
                {"planner_input_tokens": self.input_tokens}
                if self.input_tokens is not None
                else {}
            ),
            **(
                {"planner_output_tokens": self.output_tokens}
                if self.output_tokens is not None
                else {}
            ),
            **({"planner_error_code": self.error_code} if self.error_code else {}),
        }


_PLANNER_FROM_ENVIRONMENT = object()


def react_orchestrator(
    state: AgentState,
    *,
    max_steps: int | None = None,
    max_tool_calls: int | None = None,
    action_proposer: ActionProposer | None | object = _PLANNER_FROM_ENVIRONMENT,
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
    proposer = (
        create_action_proposer()
        if action_proposer is _PLANNER_FROM_ENVIRONMENT
        else action_proposer
    )

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
        selection = choose_next_action(working, action_proposer=proposer)
        decision = selection.decision
        _record_planner_selection(working, step, selection)
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
                    observation={
                        **selection.observation(),
                        **_observation(working),
                    },
                )
            )
            break
        if calls_used >= tool_limit:
            _block_for_budget(working, step, calls_used, "react_tool_budget_exhausted")
            break
        validate_react_decision(decision)
        status_before = working["status"].value
        result = None
        recovered = False
        for attempt in (1, 2):
            if calls_used >= tool_limit:
                break
            calls_used += 1
            try:
                result = invoke_mcp_tool(
                    decision.tool_name or "", decision.arguments or {}
                )
                recovered = attempt == 2
                break
            except MCPToolCallError:
                if attempt == 1 and calls_used < tool_limit:
                    working["tool_trace"].append(
                        ToolTraceEvent(
                            step=step,
                            action=decision.action,
                            reason_code=decision.reason_code,
                            tool_name=decision.tool_name,
                            outcome="retry_scheduled",
                            status_before=status_before,
                            status_after=working["status"].value,
                            observation={
                                **selection.observation(),
                                **(decision.trace_context or {}),
                                "attempt": attempt,
                            },
                        )
                    )
                    working["audit_events"].append(
                        AuditEvent(
                            event_type="react_tool_retry_scheduled",
                            actor=f"react:mcp:{decision.tool_name}",
                            detail={"step": step, "attempt": attempt},
                        )
                    )
                    continue
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
                        observation={
                            **selection.observation(),
                            **(decision.trace_context or {}),
                            "attempt": attempt,
                        },
                    )
                )
                break
        if result is None:
            if working["status"] is not AnalysisStatus.BLOCKED:
                _block_for_budget(
                    working, step, calls_used, "react_tool_budget_exhausted"
                )
            break
        _apply_tool_result(working, decision, result)
        working["tool_trace"].append(
            ToolTraceEvent(
                step=step,
                action=decision.action,
                reason_code=decision.reason_code,
                tool_name=decision.tool_name,
                outcome="recovered" if recovered else "succeeded",
                status_before=status_before,
                status_after=working["status"].value,
                observation={
                    **selection.observation(),
                    **(decision.trace_context or {}),
                    **_result_observation(decision, result),
                    "attempt": 2 if recovered else 1,
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
                    "outcome": "recovered" if recovered else "succeeded",
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


def candidate_actions(state: AgentState) -> tuple[ReactDecision, ...]:
    """Build the complete legal action set for the current evidence phase."""

    retrievals: list[ReactDecision] = []
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
        retrievals.append(
            _search_decision(
                state,
                "RETRIEVE_ALLERGEN_RULES",
                " ".join([*terms, "食品标签 配料表 过敏原 致敏物质"]),
                ["allergen", "ingredient_labeling"],
            )
        )
    if (
        additives
        and not _has_standard(state, "GB 2760")
        and "RETRIEVE_ADDITIVE_RULES" not in attempted
    ):
        terms = [
            item.get("canonical_name") or item.get("raw_name") for item in additives
        ]
        retrievals.append(
            _search_decision(
                state,
                "RETRIEVE_ADDITIVE_RULES",
                " ".join([*terms, "GB 2760-2024 食品添加剂使用标准"]),
                ["food_additive"],
            )
        )
    if (
        claim
        and claim.raw_text.strip()
        and not _has_standard(state, "GB 28050")
        and "RETRIEVE_CLAIM_RULES" not in attempted
    ):
        retrievals.append(
            _search_decision(
                state,
                "RETRIEVE_CLAIM_RULES",
                f"{claim.raw_text} 无糖 低糖 糖含量 营养声称 表C.1",
                ["nutrition_claim"],
            )
        )
    if retrievals:
        return tuple(retrievals)

    explanations: list[ReactDecision] = []
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
            explanations.append(
                ReactDecision(
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
            )
    for ingredient in additives:
        if ingredient.get("evidence_id") in explained_ids:
            continue
        explanations.append(
            ReactDecision(
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
        )
    if explanations:
        return tuple(explanations)

    if claim and claim.raw_text.strip() and not state["claim_interpretations"]:
        return (
            ReactDecision(
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
            ),
        )
    if state["claim_interpretations"] and not state["consistency_findings"]:
        ingredients = state["label_fields"].get("ingredients")
        return (
            ReactDecision(
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
            ),
        )
    return ()


def select_next_action(state: AgentState) -> ReactDecision:
    """Deterministic baseline: select the first policy-generated candidate."""

    candidates = candidate_actions(state)
    return candidates[0] if candidates else _stop_decision()


def choose_next_action(
    state: AgentState,
    *,
    action_proposer: ActionProposer | None,
) -> PlannerSelection:
    """Resolve a model proposal to a legal system-owned action or safe fallback."""

    candidates = candidate_actions(state)
    if not candidates:
        return PlannerSelection(
            decision=_stop_decision(),
            mode="policy",
            outcome="no_legal_action_remains",
            candidate_count=0,
        )
    if action_proposer is None:
        return PlannerSelection(
            decision=candidates[0],
            mode="deterministic",
            outcome="selected",
            candidate_count=len(candidates),
        )
    summaries = [_candidate_summary(item) for item in candidates]
    try:
        proposal = action_proposer.propose(
            context=build_node_context(state, "react_orchestrator").payload,
            candidates=summaries,
        )
        decision = next(
            (item for item in candidates if item.reason_code == proposal.action_id),
            None,
        )
        if decision is None:
            return _fallback_selection(
                candidates,
                action_proposer,
                error_code="planner_proposed_non_candidate_action",
                proposal=proposal,
            )
        validate_react_decision(decision)
        return PlannerSelection(
            decision=decision,
            mode="model_guarded",
            outcome="accepted",
            candidate_count=len(candidates),
            provider=proposal.provider,
            model=proposal.model,
            response_id=proposal.response_id,
            input_tokens=proposal.input_tokens,
            output_tokens=proposal.output_tokens,
        )
    except (ModelPlannerError, ValueError) as exc:
        return _fallback_selection(
            candidates,
            action_proposer,
            error_code=(
                exc.code
                if isinstance(exc, ModelPlannerError)
                else "planner_policy_rejected"
            ),
        )


def validate_react_decision(decision: ReactDecision) -> None:
    if decision.tool_name not in APPROVED_REACT_TOOLS:
        raise ValueError(f"Tool is not approved for ReAct: {decision.tool_name}")
    if decision.action != decision.tool_name:
        raise ValueError("ReAct action must match its MCP tool name")


def _candidate_summary(decision: ReactDecision) -> dict[str, str]:
    return {
        "action_id": decision.reason_code,
        "tool_name": decision.tool_name or "stop",
        "purpose": _action_purpose(decision.reason_code),
    }


def _action_purpose(reason_code: str) -> str:
    if reason_code.startswith("RETRIEVE_"):
        return "retrieve currently applicable official evidence"
    if reason_code.startswith("EXPLAIN_RISK:"):
        return "explain a confirmed hard-constraint risk using label and regulation evidence"
    if reason_code.startswith("EXPLAIN_ADDITIVE:"):
        return (
            "explain a confirmed additive without inferring compliance or health impact"
        )
    if reason_code == "INTERPRET_CONFIRMED_CLAIMS":
        return "interpret a confirmed package claim against applicable evidence"
    return "verify consistency between confirmed label facts and interpreted claims"


def _fallback_selection(
    candidates: tuple[ReactDecision, ...],
    proposer: ActionProposer,
    *,
    error_code: str,
    proposal: PlannerProposal | None = None,
) -> PlannerSelection:
    return PlannerSelection(
        decision=candidates[0],
        mode="model_guarded",
        outcome="deterministic_fallback",
        candidate_count=len(candidates),
        provider=getattr(proposer, "provider", "unknown"),
        model=getattr(proposer, "model", "unknown"),
        response_id=proposal.response_id if proposal else None,
        input_tokens=proposal.input_tokens if proposal else None,
        output_tokens=proposal.output_tokens if proposal else None,
        error_code=error_code,
    )


def _record_planner_selection(
    state: AgentState, step: int, selection: PlannerSelection
) -> None:
    state["audit_events"].append(
        AuditEvent(
            event_type=(
                "planner_proposal_fallback"
                if selection.outcome == "deterministic_fallback"
                else "planner_action_selected"
            ),
            actor=f"planner:{selection.provider or selection.mode}",
            detail={
                "step": step,
                "mode": selection.mode,
                "outcome": selection.outcome,
                "candidate_count": selection.candidate_count,
                "selected_action_id": selection.decision.reason_code,
                **({"model": selection.model} if selection.model else {}),
                **(
                    {"error_code": selection.error_code} if selection.error_code else {}
                ),
                **(
                    {"planner_response_id": selection.response_id}
                    if selection.response_id
                    else {}
                ),
                **(
                    {"input_tokens": selection.input_tokens}
                    if selection.input_tokens is not None
                    else {}
                ),
                **(
                    {"output_tokens": selection.output_tokens}
                    if selection.output_tokens is not None
                    else {}
                ),
            },
        )
    )


def _stop_decision() -> ReactDecision:
    return ReactDecision(action="stop", reason_code="NO_REQUIRED_TOOL_REMAINS")


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
