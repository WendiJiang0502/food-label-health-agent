"""Framework-neutral declaration of the required workflow topology."""

from __future__ import annotations

MANDATORY_NODES: tuple[str, ...] = (
    "validate_input",
    "extract_label",
    "confirm_label",
    "normalize_label",
    "evaluate_safety",
    "retrieve_regulations",
    "interpret_label",
    "interpret_claims",
    "verify_consistency",
    "final_safety_gate",
)

OPTIONAL_NODES: tuple[str, ...] = (
    "search_alternatives",
    "revalidate_alternatives",
)

EDGES: tuple[tuple[str, str], ...] = (
    ("validate_input", "extract_label"),
    ("confirm_label", "normalize_label"),
    ("normalize_label", "evaluate_safety"),
    ("evaluate_safety", "retrieve_regulations"),
    ("retrieve_regulations", "interpret_label"),
    ("interpret_label", "interpret_claims"),
    ("interpret_claims", "verify_consistency"),
    ("verify_consistency", "final_safety_gate"),
    ("search_alternatives", "revalidate_alternatives"),
    ("revalidate_alternatives", "final_safety_gate"),
)

CONDITIONAL_EDGES: dict[str, tuple[str, ...]] = {
    "extract_label": ("confirm_label", "normalize_label"),
    "verify_consistency": ("search_alternatives", "final_safety_gate"),
}


def validate_topology() -> None:
    """Fail fast when a mandatory safety node becomes disconnected."""

    known_nodes = set(MANDATORY_NODES) | set(OPTIONAL_NODES)
    referenced_nodes = {node for edge in EDGES for node in edge}
    referenced_nodes.update(CONDITIONAL_EDGES)
    referenced_nodes.update(
        node for targets in CONDITIONAL_EDGES.values() for node in targets
    )

    unknown = referenced_nodes - known_nodes
    if unknown:
        raise ValueError(f"Topology references unknown nodes: {sorted(unknown)}")

    if "final_safety_gate" not in known_nodes:
        raise ValueError("The final safety gate is mandatory")

    incoming_to_gate = [
        source for source, target in EDGES if target == "final_safety_gate"
    ]
    incoming_to_gate.extend(
        source
        for source, targets in CONDITIONAL_EDGES.items()
        if "final_safety_gate" in targets
    )
    if not incoming_to_gate:
        raise ValueError("The final safety gate must be reachable")
