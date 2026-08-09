"""Production-safe deterministic implementations of core graph nodes."""

from __future__ import annotations

from dataclasses import asdict

from food_label_agent.context.builder import build_node_context
from food_label_agent.domain.models import AuditEvent, Evidence, RiskFinding
from food_label_agent.domain.types import AnalysisStatus, RiskLevel, WorkflowStage
from food_label_agent.mcp.business_tools import MCPToolCallError, invoke_mcp_tool

from .routing import critical_fields_needing_confirmation
from .routing import final_safety_gate as evaluate_final_safety_gate
from .state import AgentState


def normalize_label(state: AgentState) -> dict:
    """Normalize only confirmed critical label facts."""

    if critical_fields_needing_confirmation(state):
        return {
            "status": AnalysisStatus.NEEDS_CONFIRMATION,
            "stage": WorkflowStage.HUMAN_CONFIRMATION,
            "unknowns": list(
                dict.fromkeys([*state["unknowns"], "ingredients_not_confirmed"])
            ),
        }
    field = state["label_fields"]["ingredients"]
    nutrition_table = state["label_fields"].get("nutrition_table")
    nutrition_basis = state["label_fields"].get("nutrition_basis")
    try:
        normalized = invoke_mcp_tool(
            "normalize_food_label",
            {
                "ingredients_text": field.raw_text,
                "source_bounding_box": field.bounding_box,
                "nutrition_table_text": nutrition_table.raw_text
                if nutrition_table
                else None,
                "nutrition_basis_text": nutrition_basis.raw_text
                if nutrition_basis
                else None,
            },
        )
    except MCPToolCallError as exc:
        return _tool_failure(state, exc)
    requires_confirmation = bool(normalized["requires_confirmation"])
    return {
        "status": (
            AnalysisStatus.NEEDS_CONFIRMATION
            if requires_confirmation
            else AnalysisStatus.IN_PROGRESS
        ),
        "stage": (
            WorkflowStage.HUMAN_CONFIRMATION
            if requires_confirmation
            else WorkflowStage.LABEL_NORMALIZATION
        ),
        "normalized_label": normalized,
        "unknowns": list(
            dict.fromkeys(
                [
                    *state["unknowns"],
                    *(
                        ["ingredient_structure_needs_confirmation"]
                        if requires_confirmation
                        else []
                    ),
                ]
            )
        ),
        "audit_events": [
            *state["audit_events"],
            _context_event(state, "normalize_label"),
            AuditEvent(
                event_type="label_normalized",
                actor="mcp:normalize_food_label",
                detail={
                    "tool_name": "normalize_food_label",
                    "parse_status": normalized["parse_status"],
                    "ingredient_count": _ingredient_count(normalized["ingredients"]),
                },
            ),
        ],
    }


def evaluate_safety(state: AgentState) -> dict:
    """Evaluate hard constraints without an LLM in the decision path."""

    field = state["label_fields"].get("ingredients")
    if field is None:
        return {
            "status": AnalysisStatus.NEEDS_CONFIRMATION,
            "stage": WorkflowStage.HUMAN_CONFIRMATION,
            "risk_findings": [],
        }
    confirmed_fields = {
        name: label_field.raw_text
        for name, label_field in state["label_fields"].items()
        if label_field.confirmed_by_user or name != "ingredients"
    }
    try:
        result = invoke_mcp_tool(
            "evaluate_user_constraints",
            {
                "request_id": state["request_id"],
                "jurisdiction": state["jurisdiction"],
                "applicable_date": state["applicable_date"],
                "confirmed_fields": confirmed_fields,
                "constraints": [
                    {
                        "kind": constraint.kind.value,
                        "canonical_value": constraint.canonical_value,
                        "severity": constraint.severity,
                        "operator": constraint.operator,
                        "threshold": constraint.threshold,
                        "unit": constraint.unit,
                        "basis": constraint.basis,
                    }
                    for constraint in state["user_constraints"]
                ],
            },
        )
    except MCPToolCallError as exc:
        return _tool_failure(state, exc)
    findings = [_risk_finding(item) for item in result["findings"]]
    return {
        "status": AnalysisStatus.IN_PROGRESS,
        "stage": WorkflowStage.SAFETY_EVALUATION,
        "risk_findings": findings,
        "audit_events": [
            *state["audit_events"],
            _context_event(state, "evaluate_safety"),
            AuditEvent(
                event_type="safety_evaluated",
                actor="mcp:evaluate_user_constraints",
                detail={
                    "tool_name": "evaluate_user_constraints",
                    "finding_count": len(findings),
                    "overall_risk_level": result["overall_risk_level"],
                },
            ),
        ],
    }


