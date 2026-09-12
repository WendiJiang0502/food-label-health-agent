"""Resumable workflow operations shared by HTTP and other entrypoints."""

from __future__ import annotations

from dataclasses import asdict

from food_label_agent.alternatives.models import AlternativeWorkflowRequest
from food_label_agent.domain.models import LabelField, UserConstraint
from food_label_agent.domain.types import AnalysisStatus, ConstraintKind, RiskLevel
from food_label_agent.evaluation.agent import evaluate_workflow_release
from food_label_agent.ingredients.api_models import (
    SafetyEvaluationRequest,
    SafetyEvaluationResponse,
)

from .nodes import _additive_ingredients
from .runtime import run_agent_graph
from .state import AgentState, create_initial_state


def attach_regulatory_interpretation(
    request: SafetyEvaluationRequest,
    evaluation: SafetyEvaluationResponse,
) -> dict:
    evidence, _ = run_regulatory_workflow(request, evaluation)
    return evidence


def prepare_evaluation_state(
    request: SafetyEvaluationRequest, *, state: AgentState | None = None
) -> AgentState:
    """Apply confirmed facts and constraints to a new or resumed canonical state."""

    working = state or create_initial_state(
        request_id=request.request_id,
        jurisdiction=request.jurisdiction,
        applicable_date=request.applicable_date,
    )
    if working["request_id"] != request.request_id:
        raise ValueError("恢复会话与当前 request_id 不一致")
    working["jurisdiction"] = request.jurisdiction
    working["applicable_date"] = request.applicable_date
    working["label_fields"] = {
        name: LabelField(
            name=name,
            raw_text=value,
            confidence=1.0,
            confirmed_by_user=True,
            bounding_box=(
                working["label_fields"][name].bounding_box
                if name in working["label_fields"]
                else None
            ),
        )
        for name, value in request.confirmed_fields.items()
    }
    working["ocr_evidence"] = {
        **working["ocr_evidence"],
        "status": "confirmed",
    }
    working["user_constraints"] = [_constraint(item) for item in request.constraints]
    working["status"] = AnalysisStatus.IN_PROGRESS
    _clear_retriable_failures(working)
    return working


def run_regulatory_workflow(
    request: SafetyEvaluationRequest,
    evaluation: SafetyEvaluationResponse | None = None,
    *,
    state: AgentState | None = None,
) -> tuple[dict, AgentState]:
    """Run normalization, deterministic safety, ReAct evidence and final gate."""

    final_state = run_agent_graph(prepare_evaluation_state(request, state=state))
    return evidence_payload(final_state), final_state


def run_alternative_workflow(
    request: AlternativeWorkflowRequest,
    *,
    state: AgentState | None = None,
) -> tuple[dict, AgentState]:
    """Resume the same state and independently revalidate product candidates."""

    safety_request = SafetyEvaluationRequest(
        request_id=request.request_id,
        jurisdiction=request.jurisdiction,
        applicable_date=request.applicable_date.isoformat(),
        confirmed_fields=request.confirmed_fields,
        nutrition_rows=request.nutrition_rows,
        constraints=request.constraints,
        resume_token=request.resume_token,
    )
    working = prepare_evaluation_state(safety_request, state=state)
    working["alternative_request"] = {
        "enabled": True,
        "category": request.category,
        "substitute_categories": request.substitute_categories,
        "region": request.region,
        "exclude_product_ids": (
            [request.current_product_id] if request.current_product_id else []
        ),
        "current_product_name": request.confirmed_fields.get("product_name"),
        "health_concerns": request.health_concerns,
        "current_nutrition_rows": request.nutrition_rows,
        "limit": 50,
        "display_limit": 8,
    }
    final_state = run_agent_graph(working)
    return alternative_payload(final_state, request.category), final_state


