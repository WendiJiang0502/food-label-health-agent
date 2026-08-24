"""Deterministic decomposition of label questions into evidence needs."""

from __future__ import annotations

from dataclasses import dataclass

from food_label_agent.domain.types import RiskLevel

from .state import AgentState


@dataclass(frozen=True, slots=True)
class EvidenceNeed:
    need_id: str
    query: str
    topics: tuple[str, ...]
    expected_standard_prefixes: tuple[str, ...]
    purpose: str

    def search_arguments(self, state: AgentState) -> dict:
        return {
            "query": self.query,
            "jurisdiction": state["jurisdiction"],
            "applicable_date": state["applicable_date"],
            "topics": list(self.topics),
            "limit": 5,
        }


def build_evidence_plan(state: AgentState) -> tuple[EvidenceNeed, ...]:
    """Route independent facts to narrowly scoped official-evidence searches."""

    findings = [
        item
        for item in state["risk_findings"]
        if item.risk_level is not RiskLevel.COMPATIBLE
    ]
    nutrition = [item for item in findings if _is_nutrition(item.reason_code)]
    allergens = [item for item in findings if not _is_nutrition(item.reason_code)]
    additives = _additives(state.get("normalized_label", {}))
    claim = state["label_fields"].get("label_claims")
    needs: list[EvidenceNeed] = []
    if allergens:
        terms = [
            value
            for item in allergens
            for value in (item.matched_text, item.constraint)
            if value
        ]
        needs.append(
            EvidenceNeed(
                need_id="allergen_labeling",
                query=" ".join([*terms, "食品标签 配料表 过敏原 致敏物质"]),
                topics=("allergen", "ingredient_labeling"),
                expected_standard_prefixes=("GB 7718",),
                purpose="support an allergen label interpretation",
            )
        )
    if nutrition:
        terms = [
            value
            for item in nutrition
            for value in (item.constraint, item.matched_text)
            if value
        ]
        needs.append(
            EvidenceNeed(
                need_id="nutrition_labeling",
                query=" ".join([*terms, "营养成分表 标示值 计量单位"]),
                topics=("nutrition_labeling",),
                expected_standard_prefixes=("GB 28050",),
                purpose="support nutrition-label basis and value interpretation",
            )
        )
    if additives:
        terms = [
            item.get("canonical_name") or item.get("raw_name") for item in additives
        ]
        needs.append(
            EvidenceNeed(
                need_id="food_additive",
                query=" ".join(
                    [*filter(None, terms), "GB 2760-2024 食品添加剂使用标准"]
                ),
                topics=("food_additive",),
                expected_standard_prefixes=("GB 2760",),
                purpose="identify the applicable additive standard without asserting compliance",
            )
        )
    if claim and claim.raw_text.strip():
        needs.append(
            EvidenceNeed(
                need_id="nutrition_claim",
                query=f"{claim.raw_text} 无糖 低糖 糖含量 营养声称 表C.1",
                topics=("nutrition_claim",),
                expected_standard_prefixes=("GB 28050",),
                purpose="interpret a confirmed package claim",
            )
        )
    return tuple(needs)


def evidence_supports_need(item: dict, need: EvidenceNeed) -> bool:
    """Require applicable evidence to match the routed topic and standard family."""

    topics = {str(value).casefold() for value in item.get("topics", [])}
    standard = str(item.get("standard_number", ""))
    return bool(topics.intersection(topic.casefold() for topic in need.topics)) and any(
        standard.startswith(prefix) for prefix in need.expected_standard_prefixes
    )


def _is_nutrition(reason_code: str) -> bool:
    return reason_code.startswith(("USER_NUTRITION_", "NUTRITION_", "NUTRIENT_"))


def _additives(normalized_label: dict) -> list[dict]:
    found: list[dict] = []

    def walk(items: list[dict], inside_group: bool = False) -> None:
        for item in items:
            relation = item.get("relation")
            group = relation == "group" or item.get("canonical_name") == "食品添加剂"
            if relation == "additive" or (inside_group and relation != "group"):
                found.append(item)
            walk(item.get("children", []), inside_group or group)

    walk(normalized_label.get("ingredients", []))
    return found
