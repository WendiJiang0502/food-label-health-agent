"""One-way conflicts from source text; never infer absence or certify packaging."""

from datetime import UTC, date, datetime

from food_label_agent.domain.models import UserConstraint
from food_label_agent.domain.types import ConstraintKind
from food_label_agent.ingredients.allergens import evaluate_constraints
from food_label_agent.ingredients.normalization import normalize_ingredients


def ingredient_conflict(fields, constraint):
    normalized = normalize_ingredients(fields.get("ingredients_text") or "")
    if normalized.requires_confirmation:
        return None
    if constraint.kind == "allergy":
        findings = evaluate_constraints(
            normalized,
            [
                UserConstraint(
                    kind=ConstraintKind.ALLERGY,
                    canonical_value=constraint.canonical_value,
                    severity=constraint.severity,
                )
            ],
            allergen_statement=fields.get("allergen_statement") or "",
            ingredients_confirmed=True,
        )
        finding = findings[0]
        if finding.reason_code in {
            "DIRECT_ALLERGEN_INGREDIENT",
            "DIRECT_ALLERGEN_DERIVATIVE",
            "DECLARED_ALLERGEN_STATEMENT",
            "PRECAUTIONARY_ALLERGEN_STATEMENT",
        }:
            return {
                "reason_code": finding.reason_code,
                "matched_text": finding.matched_text,
                "reason": "官网资料存在交叉接触提示，暂排除：" + finding.matched_text
                if finding.reason_code == "PRECAUTIONARY_ALLERGEN_STATEMENT"
                else "官网资料明确列出限制成分，排除：" + finding.matched_text,
            }
    if constraint.kind in {"user_avoidance", "avoid"}:
        # Exact parsed ingredient match, not substring matching of claims or flavour names.
        target = constraint.canonical_value.strip()
        for node in normalized.iter_ingredients():
            if target in {node.raw_name, node.canonical_name}:
                return {
                    "reason_code": "EXPLICIT_AVOIDED_INGREDIENT",
                    "matched_text": node.raw_name,
                    "reason": "官网配料明确列出回避项，排除：" + node.raw_name,
                }
    return None


def field_gap_state(item, field, *, flagged=False):
    """Only a version-bound verified full-label review supports 'not declared'."""
    review = item.get("label_field_reviews", {}).get(field, {})
    try:
        review_date_valid = (
            date.fromisoformat(review.get("reviewed_at", ""))
            <= datetime.now(UTC).date()
        )
    except (ValueError, TypeError):
        review_date_valid = False
    artifact_verified = any(
        a.get("snapshot_id") == review.get("evidence_id")
        and a.get("review_status") == "verified"
        and a.get("artifact_type") in {"packaging_photo", "official_label_artwork"}
        for a in item.get("evidence_assets", [])
        if isinstance(a, dict)
    )
    if not flagged and (
        review.get("status") == "not_declared"
        and review.get("review_status") == "verified"
        and review.get("full_label_checked") is True
        and review.get("source_fingerprint") == item.get("source_fingerprint")
        and review.get("evidence_id")
        and review_date_valid
        and artifact_verified
        and bool(item.get("source_fingerprint"))
    ):
        return "not_declared"
    if flagged or item.get("evidence_assets") or item.get("evidence_asset_urls"):
        return "needs_review"
    return "needs_label"


GAP_LABELS = {
    "needs_label": "待找完整标签",
    "needs_review": "已有证据待核对",
    "not_declared": "已核对完整标签，但未声明该字段；等待新版或厂家补充",
}
