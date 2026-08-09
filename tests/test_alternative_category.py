from food_label_agent.alternatives.category import suggest_product_category


def test_category_suggestion_uses_confirmed_label_facts() -> None:
    result = suggest_product_category(
        {"product_name": "燕麦饼干", "ingredients": "小麦粉、燕麦、白砂糖"}
    )

    assert result["status"] == "suggested"
    assert result["category"] == "biscuit"
    assert result["requires_confirmation"] is True
    assert set(result["matched_terms"]) == {"饼干", "小麦粉"}


def test_category_suggestion_does_not_guess_without_evidence() -> None:
    result = suggest_product_category({"ingredients": "白砂糖、食用盐"})

    assert result["status"] == "unknown"
    assert result["category"] is None
