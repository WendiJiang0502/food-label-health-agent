from food_label_agent.evaluation.ocr import compare_fields
from food_label_agent.ocr.normalization import (
    NutritionBasis,
    normalize_nutrition_text,
    parse_nutrition_basis,
)


def test_basis_parser_canonicalizes_chinese_and_latin_units() -> None:
    assert parse_nutrition_basis("每100克") == NutritionBasis(100, "g")
    assert parse_nutrition_basis("每 100 G") == NutritionBasis(100, "g")
    assert parse_nutrition_basis("每100毫升") == NutritionBasis(100, "ml")
    assert parse_nutrition_basis("按每份") is None


def test_nutrition_text_normalizes_units_but_raw_input_is_unchanged() -> None:
    raw = "能量 1091千焦；钠 389毫克"

    assert normalize_nutrition_text(raw) == "能量1091kj;钠389mg"
    assert raw == "能量 1091千焦；钠 389毫克"


def test_field_cer_treats_equivalent_basis_units_as_equal() -> None:
    metrics = compare_fields(
        {"fields": {"nutrition_basis": "每100克"}},
        {"nutrition_basis": "每100g"},
    )

    assert metrics["field_cer"]["nutrition_basis"] == 0
