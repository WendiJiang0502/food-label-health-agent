from food_label_agent.evaluation.boohee_pilot import (
    assess_detail,
    stage_official_products,
)


def test_zero_and_recipe_ingredients_cannot_become_verified_labels():
    result = assess_detail(
        {
            "code": 0,
            "data": {
                "ingredients": [
                    {"key": "sugar", "value": 0, "unit": "g"},
                    {"key": "natrium", "value": 46, "unit": "mg"},
                ],
                "materials": {"foods": [{"name": "牛奶"}]},
            },
        }
    )
    assert result["observations"][0]["status"] == "zero_unverified"
    assert result["observations"][1]["status"] == "source_unverified"
    assert result["ingredients_text"] is None
    assert not result["recommendation_eligible"]


def test_official_source_preserves_missing_sugar_and_flags_conflicting_flavour():
    result = stage_official_products(
        [
            {
                "id": 1,
                "list": [
                    {
                        "name": "草莓酸奶(230克)",
                        "ingredients": "生牛乳、葡萄蓝莓果浆",
                        "component": [{"name": "碳水化合物", "value": "12克"}],
                    }
                ],
            }
        ],
        captured_at="2026-10-04",
        source_hash="hash",
    )[0]
    assert result["sugars"] is None
    assert result["specification"] == "230克"
    assert "flavour_ingredient_conflict" in result["missing_or_conflicting"]
    assert result["barcode"] is None
    assert not result["recommendation_eligible"]
