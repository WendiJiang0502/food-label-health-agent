from __future__ import annotations

import unittest

from food_label_agent.graph.topology import MANDATORY_NODES, validate_topology
from food_label_agent.mcp.contracts import MCP_TOOLS, get_tool_contract


class TopologyTests(unittest.TestCase):
    def test_required_topology_is_valid(self) -> None:
        validate_topology()
        self.assertIn("final_safety_gate", MANDATORY_NODES)
        self.assertIn("confirm_label", MANDATORY_NODES)


class MCPContractTests(unittest.TestCase):
    def test_tool_names_are_unique(self) -> None:
        names = [tool.name for tool in MCP_TOOLS]
        self.assertEqual(len(names), len(set(names)))

    def test_safety_tools_are_declared_explicitly(self) -> None:
        contract = get_tool_contract("evaluate_user_constraints")
        self.assertTrue(contract.safety_critical)
        self.assertFalse(contract.implemented)

    def test_unknown_tool_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            get_tool_contract("invented_tool")


if __name__ == "__main__":
    unittest.main()