def retrieve_regulations(state: AgentState) -> dict:
    """Retrieve official clauses applicable to this state and its risk findings."""

    query_terms = [
        value
        for finding in state["risk_findings"]
        if finding.risk_level is not RiskLevel.COMPATIBLE
        for value in (finding.matched_text, finding.constraint)
        if value
    ]
    additive_terms = [
        item.get("canonical_name") or item.get("raw_name")
        for item in _additive_ingredients(state.get("normalized_label", {}))
    ]
    nutrition_only = (
        bool(state["risk_findings"])
        and not additive_terms
        and all(
            finding.reason_code.startswith(
                ("USER_NUTRITION_", "NUTRITION_", "NUTRIENT_")
            )
            for finding in state["risk_findings"]
        )
    )
    needs_allergen_evidence = any(
        finding.risk_level is not RiskLevel.COMPATIBLE
        and not finding.reason_code.startswith(
            ("USER_NUTRITION_", "NUTRITION_", "NUTRIENT_")
        )
        for finding in state["risk_findings"]
    )
    searches: list[dict] = []
    if nutrition_only:
        searches.append(
            {
                "query": " ".join([*query_terms, "营养成分表 标示值 计量单位"]),
                "topics": ["nutrition_labeling"],
            }
        )
    if needs_allergen_evidence:
        searches.append(
            {
                "query": " ".join([*query_terms, "食品标签 配料表 过敏原 致敏物质"]),
                "topics": ["allergen", "ingredient_labeling"],
            }
        )
    if additive_terms:
        searches.append(
            {
                "query": " ".join([*additive_terms, "GB 2760-2024 食品添加剂使用标准"]),
                "topics": ["food_additive"],
            }
        )
    if not searches:
        searches.append({"query": "食品标签 配料表", "topics": ["ingredient_labeling"]})
    try:
        results = [
            invoke_mcp_tool(
                "search_food_regulations",
                {
                    **search,
                    "jurisdiction": state["jurisdiction"],
                    "applicable_date": state["applicable_date"],
                    "limit": 5,
                },
            )
            for search in searches
        ]
    except MCPToolCallError as exc:
        return _tool_failure(state, exc)

    evidence_by_id = {
        item["evidence_id"]: _regulatory_evidence(item)
        for result in results
        for item in result["results"]
    }
    evidence = list(evidence_by_id.values())
    retrieval_unknowns = [
        unknown for result in results for unknown in result.get("unknowns", [])
    ]
    retrieval_methods = sorted(
        {result.get("retrieval_method", "unknown") for result in results}
    )
    return {
        "status": AnalysisStatus.IN_PROGRESS,
        "stage": WorkflowStage.REGULATORY_RETRIEVAL,
        "regulatory_evidence": evidence,
        "unknowns": list(dict.fromkeys([*state["unknowns"], *retrieval_unknowns])),
        "audit_events": [
            *state["audit_events"],
            AuditEvent(
                event_type="regulations_retrieved",
                actor="mcp:search_food_regulations",
                detail={
                    "tool_name": "search_food_regulations",
                    "applicable_date": state["applicable_date"],
                    "evidence_count": len(evidence),
                    "retrieval_method": (
                        retrieval_methods[0]
                        if len(retrieval_methods) == 1
                        else retrieval_methods
                    ),
                    "search_count": len(searches),
                },
            ),
        ],
    }


