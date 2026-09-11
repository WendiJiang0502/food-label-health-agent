from __future__ import annotations

import pytest

from food_label_agent.ocr.config import OCRSettings
from food_label_agent.ocr.field_parser import OCRLine, parse_food_label_fields
from food_label_agent.ocr.models import BoundingBox


def line(
    text: str,
    confidence: float = 0.98,
    *,
    x: float = 0.1,
    y: float = 0.1,
    width: float = 0.8,
    height: float = 0.06,
) -> OCRLine:
    return OCRLine(
        text=text,
        confidence=confidence,
        bounding_box=BoundingBox(x=x, y=y, width=width, height=height),
    )


def test_parser_keeps_field_level_and_line_level_evidence() -> None:
    fields = parse_food_label_fields(
        [
            line("食品名称：烧烤味薯片", y=0.02),
            line("配料表：小麦粉、白砂糖", y=0.1),
            line("植物油、食用盐", y=0.18),
            line("本产品含有小麦，可能含有花生", y=0.32),
            line("营养成分表 每100克", y=0.48),
            line("净含量：50克", y=0.56),
            line("0糖 不添加蔗糖", y=0.62),
        ],
        OCRSettings(provider="paddle"),
    )

    indexed = {field.name: field for field in fields}
    ingredients = indexed["ingredients"]

    assert indexed["product_name"].raw_text == "食品名称：烧烤味薯片"
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
    assert indexed["nutrition_basis"].raw_text == "每100克"
    assert indexed["net_quantity"].raw_text == "净含量：50克"
    assert indexed["label_claims"].raw_text == "0糖 不添加蔗糖"
    assert indexed["label_claims"].requires_confirmation is True


def test_missing_ingredient_heading_is_unclassified_not_ingredients() -> None:
    fields = parse_food_label_fields(
        [line("小麦粉、白砂糖、食用盐", confidence=0.99)],
        OCRSettings(provider="paddle"),
    )

    assert len(fields) == 1
    assert fields[0].name == "ingredients"
    assert fields[0].label == "配料表（未识别，请手动补充）"
    assert fields[0].raw_text == ""
    assert fields[0].confidence == 0.0
    assert fields[0].requires_confirmation is True


def test_review_only_ingredient_candidate_requires_strong_food_evidence() -> None:
    fields = parse_food_label_fields(
        [
            line("灌肠类", y=0.10),
            line("鸡肉、猪肉、食品添加剂（乳酸钠、卡拉胶）", y=0.14),
            line("白砂糖、食用盐、魔芋粉", y=0.18),
            line("产品标准号：GB/T 20712", y=0.23),
        ],
        OCRSettings(provider="tencentcloud"),
    )

    ingredients = {field.name: field for field in fields}["ingredients"]
    assert ingredients.label == "配料候选（标题未识别，请人工确认）"
    assert "鸡肉、猪肉" in ingredients.raw_text
    assert "产品标准" not in ingredients.raw_text
    assert ingredients.confidence == 0.5


def test_ingredient_word_inside_foreign_sentence_is_not_a_heading() -> None:
    fields = parse_food_label_fields(
        [
            line("校原料吸はそれに準するものを表示しております"),
            line("产品类型：果汁型可吸果冻", y=0.2),
        ],
        OCRSettings(provider="paddle"),
    )

    assert len(fields) == 1
    assert fields[0].name == "ingredients"
    assert fields[0].label == "配料表（未识别，请手动补充）"
    assert fields[0].raw_text == ""


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


def test_ingredient_value_strips_ocr_bullet_noise() -> None:
    fields = parse_food_label_fields(
        [line("配料：·生牛乳", y=0.2)], OCRSettings(provider="paddle")
    )

    ingredients = {field.name: field for field in fields}["ingredients"]
    assert ingredients.raw_text == "生牛乳"


def test_ingredient_heading_can_follow_an_ocr_bullet_inside_a_line() -> None:
    fields = parse_food_label_fields(
        [line("产品类别：饮料·配料：水、浓缩果汁·生产日期：见瓶盖")],
        OCRSettings(provider="tencentcloud"),
    )

    ingredients = {field.name: field for field in fields}["ingredients"]
    assert ingredients.raw_text == "水、浓缩果汁·"


def test_split_ingredient_heading_is_rejoined() -> None:
    fields = parse_food_label_fields(
        [
            line("配", x=0.25, y=0.20, width=0.04, height=0.025),
            line("料：小麦粉、青菜", x=0.29, y=0.20, width=0.32, height=0.025),
            line("饮用水、食用盐", x=0.25, y=0.24, width=0.30, height=0.025),
            line("产品类别：速冻面米食品", x=0.25, y=0.29, width=0.35),
        ],
        OCRSettings(provider="tencentcloud"),
    )

    ingredients = {field.name: field for field in fields}["ingredients"]
    assert ingredients.raw_text == "小麦粉、青菜\n饮用水、食用盐"


