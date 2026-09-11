"""Structured short-term state derived only from confirmed workflow facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from food_label_agent.graph.state import AgentState


@dataclass(frozen=True, slots=True)
class ConversationProduct:
    request_id: str
    display_name: str
    jurisdiction: str
    applicable_date: str
    confirmed_fields: dict[str, str]
    nutrition: dict[str, Any]
    risk_findings: tuple[dict[str, Any], ...]
    unresolved_questions: tuple[str, ...]
    regulatory_evidence: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["risk_findings"] = list(self.risk_findings)
        value["unresolved_questions"] = list(self.unresolved_questions)
        value["regulatory_evidence"] = list(self.regulatory_evidence)
        return value


@dataclass(frozen=True, slots=True)
class StructuredConversationState:
    active_product_id: str | None = None
    products: tuple[ConversationProduct, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    current_intent: str = "general_question"
    last_evidence: tuple[dict[str, Any], ...] = ()
    updated_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_product_id": self.active_product_id,
            "products": [item.to_dict() for item in self.products],
            "unresolved_questions": list(self.unresolved_questions),
            "current_intent": self.current_intent,
            "last_evidence": list(self.last_evidence),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> StructuredConversationState:
        if not value:
            return cls()
        products = tuple(
            ConversationProduct(
                request_id=str(item["request_id"]),
                display_name=str(item.get("display_name") or "已确认商品"),
                jurisdiction=str(item.get("jurisdiction") or "CN"),
                applicable_date=str(item.get("applicable_date") or ""),
                confirmed_fields={
                    str(key): str(text)
                    for key, text in dict(item.get("confirmed_fields") or {}).items()
                },
                nutrition=dict(item.get("nutrition") or {}),
                risk_findings=tuple(item.get("risk_findings") or ()),
                unresolved_questions=tuple(item.get("unresolved_questions") or ()),
                regulatory_evidence=tuple(item.get("regulatory_evidence") or ()),
            )
            for item in value.get("products", [])[:2]
        )
        return cls(
            active_product_id=value.get("active_product_id"),
            products=products,
            unresolved_questions=tuple(value.get("unresolved_questions") or ()),
            current_intent=str(value.get("current_intent") or "general_question"),
            last_evidence=tuple(value.get("last_evidence") or ()),
            updated_at=str(value.get("updated_at") or datetime.now().astimezone().isoformat()),
        )


def update_structured_state(
    current: StructuredConversationState,
    *,
    message: str,
    workflow_state: AgentState | None = None,
) -> StructuredConversationState:
    products = list(current.products)
    active_product_id = current.active_product_id
    last_evidence = current.last_evidence
    if workflow_state is not None:
        product = product_from_agent_state(workflow_state)
        products = [item for item in products if item.request_id != product.request_id]
        products.append(product)
        products = products[-2:]
        active_product_id = product.request_id
        last_evidence = product.regulatory_evidence
    unresolved = tuple(
        dict.fromkeys(
            question
            for product in products
            for question in product.unresolved_questions
        )
    )[:20]
    return StructuredConversationState(
        active_product_id=active_product_id,
        products=tuple(products),
        unresolved_questions=unresolved,
        current_intent=classify_conversation_intent(message),
        last_evidence=last_evidence,
    )


def product_from_agent_state(state: AgentState) -> ConversationProduct:
    fields = {
        name: field.raw_text
        for name, field in state["label_fields"].items()
        if field.confirmed_by_user
    }
    display_name = (
        fields.get("product_name")
        or fields.get("name")
        or f"商品 {state['request_id'][-6:]}"
    )
    evidence = tuple(
        {
            "source_id": item.source_id,
            "title": item.title,
            "section": item.section,
            "source_url": item.source_url,
            "evidence_text": item.evidence_text,
        }
        for item in state["regulatory_evidence"][:10]
    )
    return ConversationProduct(
        request_id=state["request_id"],
        display_name=display_name,
        jurisdiction=state["jurisdiction"],
        applicable_date=state["applicable_date"],
        confirmed_fields=fields,
        nutrition=dict(state["normalized_label"].get("nutrition") or {}),
        risk_findings=tuple(asdict(item) for item in state["risk_findings"]),
        unresolved_questions=tuple(
            dict.fromkeys([*state["unknowns"], *state["warnings"]])
        )[:20],
        regulatory_evidence=evidence,
    )


def classify_conversation_intent(message: str) -> str:
    text = message.casefold()
    if any(term in text for term in ("对比", "比较", "哪个", "哪一个")):
        return "compare_products"
    if any(term in text for term in ("识别错", "怎么改", "修改", "纠错", "括号")):
        return "correct_label"
    if any(term in text for term in ("法规", "国标", "规定", "条款")):
        return "regulation_question"
    if any(term in text for term in ("证据冲突", "证据矛盾", "信息冲突", "说法不一致")):
        return "evidence_conflict"
    if any(term in text for term in ("能吃", "适合", "过敏", "风险")):
        return "safety_question"
    return "general_question"


def reasoning_effort_for_intent(intent: str, *, default: str = "low") -> str:
    if intent in {"compare_products", "regulation_question", "evidence_conflict"}:
        return "medium"
    return default


def compare_confirmed_products(
    state: StructuredConversationState,
) -> dict[str, Any]:
    if len(state.products) < 2:
        return {"status": "unknown", "reason": "two_confirmed_products_required"}
    products = state.products[-2:]
    rows: list[dict[str, Any]] = []
    for nutrient in ("energy", "protein", "fat", "sugars", "sodium"):
        values = [_nutrient_value(product, nutrient) for product in products]
        if all(value is not None for value in values) and values[0][1:] == values[1][1:]:
            rows.append(
                {
                    "nutrient": nutrient,
                    "basis": values[0][2],
                    "unit": values[0][1],
                    "values": [
                        {"product": product.display_name, "value": value[0]}
                        for product, value in zip(products, values, strict=True)
                    ],
                }
            )
    return {
        "status": "compared" if rows else "unknown",
        "products": [item.display_name for item in products],
        "comparisons": rows,
        "risk_findings": [
            {"product": item.display_name, "findings": list(item.risk_findings)}
            for item in products
        ],
        "boundary": "evidence_comparison_only_no_medical_decision",
        "reason": None if rows else "no_same_basis_confirmed_nutrition",
    }


def correction_guidance(state: StructuredConversationState) -> dict[str, Any]:
    product = next(
        (item for item in state.products if item.request_id == state.active_product_id),
        state.products[-1] if state.products else None,
    )
    if product is None:
        return {"status": "unknown", "reason": "no_confirmed_product"}
    issues = list(product.unresolved_questions)
    return {
        "status": "review_required" if issues else "confirmed",
        "product": product.display_name,
        "issues": issues,
        "instructions": [
            "对照实物包装定位对应文字",
            "只修改能够从包装确认的文字",
            "修改后再次明确确认，系统不会自动写回标签事实",
        ],
        "auto_correction_applied": False,
    }


def _nutrient_value(
    product: ConversationProduct, nutrient: str
) -> tuple[float, str, str] | None:
    nutrition = product.nutrition
    basis = nutrition.get("basis") or {}
    basis_type = str(basis.get("type") or "")
    for item in nutrition.get("nutrients", []):
        if item.get("canonical_name") == nutrient and basis_type in {"per_100g", "per_100ml"}:
            return float(item["value"]), str(item["unit"]), basis_type
    return None
