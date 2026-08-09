"""Deterministic interpretation and consistency checks for label claims."""

from .service import interpret_claim, verify_claim_consistency

__all__ = ["interpret_claim", "verify_claim_consistency"]
