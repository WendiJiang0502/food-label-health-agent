from __future__ import annotations

import unittest

from food_label_agent.domain.models import Evidence, LabelField, RiskFinding
from food_label_agent.domain.types import AnalysisStatus, RiskLevel
from food_label_agent.graph.routing import final_safety_gate, route_after_ocr
from food_label_agent.graph.state import create_initial_state


class OCRRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = create_initial_state(
            request_id="request-1",
            jurisdiction="CN",
            applicable_date="2026-08-02",
        )

    def test_missing_ingredients_requires_confirmation(self) -> None:
        self.assertEqual(route_after_ocr(self.state), "confirm_label")

    def test_low_confidence_ingredients_requires_confirmation(self) -> None:
        self.state["label_fields"]["ingredients"] = LabelField(
            name="ingredients",
            raw_text="小麦粉、白砂糖",
            confidence=0.61,
        )
        self.assertEqual(route_after_ocr(self.state), "confirm_label")

    def test_user_confirmation_overrides_low_ocr_confidence(self) -> None:
        self.state["label_fields"]["ingredients"] = LabelField(
            name="ingredients",
            raw_text="小麦粉、白砂糖",
            confidence=0.61,
            confirmed_by_user=True,
        )
        self.assertEqual(route_after_ocr(self.state), "normalize_label")

    def test_reliable_ingredients_routes_to_normalization(self) -> None:
        self.state["label_fields"]["ingredients"] = LabelField(
            name="ingredients",
            raw_text="小麦粉、白砂糖",
            confidence=0.97,
        )
        self.assertEqual(route_after_ocr(self.state), "normalize_label")

    def test_detected_claim_must_be_confirmed_before_health_interpretation(
        self,
    ) -> None:
        self.state["label_fields"]["ingredients"] = LabelField(
            name="ingredients", raw_text="水、赤藓糖醇", confidence=0.99
        )
        self.state["label_fields"]["label_claims"] = LabelField(
            name="label_claims", raw_text="0糖", confidence=0.84
        )

        self.assertEqual(route_after_ocr(self.state), "confirm_label")


class FinalSafetyGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = create_initial_state(
            request_id="request-2",
            jurisdiction="CN",
            applicable_date="2026-08-02",
        )
        self.state["label_fields"]["ingredients"] = LabelField(
            name="ingredients",
            raw_text="花生、白砂糖",
            confidence=0.98,
        )

    def test_avoid_finding_is_preserved_as_warning(self) -> None:
        self.state["risk_findings"].append(
            RiskFinding(
                risk_level=RiskLevel.AVOID,
                constraint="peanut",
                matched_text="花生",
                reason_code="DIRECT_INGREDIENT_MATCH",
                explanation="配料表明确包含花生。",
            )
        )

        result = final_safety_gate(self.state)

        self.assertEqual(result.status, AnalysisStatus.COMPLETED)
        self.assertTrue(result.can_complete)
        self.assertIn("hard_constraint_conflict", result.warnings)

    def test_errors_block_completion(self) -> None:
        self.state["errors"].append("regulatory_store_unavailable")

        result = final_safety_gate(self.state)

        self.assertEqual(result.status, AnalysisStatus.BLOCKED)
        self.assertFalse(result.can_complete)

    def test_missing_critical_field_cannot_complete(self) -> None:
        self.state["label_fields"].clear()

        result = final_safety_gate(self.state)

        self.assertEqual(result.status, AnalysisStatus.NEEDS_CONFIRMATION)
        self.assertFalse(result.can_complete)
        self.assertIn("critical_label_fields_unconfirmed:ingredients", result.unknowns)

    def test_interpretation_cannot_lower_deterministic_avoid_risk(self) -> None:
        self.state["risk_findings"].append(
            RiskFinding(
                risk_level=RiskLevel.AVOID,
                constraint="peanut",
                matched_text="花生",
                reason_code="DIRECT_INGREDIENT_MATCH",
                explanation="配料表明确包含花生。",
                evidence_ids=("label.ingredients.item.1",),
            )
        )
        evidence = _regulatory_evidence()
        self.state["regulatory_evidence"] = [evidence]
        self.state["ingredient_explanations"] = [
            _grounded_explanation(evidence, risk_level="compatible")
        ]

        result = final_safety_gate(self.state)

        self.assertEqual(result.status, AnalysisStatus.BLOCKED)
        self.assertFalse(result.can_complete)
        self.assertIn("interpretation_changed_risk:0", result.violations)

    def test_citation_must_match_retrieved_clause(self) -> None:
        self.state["risk_findings"].append(
            RiskFinding(
                risk_level=RiskLevel.AVOID,
                constraint="peanut",
                matched_text="花生",
                reason_code="DIRECT_INGREDIENT_MATCH",
                explanation="配料表明确包含花生。",
                evidence_ids=("label.ingredients.item.1",),
            )
        )
        evidence = _regulatory_evidence()
        explanation = _grounded_explanation(evidence, risk_level="avoid")
        explanation["citations"][0]["section"] = "不存在的条款"
        self.state["regulatory_evidence"] = [evidence]
        self.state["ingredient_explanations"] = [explanation]

        result = final_safety_gate(self.state)

        self.assertEqual(result.status, AnalysisStatus.BLOCKED)
        self.assertIn("interpretation_citation_mismatch:0", result.violations)

    def test_future_evidence_contamination_is_blocked(self) -> None:
        self.state["regulatory_evidence"] = [
            _regulatory_evidence(
                effective_from="2027-03-16",
                effective_to=None,
            )
        ]

        result = final_safety_gate(self.state)

        self.assertEqual(result.status, AnalysisStatus.BLOCKED)
        self.assertTrue(
            any(
                value.startswith("regulatory_evidence_not_applicable:")
                for value in result.violations
            )
        )

    def test_consistent_threshold_claim_without_regulatory_grounding_is_blocked(
        self,
    ) -> None:
        self.state["claim_interpretations"] = [
            {
                "status": "interpreted",
                "canonical_type": "sugar_free",
                "label_evidence_ids": ["label.claims.item.1"],
                "regulatory_evidence_ids": [],
                "citations": [],
            }
        ]
        self.state["consistency_findings"] = [
            {
                "status": "consistent",
                "claim_type": "sugar_free",
                "label_evidence_ids": ["label.claims.item.1"],
            }
        ]

        result = final_safety_gate(self.state)

        self.assertEqual(result.status, AnalysisStatus.BLOCKED)
        self.assertIn("claim_threshold_conclusion_ungrounded:0", result.violations)

    def test_claim_ingredient_inconsistency_is_preserved_as_warning(self) -> None:
        self.state["consistency_findings"] = [
            {
                "status": "inconsistent",
                "claim_type": "no_sucrose",
                "matched_text": "白砂糖",
            }
        ]

        result = final_safety_gate(self.state)

        self.assertIn("label_claim_inconsistency", result.warnings)


def _regulatory_evidence(
    *,
    effective_from: str = "2012-04-20",
    effective_to: str | None = "2027-03-15",
) -> Evidence:
    return Evidence(
        source_id="reg.cn.gb7718-2011.4.4.3.1.allergens",
        title="食品安全国家标准 预包装食品标签通则",
        jurisdiction="CN",
        section="4.4.3.1 致敏物质",
        source_url="https://www.nhc.gov.cn/example/gb7718.pdf",
        effective_from=effective_from,
        effective_to=effective_to,
        authority_level="A",
        standard_number="GB 7718-2011",
        evidence_text="花生及花生制品属于致敏物质。",
        content_hash="a" * 64,
        page_start=7,
        page_end=7,
    )


def _grounded_explanation(evidence: Evidence, *, risk_level: str) -> dict:
    return {
        "status": "explained",
        "risk_level": risk_level,
        "explanation": "花生明确命中过敏约束。",
        "label_evidence_ids": ["label.ingredients.item.1"],
        "regulatory_evidence_ids": [evidence.source_id],
        "citations": [
            {
                "evidence_id": evidence.source_id,
                "standard_number": evidence.standard_number,
                "section": evidence.section,
                "source_url": evidence.source_url,
                "page_start": evidence.page_start,
                "page_end": evidence.page_end,
                "content_hash": evidence.content_hash,
                "evidence_excerpt": evidence.evidence_text,
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
