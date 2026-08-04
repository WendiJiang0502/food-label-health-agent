from __future__ import annotations

import pytest

from food_label_agent.ocr.config import OCRSettings
from food_label_agent.ocr.field_parser import OCRLine, parse_food_label_fields
from food_label_agent.ocr.models import BoundingBox


def line(
    text: str,
    confidence: float = 0.98,
    *,
    y: float = 0.1,
) -> OCRLine:
    return OCRLine(
        text=text,
        confidence=confidence,
        bounding_box=BoundingBox(x=0.1, y=y, width=0.8, height=0.06),
    )


def test_parser_keeps_field_level_and_line_level_evidence() -> None:
    fields = parse_food_label_fields(
        [
            line("配料表：小麦粉、白砂糖", y=0.1),
            line("植物油、食用盐", y=0.18),
            line("本产品含有小麦，可能含有花生", y=0.32),
            line("营养成分表 每100克", y=0.48),
            line("0糖 不添加蔗糖", y=0.62),
        ],
        OCRSettings(provider="paddle"),
    )

    indexed = {field.name: field for field in fields}
    ingredients = indexed["ingredients"]

    assert ingredients.raw_text == "小麦粉、白砂糖\n植物油、食用盐"
    assert ingredients.requires_confirmation is True
    assert [item.text for item in ingredients.evidence_lines] == [
        "小麦粉、白砂糖",
        "植物油、食用盐",
    ]
    assert ingredients.bounding_box is not None
    assert ingredients.bounding_box.y == pytest.approx(0.1)
    assert ingredients.bounding_box.height == pytest.approx(0.14)
    assert indexed["allergen_statement"].raw_text.endswith("可能含有花生")
    assert indexed["nutrition_basis"].raw_text == "营养成分表 每100克"
    assert indexed["label_claims"].raw_text == "0糖 不添加蔗糖"
    assert indexed["label_claims"].requires_confirmation is True


def test_missing_ingredient_heading_is_unclassified_not_ingredients() -> None:
    fields = parse_food_label_fields(
        [line("小麦粉、白砂糖、食用盐", confidence=0.99)],
        OCRSettings(provider="paddle"),
    )

    assert len(fields) == 1
    assert fields[0].name == "unclassified_text"
    assert fields[0].label == "未定位到配料表"
    assert fields[0].raw_text == "小麦粉、白砂糖、食用盐"
    assert fields[0].confidence == 0.50
    assert fields[0].requires_confirmation is True


def test_allergen_wording_without_heading_is_detected() -> None:
    fields = parse_food_label_fields(
        [
            line("配料：燕麦片、可可粉"),
            line("含有麸质的谷物及大豆制品", confidence=0.92),
        ],
        OCRSettings(provider="paddle"),
    )

    indexed = {field.name: field for field in fields}
    assert indexed["ingredients"].raw_text == "燕麦片、可可粉"
    assert indexed["allergen_statement"].requires_confirmation is True
    assert indexed["allergen_statement"].evidence_lines[0].confidence == 0.92


def test_repeated_package_headings_do_not_enter_ingredient_content() -> None:
    fields = parse_food_label_fields(
        [
            line("配料：生牛乳", y=0.2),
            line("配料", y=0.8),
            line("营养成分表", y=0.9),
        ],
        OCRSettings(provider="paddle"),
    )

    ingredients = {field.name: field for field in fields}["ingredients"]
    assert ingredients.raw_text == "生牛乳"


def test_nutrition_basis_excludes_heading_and_deduplicates_packages() -> None:
    fields = parse_food_label_fields(
        [
            line("营养成分表", y=0.1),
            line("每100克", confidence=0.97, y=0.2),
            line("营养成分表", y=0.6),
            line("每100克", confidence=0.99, y=0.7),
        ],
        OCRSettings(provider="paddle"),
    )

    indexed = {field.name: field for field in fields}
    assert indexed["nutrition_basis"].raw_text == "每100克"
    assert indexed["nutrition_basis"].confidence == 0.99


def test_distant_product_name_is_not_appended_to_inline_ingredients() -> None:
    fields = parse_food_label_fields(
        [
            line("配料：生牛乳", y=0.20),
            line("纯牛奶", y=0.55),
            line("每100克", y=0.70),
        ],
        OCRSettings(provider="paddle"),
    )

    ingredients = {field.name: field for field in fields}["ingredients"]
    assert ingredients.raw_text == "生牛乳"