def _context_event(state: AgentState, node_name: str) -> AuditEvent:
    context = build_node_context(state, node_name)
    return AuditEvent(
        event_type="node_context_built",
        actor=f"context_builder:{node_name}",
        detail={
            "node_name": node_name,
            "included_fields": list(context.included_fields),
            "excluded_fields": list(context.excluded_fields),
            "estimated_tokens": context.estimated_tokens,
            "token_budget": context.token_budget,
            "truncated": context.truncated,
            "budget_exceeded": context.budget_exceeded,
            "context_digest": context.digest,
        },
    )


def interpret_label(state: AgentState) -> dict:
    """Build evidence-bound ingredient explanations without changing risk."""

    explanations: list[dict] = []
    unknowns = list(state["unknowns"])
    regulation_payload = [asdict(item) for item in state["regulatory_evidence"]]
    for finding in state["risk_findings"]:
        if finding.risk_level is RiskLevel.COMPATIBLE:
            continue
        if finding.reason_code.startswith(
            ("USER_NUTRITION_", "NUTRITION_", "NUTRIENT_")
        ):
            continue
        ingredient = _ingredient_for_finding(state["normalized_label"], finding)
        if ingredient is None:
            unknowns.append("ingredient_explanation_target_missing")
            continue
        try:
            explanation = invoke_mcp_tool(
                "explain_ingredient",
                {
                    "ingredient": ingredient,
                    "risk_finding": _risk_finding_payload(finding),
                    "regulatory_evidence": regulation_payload,
                    "jurisdiction": state["jurisdiction"],
                    "applicable_date": state["applicable_date"],
                },
            )
        except MCPToolCallError as exc:
            return _tool_failure(state, exc)
        explanations.append(explanation)
        unknowns.extend(explanation.get("unknowns", []))

    for ingredient in _additive_ingredients(state.get("normalized_label", {})):
        try:
            explanation = invoke_mcp_tool(
                "explain_ingredient",
                {
                    "ingredient": ingredient,
                    "risk_finding": None,
                    "regulatory_evidence": regulation_payload,
                    "jurisdiction": state["jurisdiction"],
                    "applicable_date": state["applicable_date"],
                },
            )
        except MCPToolCallError as exc:
            return _tool_failure(state, exc)
        explanations.append(explanation)
        unknowns.extend(explanation.get("unknowns", []))

    return {
        "status": AnalysisStatus.IN_PROGRESS,
        "stage": WorkflowStage.INTERPRETATION,
        "ingredient_explanations": explanations,
        "unknowns": list(dict.fromkeys(unknowns)),
        "audit_events": [
            *state["audit_events"],
            AuditEvent(
                event_type="label_interpreted",
                actor="mcp:explain_ingredient",
                detail={
                    "tool_name": "explain_ingredient",
                    "explanation_count": len(explanations),
                    "unknown_count": sum(
                        item["status"] == "unknown" for item in explanations
                    ),
                },
            ),
        ],
    }


