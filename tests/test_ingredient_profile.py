from food_label_agent.alternatives.ingredient_profile import ingredient_profile
from food_label_agent.alternatives.ingredient_screening import ingredient_conflict
from food_label_agent.ingredients.api_models import ConstraintInput


def profile(text, **kwargs):
    return ingredient_profile(
        {
            "extracted_fields": {"ingredients_text": text},
            "source_url": "https://example.com/label",
            "source_fingerprint": "v1",
            **kwargs,
        }
    )


def test_nested_sugar_polyol_and_egg_are_separate():
    p = profile("生牛乳、果酱(白砂糖、赤藓糖醇)、蛋黄粉、甜菊糖苷")
    assert {x["group"] for x in p["observations"]} == {
        "milk_sources",
        "sugar_ingredients",
        "polyols",
        "egg_sources",
        "sweeteners",
    }
    assert all(
        x["source_span"] and x["source_fingerprint"] == "v1" for x in p["observations"]
    )
    assert p["total_sugars_inferred"] is False


def test_claims_are_not_positive_or_negative_ingredient_evidence():
    p = profile("不添加白砂糖、乳酸菌、可可脂")
    assert p["observations"] == [] and p["negative_claims_supported"] is False
    assert profile("")["status"] == "missing"


def test_flagged_ingredient_evidence_stays_draft():
    p = profile("白砂糖", source_quality_flags=["配料冲突"])
    assert p["observations"][0]["status"] == "needs_review"


def test_egg_powder_and_milk_derivatives_conflict():
    for text, key in [("蛋黄粉", "egg"), ("稀奶油", "milk"), ("乳清蛋白粉", "milk")]:
        r = ingredient_conflict(
            {"ingredients_text": text}, ConstraintInput(canonical_value=key)
        )
        assert r and r["reason_code"] == "DIRECT_ALLERGEN_DERIVATIVE"