def evidence_payload(state: AgentState) -> dict:
    has_additives = bool(_additive_ingredients(state["normalized_label"]))
    needs_explanation = has_additives or any(
        finding.risk_level is not RiskLevel.COMPATIBLE
        and not finding.reason_code.startswith(
            ("USER_NUTRITION_", "NUTRITION_", "NUTRIENT_")
        )
        for finding in state["risk_findings"]
    )
    if not needs_explanation and not state["claim_interpretations"]:
        evidence_status = "not_required"
    elif state["errors"]:
        evidence_status = "blocked"
    elif (
        any(
            item.get("status") == "unknown" for item in state["ingredient_explanations"]
        )
        or (needs_explanation and not state["ingredient_explanations"])
        or any(
            item.get("status") == "unknown" or item.get("unknowns")
            for item in state["claim_interpretations"]
        )
        or any(
            item.get("status") == "unknown" for item in state["consistency_findings"]
        )
    ):
        evidence_status = "unknown"
    else:
        evidence_status = "grounded"
    return {
        "status": evidence_status,
        "jurisdiction": state["jurisdiction"],
        "applicable_date": state["applicable_date"],
        "final_status": state["status"].value,
        "interpretations": state["ingredient_explanations"],
        "claim_interpretations": state["claim_interpretations"],
        "consistency_findings": state["consistency_findings"],
        "regulatory_evidence": [asdict(item) for item in state["regulatory_evidence"]],
        "unknowns": state["unknowns"],
        "errors": state["errors"],
        "agent_trace": [asdict(item) for item in state["tool_trace"]],
        "workflow_trace": [asdict(item) for item in state["workflow_trace"]],
        "react_budget": state["react_budget"],
        "release_gate": evaluate_workflow_release(state),
    }


