"""Release checks for evidence-need routing and conclusion support."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from food_label_agent.graph.evidence_plan import EvidenceNeed, evidence_supports_need


@dataclass(frozen=True, slots=True)
class EvidenceRoutingEvaluation:
    case_count: int
    supporting_evidence_accuracy: float
    hard_negative_rejection_rate: float
    evaluation_passed: bool
    release_blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["release_blockers"] = list(self.release_blockers)
        return result


def evaluate_evidence_routing() -> EvidenceRoutingEvaluation:
    allergen = EvidenceNeed(
        need_id="allergen_labeling",
        query="allergen",
        topics=("allergen", "ingredient_labeling"),
        expected_standard_prefixes=("GB 7718",),
        purpose="allergen labeling",
    )
    additive = EvidenceNeed(
        need_id="food_additive",
        query="additive",
        topics=("food_additive",),
        expected_standard_prefixes=("GB 2760",),
        purpose="additive identity",
    )
    claim = EvidenceNeed(
        need_id="nutrition_claim",
        query="claim",
        topics=("nutrition_claim",),
        expected_standard_prefixes=("GB 28050",),
        purpose="nutrition claim",
    )
    cases = (
        (allergen, {"topics": ["allergen"], "standard_number": "GB 7718-2011"}, True),
        (allergen, {"topics": ["allergen"], "standard_number": "GB 28050-2011"}, False),
        (
            allergen,
            {"topics": ["food_additive"], "standard_number": "GB 7718-2011"},
            False,
        ),
        (
            additive,
            {"topics": ["food_additive"], "standard_number": "GB 2760-2024"},
            True,
        ),
        (
            additive,
            {"topics": ["food_additive"], "standard_number": "GB 7718-2011"},
            False,
        ),
        (
            claim,
            {"topics": ["nutrition_claim"], "standard_number": "GB 28050-2011"},
            True,
        ),
        (
            claim,
            {"topics": ["nutrition_labeling"], "standard_number": "GB 28050-2011"},
            False,
        ),
    )
    outcomes = [
        evidence_supports_need(item, need) == expected for need, item, expected in cases
    ]
    negatives = [
        evidence_supports_need(item, need) is False
        for need, item, expected in cases
        if expected is False
    ]
    accuracy = sum(outcomes) / len(outcomes)
    negative_rate = sum(negatives) / len(negatives)
    blockers = []
    if accuracy < 1.0:
        blockers.append("evidence_support_accuracy_regression")
    if negative_rate < 1.0:
        blockers.append("related_but_unsupported_evidence_accepted")
    return EvidenceRoutingEvaluation(
        case_count=len(cases),
        supporting_evidence_accuracy=accuracy,
        hard_negative_rejection_rate=negative_rate,
        evaluation_passed=not blockers,
        release_blockers=tuple(blockers),
    )