def test_allergen_continuation_is_kept_without_adjacent_metadata() -> None:
    fields = parse_food_label_fields(
        [
            line("配料：小麦粉", x=0.2, y=0.1),
            line("致敏物质提示：本产品含有乳制品、含麸", x=0.2, y=0.4, height=0.025),
            line("质的谷物制品、花生制品。", x=0.2, y=0.43, height=0.025),
            line("产品类型：冷冻饮品", x=0.2, y=0.48, height=0.025),
        ],
        OCRSettings(provider="tencentcloud"),
    )

    allergens = {field.name: field for field in fields}["allergen_statement"]
    assert allergens.raw_text.endswith("质的谷物制品、花生制品。")
    assert "产品类型" not in allergens.raw_text


def test_allergen_continuation_keeps_multiple_wrapped_lines() -> None:
    fields = parse_food_label_fields(
        [
            line(
                "致敏物质提示：本产品含有小麦、鸡蛋。该生产设备还加工",
                x=0.20,
                y=0.40,
                height=0.025,
            ),
            line("含有大豆制品、乳制品、芝麻的产品。", x=0.20, y=0.43, height=0.025),
            line("产品标准号：GB/T 20980", x=0.20, y=0.47, height=0.025),
        ],
        OCRSettings(provider="tencentcloud"),
    )

    allergens = {field.name: field for field in fields}["allergen_statement"]
    assert allergens.raw_text.splitlines() == [
        "致敏物质提示：本产品含有小麦、鸡蛋。该生产设备还加工",
        "含有大豆制品、乳制品、芝麻的产品。",
    ]


def test_allergen_continuation_keeps_possible_cross_contact_line() -> None:
    fields = parse_food_label_fields(
        [
            line(
                "过敏原信息：本产品含有大豆、含麸质的谷物和芝麻成分，",
                x=0.12,
                y=0.52,
                height=0.022,
            ),
            line(
                "可能含有花生、坚果、蛋类、鱼类、甲壳纲类动物和乳成分。",
                x=0.12,
                y=0.55,
                height=0.022,
            ),
            line("储存条件：-18℃以下", x=0.12, y=0.59, height=0.022),
        ],
        OCRSettings(provider="tencentcloud"),
    )

    allergens = {field.name: field for field in fields}["allergen_statement"]
    assert "可能含有花生" in allergens.raw_text
    assert "乳成分" in allergens.raw_text
    assert "储存条件" not in allergens.raw_text


def test_allergen_continuation_can_wrap_in_middle_of_word() -> None:
    fields = parse_food_label_fields(
        [
            line("本产品含有乳制品、含麸", x=0.2, y=0.40, height=0.025),
            line("质的谷物、花生、坚", x=0.2, y=0.43, height=0.025),
            line("果及其果仁类制品。", x=0.2, y=0.46, height=0.025),
            line("净含量：68克", x=0.2, y=0.50, height=0.025),
        ],
        OCRSettings(provider="tencentcloud"),
    )

    allergens = {field.name: field for field in fields}["allergen_statement"]
    assert allergens.raw_text.splitlines() == [
        "本产品含有乳制品、含麸",
        "质的谷物、花生、坚",
        "果及其果仁类制品。",
    ]


def test_allergen_continuation_accepts_overlapping_tencent_line_boxes() -> None:
    fields = parse_food_label_fields(
        [
            line(
                "致敏物质提示：本产品含有乳制品，该生产设备还加工含有大豆制品、含麸",
                x=0.174,
                y=0.607,
                width=0.347,
                height=0.071,
            ),
            line(
                "质的谷物制品、花生制品、蛋制品、坚果及其果仁类制品的产品。",
                x=0.176,
                y=0.643,
                width=0.294,
                height=0.064,
            ),
            line(
                "产品类型：组合型雪糕",
                x=0.314,
                y=0.675,
                width=0.108,
                height=0.044,
            ),
        ],
        OCRSettings(provider="tencentcloud"),
    )

    allergens = {field.name: field for field in fields}["allergen_statement"]
    assert "质的谷物制品" in allergens.raw_text
    assert "产品类型" not in allergens.raw_text


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


def test_nutrition_basis_extracts_serving_size_without_nrv_headers() -> None:
    fields = parse_food_label_fields(
        [
            line("配料：果汁、果胶", y=0.1),
            line("每份20克(g) NRV% 每份20克(p) NRV", y=0.4),
        ],
        OCRSettings(provider="paddle"),
    )

    indexed = {field.name: field for field in fields}
    assert indexed["nutrition_basis"].raw_text == "每份20克"


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


