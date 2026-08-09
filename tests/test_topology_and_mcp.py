from __future__ import annotations

import unittest

from food_label_agent.graph.topology import MANDATORY_NODES, validate_topology
from food_label_agent.mcp.contracts import MCP_TOOLS, get_tool_contract


class TopologyTests(unittest.TestCase):
    def test_required_topology_is_valid(self) -> None:
        validate_topology()
        self.assertIn("final_safety_gate", MANDATORY_NODES)
        self.assertIn("confirm_label", MANDATORY_NODES)
        self.assertIn("interpret_claims", MANDATORY_NODES)
        self.assertIn("verify_consistency", MANDATORY_NODES)


class MCPContractTests(unittest.TestCase):
    def test_tool_names_are_unique(self) -> None:
        names = [tool.name for tool in MCP_TOOLS]
        self.assertEqual(len(names), len(set(names)))

    def test_safety_tools_are_declared_explicitly(self) -> None:
        contract = get_tool_contract("evaluate_user_constraints")
        self.assertTrue(contract.safety_critical)
        self.assertTrue(contract.implemented)

    def test_normalization_tool_is_implemented(self) -> None:
        contract = get_tool_contract("normalize_food_label")
        self.assertTrue(contract.implemented)

    def test_regulation_search_tool_is_implemented_and_safety_critical(self) -> None:
        contract = get_tool_contract("search_food_regulations")
        self.assertTrue(contract.implemented)
        self.assertTrue(contract.safety_critical)

    def test_ingredient_explanation_tool_is_implemented(self) -> None:
        contract = get_tool_contract("explain_ingredient")
        self.assertTrue(contract.implemented)

    def test_claim_tools_are_implemented(self) -> None:
        self.assertTrue(get_tool_contract("interpret_label_claim").implemented)
        consistency = get_tool_contract("verify_label_consistency")
        self.assertTrue(consistency.implemented)
        self.assertTrue(consistency.safety_critical)

    def test_unknown_tool_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            get_tool_contract("invented_tool")


if __name__ == "__main__":
    unittest.main()
