from food_label_agent.ocr.nutrition import validate_nutrition_table


def test_valid_core_nutrition_rows_have_no_issues() -> None:
    table = validate_nutrition_table(
        [
            ["营养成分表", "每100克", "NRV%"],
            ["能量", "1200 kJ", "14%"],
            ["蛋白质", "8.0 g", "13%"],
            ["钠", "320 mg", "16%"],
        ]
    )
    assert table.issues == []


def test_missing_basis_value_and_ambiguous_digit_require_review() -> None:
    table = validate_nutrition_table(
        [["营养成分表"], ["蛋白质"], ["钠", "3O0 mg", "15%"]]
    )
    codes = {issue.code for issue in table.issues}
    blocking = {issue.code for issue in table.issues if issue.severity == "blocking"}

    assert "NUTRITION_BASIS_MISSING" in codes
    assert blocking == {"NUTRIENT_VALUE_MISSING", "AMBIGUOUS_NUMERIC_GLYPH"}


def test_wrong_nutrient_unit_is_blocking() -> None:
    table = validate_nutrition_table([["营养成分表", "每100克"], ["蛋白质", "31千焦"]])

    assert {issue.code for issue in table.issues if issue.severity == "blocking"} == {
        "NUTRIENT_UNIT_MISSING"
    }