def interpret_claims(state: AgentState) -> dict:
    """Retrieve claim-specific evidence and interpret confirmed package claims."""

    field = state["label_fields"].get("label_claims")
    if field is None or not field.raw_text.strip():
        return {
            "status": AnalysisStatus.IN_PROGRESS,
            "stage": WorkflowStage.CLAIM_INTERPRETATION,
            "claim_interpretations": [],
        }
    if not field.confirmed_by_user:
        return {
            "status": AnalysisStatus.NEEDS_CONFIRMATION,
            "stage": WorkflowStage.HUMAN_CONFIRMATION,
            "unknowns": list(
                dict.fromkeys([*state["unknowns"], "label_claims_not_confirmed"])
            ),
        }
    try:
        search = invoke_mcp_tool(
            "search_food_regulations",
            {
                "query": f"{field.raw_text} 无糖 低糖 糖含量 营养声称 表C.1",
                "jurisdiction": state["jurisdiction"],
                "applicable_date": state["applicable_date"],
                "topics": ["nutrition_claim"],
                "limit": 5,
            },
        )
        existing = {item.source_id: item for item in state["regulatory_evidence"]}
        for item in search["results"]:
            evidence = _regulatory_evidence(item)
            existing[evidence.source_id] = evidence
        regulation_payload = [asdict(item) for item in existing.values()]
        result = invoke_mcp_tool(
            "interpret_label_claim",
            {
                "claim_text": field.raw_text,
                "regulatory_evidence": regulation_payload,
                "jurisdiction": state["jurisdiction"],
                "applicable_date": state["applicable_date"],
            },
        )
    except MCPToolCallError as exc:
        return _tool_failure(state, exc)
    return {
        "status": AnalysisStatus.IN_PROGRESS,
        "stage": WorkflowStage.CLAIM_INTERPRETATION,
        "regulatory_evidence": list(existing.values()),
        "claim_interpretations": result["claims"],
        "unknowns": list(
            dict.fromkeys(
                [
                    *state["unknowns"],
                    *search.get("unknowns", []),
                    *result.get("unknowns", []),
                ]
            )
        ),
        "audit_events": [
            *state["audit_events"],
            AuditEvent(
                event_type="label_claims_interpreted",
                actor="mcp:interpret_label_claim",
                detail={
                    "tool_name": "interpret_label_claim",
                    "claim_count": len(result["claims"]),
                    "evidence_count": len(search["results"]),
                },
            ),
        ],
    }


def verify_consistency(state: AgentState) -> dict:
    """Cross-check interpreted claims against confirmed label facts."""

    if not state["claim_interpretations"]:
        return {
            "status": AnalysisStatus.IN_PROGRESS,
            "stage": WorkflowStage.CONSISTENCY_VERIFICATION,
            "consistency_findings": [],
        }
    ingredients = state["label_fields"].get("ingredients")
    try:
        result = invoke_mcp_tool(
            "verify_label_consistency",
            {
                "claims": state["claim_interpretations"],
                "ingredients_text": ingredients.raw_text if ingredients else None,
                "nutrition_values": _nutrition_values(state),
                "regulatory_evidence": [
                    asdict(item) for item in state["regulatory_evidence"]
                ],
                "jurisdiction": state["jurisdiction"],
                "applicable_date": state["applicable_date"],
            },
        )
    except MCPToolCallError as exc:
        return _tool_failure(state, exc)
    return {
        "status": AnalysisStatus.IN_PROGRESS,
        "stage": WorkflowStage.CONSISTENCY_VERIFICATION,
        "consistency_findings": result["findings"],
        "unknowns": list(
            dict.fromkeys([*state["unknowns"], *result.get("unknowns", [])])
        ),
        "audit_events": [
            *state["audit_events"],
            AuditEvent(
                event_type="label_consistency_verified",
                actor="mcp:verify_label_consistency",
                detail={
                    "tool_name": "verify_label_consistency",
                    "finding_count": len(result["findings"]),
                    "status": result["status"],
                },
            ),
        ],
    }


def final_safety_gate_node(state: AgentState) -> dict:
    """Apply the mandatory evidence and risk-preservation gate."""

    result = evaluate_final_safety_gate(state)
    violation_errors = [
        f"safety_gate_violation:{violation}" for violation in result.violations
    ]
    if result.status is AnalysisStatus.COMPLETED:
        stage = WorkflowStage.COMPLETED
    elif result.status is AnalysisStatus.NEEDS_CONFIRMATION:
        stage = WorkflowStage.HUMAN_CONFIRMATION
    else:
        stage = WorkflowStage.FINAL_SAFETY_GATE
    return {
        "status": result.status,
        "stage": stage,
        "warnings": list(result.warnings),
        "unknowns": list(result.unknowns),
        "errors": list(dict.fromkeys([*state["errors"], *violation_errors])),
        "audit_events": [
            *state["audit_events"],
            _context_event(state, "final_safety_gate"),
            AuditEvent(
                event_type="final_safety_gate_evaluated",
                actor="orchestrator:final_safety_gate",
                detail={
                    "can_complete": result.can_complete,
                    "status": result.status.value,
                    "violation_count": len(result.violations),
                },
            ),
        ],
    }


