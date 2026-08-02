from __future__ import annotations

import unittest

from food_label_agent.domain.models import LabelField, RiskFinding
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


if __name__ == "__main__":
    unittest.main()
