from __future__ import annotations

import pytest

from food_label_agent.domain.models import UserConstraint
from food_label_agent.domain.types import ConstraintKind, RiskLevel
from food_label_agent.ingredients.allergens import (
    ALLERGEN_CATEGORIES,
    evaluate_constraints,
)
from food_label_agent.ingredients.normalization import normalize_ingredients

EXPLICIT_ALIAS_CASES = [
    (key, alias)
    for key, category in ALLERGEN_CATEGORIES.items()
    for alias in category.aliases
]


def allergy(value: str) -> UserConstraint:
    return UserConstraint(
        kind=ConstraintKind.ALLERGY,
        canonical_value=value,
        severity="severe",
    )


@pytest.mark.parametrize(
    ("ingredient", "constraint"),
    [
        ("小麦粉", "gluten"),
        ("虾粉", "crustacean"),
        ("鱼露", "fish"),
        ("鸡蛋", "egg"),
        ("花生酱", "peanut"),
        ("大豆分离蛋白", "soy"),
        ("酪蛋白酸钠", "milk"),
        ("腰果", "tree_nut"),
    ],
)
def test_explicit_allergens_are_never_compatible(
    ingredient: str, constraint: str
) -> None:
    findings = evaluate_constraints(
        normalize_ingredients(f"白砂糖、{ingredient}"), [allergy(constraint)]
    )

    assert findings[0].risk_level is RiskLevel.AVOID
    assert findings[0].matched_text == ingredient
    assert findings[0].evidence_ids == ("label.ingredients.item.2",)


def test_explicit_alias_acceptance_corpus_has_62_terms() -> None:
    """Prevent accidental corpus shrinkage from making recall look better."""

    assert len(EXPLICIT_ALIAS_CASES) == 62


@pytest.mark.parametrize(("constraint", "ingredient"), EXPLICIT_ALIAS_CASES)
def test_every_explicit_alias_is_avoid_as_direct_ingredient(
    constraint: str, ingredient: str
) -> None:
    finding = evaluate_constraints(
        normalize_ingredients(f"白砂糖、{ingredient}"),
        [allergy(constraint)],
    )[0]

    assert finding.risk_level is RiskLevel.AVOID
    assert finding.risk_level is not RiskLevel.COMPATIBLE
    assert finding.matched_text == ingredient
    assert finding.evidence_ids == ("label.ingredients.item.2",)


@pytest.mark.parametrize(("constraint", "ingredient"), EXPLICIT_ALIAS_CASES)
def test_every_explicit_alias_is_avoid_inside_compound_ingredient(
    constraint: str, ingredient: str
) -> None:
    finding = evaluate_constraints(
        normalize_ingredients(f"复合调味料（白砂糖、{ingredient}）"),
        [allergy(constraint)],
    )[0]

    assert finding.risk_level is RiskLevel.AVOID
    assert finding.risk_level is not RiskLevel.COMPATIBLE
    assert finding.matched_text == ingredient
    assert finding.evidence_ids == ("label.ingredients.item.1.2",)


def test_compound_milk_derivative_reports_nested_evidence() -> None:
    finding = evaluate_constraints(
        normalize_ingredients("复合调味料（白砂糖、食用盐、乳清蛋白）"),
        [allergy("milk")],
    )[0]

    assert finding.risk_level is RiskLevel.AVOID
    assert finding.reason_code == "DIRECT_ALLERGEN_DERIVATIVE"
    assert finding.evidence_ids == ("label.ingredients.item.1.3",)


def test_precautionary_statement_is_caution() -> None:
    finding = evaluate_constraints(
        normalize_ingredients("小麦粉、白砂糖"),
        [allergy("peanut")],
        allergen_statement="本产品可能含有花生",
    )[0]

    assert finding.risk_level is RiskLevel.CAUTION
    assert finding.reason_code == "PRECAUTIONARY_ALLERGEN_STATEMENT"
    assert finding.evidence_ids == ("label.allergen_statement",)


def test_precaution_cue_does_not_leak_into_direct_declaration_clause() -> None:
    normalized = normalize_ingredients("白砂糖、食用盐")
    statement = "本产品含有小麦，可能含有花生及坚果制品"

    gluten = evaluate_constraints(
        normalized, [allergy("gluten")], allergen_statement=statement
    )[0]
    peanut = evaluate_constraints(
        normalized, [allergy("peanut")], allergen_statement=statement
    )[0]

    assert gluten.risk_level is RiskLevel.AVOID
    assert gluten.reason_code == "DECLARED_ALLERGEN_STATEMENT"
    assert peanut.risk_level is RiskLevel.CAUTION


def test_ambiguous_name_is_unknown_instead_of_guessed() -> None:
    finding = evaluate_constraints(
        normalize_ingredients("白砂糖、奶味香精"), [allergy("milk")]
    )[0]

    assert finding.risk_level is RiskLevel.UNKNOWN
    assert finding.reason_code == "AMBIGUOUS_INGREDIENT_NAME"
    assert finding.matched_text == "奶味香精"


def test_compatible_wording_is_bounded_to_confirmed_label() -> None:
    finding = evaluate_constraints(
        normalize_ingredients("白砂糖、食用盐"), [allergy("milk")]
    )[0]

    assert finding.risk_level is RiskLevel.COMPATIBLE
    assert "当前已确认标签范围" in finding.explanation
    assert "绝对安全" in finding.explanation
    assert finding.matched_text
    assert finding.evidence_ids


def test_parse_failure_produces_unknown() -> None:
    finding = evaluate_constraints(
        normalize_ingredients("复合调味料（白砂糖、乳清蛋白"), [allergy("milk")]
    )[0]
    assert finding.risk_level is RiskLevel.UNKNOWN
    assert finding.reason_code == "INGREDIENT_PARSE_UNCERTAIN"