def _risk_finding(value: dict) -> RiskFinding:
    return RiskFinding(
        risk_level=RiskLevel(value["risk_level"]),
        constraint=value["constraint"],
        matched_text=value.get("matched_text"),
        reason_code=value["reason_code"],
        explanation=value["explanation"],
        evidence_ids=tuple(value.get("evidence_ids", ())),
    )


def _regulatory_evidence(value: dict) -> Evidence:
    return Evidence(
        source_id=value["evidence_id"],
        title=value["title"],
        jurisdiction=value["jurisdiction"],
        section=value["section"],
        source_url=value["source_url"],
        effective_from=value["effective_from"],
        effective_to=value.get("effective_to"),
        authority_level=value["authority_level"],
        standard_number=value["standard_number"],
        evidence_text=value["evidence_text"],
        content_hash=value["content_hash"],
        retrieval_score=value["retrieval_score"],
        retrieval_method=value["retrieval_method"],
        source_type=value.get("source_type"),
        document_hash=value.get("document_hash"),
        page_start=value.get("page_start"),
        page_end=value.get("page_end"),
    )


def _risk_finding_payload(finding: RiskFinding) -> dict:
    return {
        "risk_level": finding.risk_level.value,
        "constraint": finding.constraint,
        "matched_text": finding.matched_text,
        "reason_code": finding.reason_code,
        "explanation": finding.explanation,
        "evidence_ids": list(finding.evidence_ids),
    }


def _ingredient_for_finding(
    normalized_label: dict, finding: RiskFinding
) -> dict | None:
    evidence_ids = set(finding.evidence_ids)
    stack = list(reversed(normalized_label.get("ingredients", [])))
    while stack:
        ingredient = stack.pop()
        if ingredient.get("evidence_id") in evidence_ids:
            return ingredient
        stack.extend(reversed(ingredient.get("children", [])))
    if "label.allergen_statement" in evidence_ids and finding.matched_text:
        return {
            "raw_name": finding.matched_text,
            "canonical_name": finding.matched_text,
            "category": "包装致敏物质提示",
            "relation": "declared_statement",
            "allergen_keys": [finding.constraint],
            "normalization_method": "declared_statement",
            "evidence_id": "label.allergen_statement",
        }
    return None


def _ingredient_count(items: list[dict]) -> int:
    return sum(1 + _ingredient_count(item.get("children", [])) for item in items)


def _additive_ingredients(normalized_label: dict) -> list[dict]:
    result: list[dict] = []

    def walk(items: list[dict], *, inside_group: bool = False) -> None:
        for item in items:
            relation = item.get("relation")
            is_group = relation == "group" or item.get("canonical_name") == "食品添加剂"
            if relation == "additive":
                result.append(item)
            elif inside_group and relation != "group":
                result.append({**item, "relation": "additive_declared"})
            walk(item.get("children", []), inside_group=inside_group or is_group)

    walk(normalized_label.get("ingredients", []))
    return result


def _nutrition_values(state: AgentState) -> dict:
    nutrition = state.get("normalized_label", {}).get("nutrition") or {}
    sugar = next(
        (
            item
            for item in nutrition.get("nutrients", [])
            if item.get("canonical_name") == "sugars"
        ),
        None,
    )
    if sugar and sugar.get("basis") in {"per_100g", "per_100ml"}:
        return {"sugars_g": sugar["value"], "basis": sugar["basis"]}
    return {}


def _tool_failure(state: AgentState, error: MCPToolCallError) -> dict:
    return {
        "status": AnalysisStatus.BLOCKED,
        "errors": [
            *state["errors"],
            f"mcp_tool_failed:{error.tool_name}",
        ],
        "unknowns": list(
            dict.fromkeys([*state["unknowns"], f"{error.tool_name}_unavailable"])
        ),
        "audit_events": [
            *state["audit_events"],
            AuditEvent(
                event_type="mcp_tool_failed",
                actor="orchestrator",
                detail={"tool_name": error.tool_name},
            ),
        ],
    }
