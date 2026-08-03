from food_label_agent.evaluation.ocr import (
    character_error_rate,
    compare_fields,
    detect_image_type,
    numeric_token_accuracy,
    token_recall,
)


def test_image_type_comes_from_file_signature_not_filename() -> None:
    assert detect_image_type(b"\xff\xd8\xffpayload") == (".jpg", "image/jpeg")
    assert detect_image_type(b"not-an-image") is None


def test_character_error_rate_ignores_spacing_and_case() -> None:
    assert character_error_rate("Milk 100 g", "milk100g") == 0
    assert character_error_rate("小麦粉", "小麦") == 1 / 3


def test_safety_metrics_are_explicit_about_missing_expected_tokens() -> None:
    assert token_recall(["小麦", "花生"], "本品含有小麦") == 0.5
    assert numeric_token_accuracy("每100克，蛋白质5.2克", "每100g 蛋白质5.2g") == 1
    assert numeric_token_accuracy("没有数字", "100") is None


def test_compare_fields_reports_field_allergen_and_number_metrics() -> None:
    metrics = compare_fields(
        {
            "fields": {
                "ingredients": "小麦粉、白砂糖",
                "nutrition_basis": "每100克",
            },
            "allergens": ["小麦", "花生"],
        },
        {"ingredients": "小麦粉、白砂糖", "nutrition_basis": "每100g"},
    )

    assert metrics["field_cer"]["ingredients"] == 0
    assert metrics["allergen_recall"] == 0.5
    assert metrics["numeric_token_accuracy"] == 1
