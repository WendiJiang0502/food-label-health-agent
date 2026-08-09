from __future__ import annotations

import unittest

from food_label_agent.domain.models import ImageInput, UserConstraint
from food_label_agent.domain.types import AnalysisStatus, ConstraintKind, WorkflowStage
from food_label_agent.graph.state import create_initial_state


class InitialStateTests(unittest.TestCase):
    def test_initial_state_has_complete_collections_and_audit_event(self) -> None:
        state = create_initial_state(
            request_id="request-1",
            jurisdiction="CN",
            applicable_date="2026-08-02",
            images=[ImageInput(uri="memory://label.jpg", side="ingredients")],
            user_constraints=[
                UserConstraint(
                    kind=ConstraintKind.ALLERGY,
                    canonical_value="peanut",
                    severity="severe",
                )
            ],
        )

        self.assertEqual(state["status"], AnalysisStatus.RECEIVED)
        self.assertEqual(state["stage"], WorkflowStage.INPUT_VALIDATION)
        self.assertEqual(len(state["images"]), 1)
        self.assertEqual(len(state["user_constraints"]), 1)
        self.assertEqual(state["risk_findings"], [])
        self.assertEqual(state["tool_trace"], [])
        self.assertEqual(state["react_budget"]["tool_calls_used"], 0)
        self.assertEqual(state["audit_events"][0].event_type, "state_created")


if __name__ == "__main__":
    unittest.main()