def test_inline_product_metadata_is_cut_off_after_ingredients() -> None:
    fields = parse_food_label_fields(
        [line("配料：无花果干(100%)产品类型：水果制品", y=0.2)],
        OCRSettings(provider="paddle"),
    )

    ingredients = {field.name: field for field in fields}["ingredients"]
    assert ingredients.raw_text == "无花果干(100%)"


def test_specification_and_dealer_lines_do_not_enter_ingredients() -> None:
    fields = parse_food_label_fields(
        [
            line("配料：精制盐、碘化钾、亚铁氰化钾", y=0.20),
            line("精制盐(氯化钠以干基计)：≥97.00g/100g", y=0.26),
            line("经销商：某食品公司", y=0.32),
        ],
        OCRSettings(provider="paddle"),
    )

    ingredients = {field.name: field for field in fields}["ingredients"]
    assert ingredients.raw_text == "精制盐、碘化钾、亚铁氰化钾"


def test_ingredient_percentage_lines_are_not_mistaken_for_specifications() -> None:
    fields = parse_food_label_fields(
        [
            line("配料：小麦粉、橙皮（≥9%）", y=0.20),
            line("鸡蛋、白砂糖（添加量≥1%）", y=0.25),
            line("生产日期：见喷码", y=0.31),
        ],
        OCRSettings(provider="tencentcloud"),
    )

    ingredients = {field.name: field for field in fields}["ingredients"]
    assert "橙皮（≥9%）" in ingredients.raw_text
    assert "添加量≥1%" in ingredients.raw_text


def test_heading_followed_by_dealer_details_stays_empty() -> None:
    fields = parse_food_label_fields(
        [line("配料：", y=0.20), line("经销商：某食品公司", y=0.26)],
        OCRSettings(provider="paddle"),
    )

    ingredients = {field.name: field for field in fields}["ingredients"]
    assert ingredients.raw_text == ""


def test_spatial_parser_recovers_out_of_order_wrinkled_label_lines() -> None:
    fields = parse_food_label_fields(
        [
            line("水、食用盐、大豆蛋白、食品添加剂（三", x=0.14, y=0.34),
            line("配料：", x=0.14, y=0.38, width=0.08, height=0.025),
            line("牛肉", x=0.24, y=0.37, width=0.08, height=0.025),
            line("六偏磷酸钠、焦磷酸钠、碳酸氢钠", x=0.14, y=0.40),
            line("柠檬酸、柠檬酸钠、L-苹果酸", x=0.14, y=0.43),
            line("保质期：12个月", x=0.18, y=0.46),
            line("D-异抗坏血酸钠）", x=0.70, y=0.45, width=0.20),
        ],
        OCRSettings(provider="tencentcloud"),
    )

    text = {field.name: field for field in fields}["ingredients"].raw_text
    assert "牛肉" in text
    assert "水、食用盐、大豆蛋白" in text
    assert "D-异抗坏血酸钠" in text
    assert "保质期" not in text


def test_spatial_parser_keeps_parallel_metadata_column_out() -> None:
    fields = parse_food_label_fields(
        [
            line("配料：", x=0.43, y=0.37, width=0.09, height=0.025),
            line("小麦粉、棕榈油、食用盐", x=0.43, y=0.40, width=0.33),
            line("食品添加剂（碳酸钠）", x=0.43, y=0.43, width=0.30),
            line("经销商", x=0.82, y=0.36, width=0.12, height=0.025),
            line("上海某食品有限公司", x=0.82, y=0.40, width=0.16),
            line("过敏原：含有小麦", x=0.43, y=0.47, width=0.32),
        ],
        OCRSettings(provider="tencentcloud"),
    )

    text = {field.name: field for field in fields}["ingredients"].raw_text
    assert "小麦粉、棕榈油、食用盐" in text
    assert "食品添加剂" in text
    assert "上海某食品有限公司" not in text


def test_degraded_heading_can_recover_bread_ingredients() -> None:
    fields = parse_food_label_fields(
        [
            line(
                "配小麦粉白砂糖植物油麸皮，鸡蛋，水、牛奶奶油盐酵母",
                x=0.15,
                y=0.20,
                height=0.025,
            ),
            line("料，每食品添加剂，硫酸钙，抗坏血酸", x=0.15, y=0.23),
            line("酶、磷脂、单硬脂酸甘油酯、脱氢乙酸钠", x=0.15, y=0.26),
            line("生产日期：见封口", x=0.15, y=0.31),
        ],
        OCRSettings(provider="tencentcloud"),
    )

    text = {field.name: field for field in fields}["ingredients"].raw_text
    assert text.startswith("小麦粉白砂糖")
    assert "食品添加剂" in text
    assert "脱氢乙酸钠" in text
    assert "生产日期" not in text
