from food_label_agent.alternatives.category import suggest_product_category


def test_category_suggestion_uses_confirmed_label_facts() -> None:
    result = suggest_product_category(
        {"product_name": "燕麦饼干", "ingredients": "小麦粉、燕麦、白砂糖"}
    )

    assert result["status"] == "automatic"
    assert result["category"] == "biscuit"
    assert result["requires_confirmation"] is False
    assert result["matched_terms"][0] == "饼干"
    assert result["substitute_categories"] == [
        "biscuit",
        "snack",
    ]


def test_category_suggestion_expands_only_to_a_genuine_same_use_scope() -> None:
    breakfast = suggest_product_category(
        {"product_name": "全麦吐司面包", "ingredients": "小麦粉、酵母"}
    )
    quick_meal = suggest_product_category(
        {"product_name": "红烧牛肉方便面", "ingredients": "小麦粉、面饼"}
    )

    assert breakfast["substitute_categories"] == ["bread", "breakfast_cereal"]
    assert quick_meal["substitute_categories"] == [
        "instant_noodles",
        "prepared_meal",
    ]


def test_category_suggestion_does_not_guess_without_evidence() -> None:
    result = suggest_product_category({"ingredients": "小麦粉、水、白砂糖、食用盐"})

    assert result["status"] == "unknown"
    assert result["category"] is None


def test_category_suggestion_covers_condiments() -> None:
    result = suggest_product_category(
        {"product_name": "黑豆酱油", "ingredients": "水、非转基因黑豆、食用盐"}
    )

    assert result["category"] == "sauce_condiment"


def test_category_suggestion_covers_daily_nuts() -> None:
    result = suggest_product_category(
        {"product_name": "每日坚果", "ingredients": "核桃仁、腰果仁"}
    )

    assert result["status"] == "automatic"
    assert result["category"] == "snack"


def test_category_suggestion_covers_light_soy_sauce() -> None:
    result = suggest_product_category(
        {"product_name": "薄盐生抽", "ingredients": "水、大豆、小麦"}
    )

    assert result["status"] == "automatic"
    assert result["category"] == "sauce_condiment"


def test_category_suggestion_can_infer_biscuit_from_confirmed_formula() -> None:
    result = suggest_product_category(
        {
            "product_name": "快乐河马1条装",
            "ingredients": "白砂糖、植物油、小麦粉、碳酸氢铵、食用盐",
        }
    )

    assert result["status"] == "automatic"
    assert result["category"] == "biscuit"
    assert result["requires_confirmation"] is False
    assert result["substitute_categories"] == [
        "biscuit",
        "snack",
        "confectionery",
    ]