def alternative_payload(state: AgentState, category: str) -> dict:
    release_gate = evaluate_workflow_release(state)
    all_raw_eligible = [
        item
        for item in state["alternatives"]
        if item.get("disposition") == "eligible"
    ]
    # A failed final gate must fail closed at the API boundary. Keeping these
    # candidates in `eligible` would let a client present an unsafe record even
    # though the workflow itself is blocked.
    raw_eligible = all_raw_eligible if release_gate["passed"] else []
    health_comparison_requested = bool(
        state["alternative_request"].get("health_concerns")
    )
    eligible = [
        _with_alternative_result_state(
            item,
            health_comparison_requested=health_comparison_requested,
        )
        for item in raw_eligible
    ]
    excluded = [
        _with_alternative_result_state(
            item,
            health_comparison_requested=health_comparison_requested,
        )
        for item in state["alternatives"]
        if item.get("disposition") == "excluded"
    ]
    evidence_rejected = [
        _with_evidence_review_state(item)
        for item in state["alternative_request"].get("search_rejected", [])
    ]
    if not release_gate["passed"]:
        evidence_rejected.extend(
            _with_release_gate_blocked_state(item) for item in all_raw_eligible
        )
    coverage = state["alternative_request"].get("catalog_coverage", {})
    catalog_total = int(coverage.get("total") or 0)
    review_ready_total = int(coverage.get("evidence_gate_count") or 0)
    target_comparable = [
        item
        for item in eligible
        if not item.get("catalog_eligibility", {}).get(
            "missing_comparison_fields", []
        )
    ]
    sugar_missing = [
        item
        for item in eligible
        if "糖"
        in item.get("catalog_eligibility", {}).get(
            "missing_comparison_fields", []
        )
    ]
    sugar_evidence_status_counts = {
        status: sum(
            item.get("catalog_eligibility", {}).get("sugars_review_status")
            == status
            for item in sugar_missing
        )
        for status in (
            "declared",
            "not_declared",
            "source_insufficient",
            "not_reviewed",
        )
    }
    effective = target_comparable if health_comparison_requested else eligible
    display_limit = state["alternative_request"].get("display_limit", 8)

    def ratio(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    return {
        "status": state["status"].value,
        "category": category,
        "catalog_scope": state["alternative_request"].get("catalog_scope"),
        "catalog_status": state["alternative_request"].get("catalog_status"),
        "catalog_warnings": state["alternative_request"].get("catalog_warnings", []),
        "catalog_coverage": coverage,
        "selection_basis": state["alternative_request"].get("selection_basis"),
        "eligible": eligible,
        "display_metrics": {
            "catalog_count": catalog_total,
            "displayable_count": len(eligible),
            "displayable_rate": ratio(len(eligible), catalog_total),
            "review_ready_catalog_count": review_ready_total,
            "review_ready_display_rate": ratio(len(eligible), review_ready_total),
            "initially_visible_count": min(len(eligible), display_limit),
            "initially_visible_rate": ratio(min(len(eligible), display_limit), catalog_total),
            "target_comparison_requested": health_comparison_requested,
            "target_comparable_count": len(target_comparable),
            "target_comparable_rate": ratio(len(target_comparable), len(eligible)),
            "sugar_missing_count": len(sugar_missing),
            "sugar_evidence_status_counts": sugar_evidence_status_counts,
            "effective_display_count": len(effective),
            "effective_display_rate": ratio(len(effective), catalog_total),
        },
        "excluded": excluded,
        "evidence_rejected": evidence_rejected,
        "result_summary": _alternative_result_summary(
            eligible=eligible,
            excluded=excluded,
            evidence_rejected=evidence_rejected,
        ),
        "comparison": (
            state["alternative_comparison"]
            if release_gate["passed"]
            else {
                "status": "not_compared",
                "unknowns": ["final_safety_gate_blocked"],
                "comparisons": [],
            }
        ),
        "candidate_count": state["alternative_request"].get("candidate_count", 0),
        "revalidated_count": state["alternative_request"].get("revalidated_count", 0),
        "revalidation_rate": state["alternative_request"].get("revalidation_rate", 0.0),
        "ranking_method": state["alternative_request"].get("ranking_method", {}),
        "unknowns": state["unknowns"],
        "errors": state["errors"],
        "workflow_trace": [asdict(item) for item in state["workflow_trace"]],
        "release_gate": release_gate,
    }


def _with_alternative_result_state(
    item: dict,
    *,
    health_comparison_requested: bool,
) -> dict:
    """Attach one stable, actionable display state without weakening safety."""

    enriched = dict(item)
    if item.get("disposition") == "excluded":
        enriched["result_state"] = _result_state_payload(
            "constraint_conflict",
            detail="该商品未通过你设置的硬性约束，因此不会进入备选列表。",
            next_action="可以查看冲突字段；不要为了获得更多结果而放宽严重过敏或明确营养上限。",
        )
        return enriched

    eligibility = item.get("catalog_eligibility", {})
    missing = list(eligibility.get("missing_comparison_fields") or [])
    if health_comparison_requested and missing:
        detail, next_action = _limited_comparison_guidance(eligibility, missing)
        enriched["result_state"] = _result_state_payload(
            "same_use_evidence_limited",
            detail=detail,
            next_action=next_action,
            missing_fields=missing,
        )
        return enriched

    enriched["result_state"] = _result_state_payload(
        "comparable",
        detail=(
            "该商品已通过当前硬性约束，目标营养字段也具备同口径比较证据。"
            if health_comparison_requested
            else "该商品已通过当前硬性约束，可作为同类别或同用途备选。"
        ),
        next_action="购买前仍需核对实际包装的配方、规格和版本。",
    )
    return enriched


def _with_evidence_review_state(item: dict) -> dict:
    enriched = dict(item)
    coverage = item.get("label_coverage") or {}
    context = coverage.get("context_eligibility") or {}
    missing = list(
        context.get("missing_required_fields")
        or coverage.get("missing_fields")
        or []
    )
    enriched["result_state"] = _result_state_payload(
        "packaging_review_required",
        detail="商品身份可能匹配，但现有包装证据不足以完成本次安全判断。",
        next_action=(
            f"需要核对同一 SKU 包装的{'、'.join(missing)}。"
            if missing
            else "需要核对同一 SKU 的配料、过敏原提示和营养标签。"
        ),
        missing_fields=missing,
    )
    return enriched


def _with_release_gate_blocked_state(item: dict) -> dict:
    enriched = dict(item)
    enriched["reason_code"] = "FINAL_SAFETY_GATE_BLOCKED"
    enriched["result_state"] = _result_state_payload(
        "packaging_review_required",
        detail="最终安全门未通过，因此该商品不能作为推荐结果展示。",
        next_action="请补齐对应证据并重新完成安全复核；不要仅凭当前候选食用或购买。",
    )
    return enriched


def _limited_comparison_guidance(
    eligibility: dict,
    missing_fields: list[str],
) -> tuple[str, str]:
    if "糖" in missing_fields:
        sugar_status = eligibility.get("sugars_review_status")
        if sugar_status == "not_declared":
            return (
                "该商品未单列糖，因此不能判断是否符合你的糖上限。",
                "可以继续查看碳水化合物，但不能宣称它更适合控糖；购买前请核对实物营养标签。",
            )
        if sugar_status == "source_insufficient":
            return (
                "当前官方来源没有提供可核对的糖数值，因此不能完成控糖比较。",
                "需要查看同一 SKU 的完整营养背标；在此之前只作同用途备选。",
            )
        return (
            "该商品缺少已复核的糖数值，暂时不能完成控糖比较。",
            "请核对同一 SKU 的实物营养背标；不从碳水化合物推算糖。",
        )
    joined = "、".join(missing_fields)
    return (
        f"该商品缺少{joined}的可比较证据，不能回答当前健康关注。",
        f"可以作为同用途备选，但购买前需核对实物包装的{joined}；不宣称营养上更优。",
    )


def _result_state_payload(
    state: str,
    *,
    detail: str,
    next_action: str,
    missing_fields: list[str] | None = None,
) -> dict:
    labels = {
        "comparable": "可显示并比较",
        "same_use_evidence_limited": "同用途备选，比较证据不足",
        "packaging_review_required": "需要核对包装后才能判断",
        "constraint_conflict": "与你的硬性约束冲突",
        "no_trusted_candidate": "当前没有可信候选",
    }
    return {
        "state": state,
        "label": labels[state],
        "detail": detail,
        "next_action": next_action,
        "missing_fields": missing_fields or [],
    }


def _alternative_result_summary(
    *,
    eligible: list[dict],
    excluded: list[dict],
    evidence_rejected: list[dict],
) -> dict:
    counts = {
        state: sum(
            item.get("result_state", {}).get("state") == state
            for item in (*eligible, *excluded, *evidence_rejected)
        )
        for state in (
            "comparable",
            "same_use_evidence_limited",
            "packaging_review_required",
            "constraint_conflict",
        )
    }
    if counts["comparable"]:
        primary = "comparable"
    elif counts["same_use_evidence_limited"]:
        primary = "same_use_evidence_limited"
    elif counts["packaging_review_required"]:
        primary = "packaging_review_required"
    elif counts["constraint_conflict"]:
        primary = "constraint_conflict"
    else:
        primary = "no_trusted_candidate"
    return {
        "primary_state": primary,
        "primary": _result_state_payload(
            primary,
            detail=(
                "已查询当前审核目录，但没有商品同时满足用途、硬性约束和证据要求。"
                if primary == "no_trusted_candidate"
                else "本次结果已按可比较性、包装证据和硬性约束分层。"
            ),
            next_action=(
                "可以更正替代用途或稍后重试；系统不会为了显示结果而降低证据门槛。"
                if primary == "no_trusted_candidate"
                else "先查看可比较候选，其他商品会明确标出缺少的证据或冲突。"
            ),
        ),
        "counts": counts,
        "safety_gate_held": True,
    }


def _constraint(item) -> UserConstraint:
    return UserConstraint(
        kind=ConstraintKind(item.kind),
        canonical_value=item.canonical_value,
        severity=item.severity,
        operator=item.operator,
        threshold=item.threshold,
        unit=item.unit,
        basis=item.basis,
    )


def _clear_retriable_failures(state: AgentState) -> None:
    state["errors"] = [
        item for item in state["errors"] if not item.startswith("mcp_tool_failed:")
    ]
    state["unknowns"] = [
        item for item in state["unknowns"] if not item.endswith("_unavailable")
    ]
