from __future__ import annotations

from food_label_agent.ingredients.normalization import normalize_ingredients


def test_plain_ingredients_keep_order_and_source_ranges() -> None:
    result = normalize_ingredients("配料：小麦粉、白砂糖、植物油、鸡蛋、牛奶、乳清蛋白")

    assert result.parse_status == "parsed"
    assert [item.raw_name for item in result.ingredients] == [
        "小麦粉",
        "白砂糖",
        "植物油",
        "鸡蛋",
        "牛奶",
        "乳清蛋白",
    ]
    assert result.ingredients[0].canonical_name == "小麦粉"
    assert result.ingredients[0].source_range.start == 3
    assert result.ingredients[-1].evidence_id == "label.ingredients.item.6"


def test_nested_compound_ingredient_builds_traceable_tree() -> None:
    result = normalize_ingredients(
        "小麦粉、复合调味料（白砂糖、食用盐、食品添加剂（乳清蛋白、酵母抽提物））"
    )

    compound = result.ingredients[1]
    additive_group = compound.children[2]
    whey = additive_group.children[0]
    assert compound.category == "复合配料"
    assert [item.raw_name for item in compound.children] == [
        "白砂糖",
        "食用盐",
        "食品添加剂",
    ]
    assert whey.path == (2, 3, 1)
    assert whey.evidence_id == "label.ingredients.item.2.3.1"
    assert whey.source_span == "乳清蛋白"


def test_unclosed_bracket_requires_human_confirmation() -> None:
    result = normalize_ingredients("小麦粉、复合调味料（白砂糖、食用盐")

    assert result.parse_status == "needs_confirmation"
    assert result.requires_confirmation is True
    assert result.issues[0].code == "UNCLOSED_BRACKET"


def test_known_additive_name_split_across_ocr_lines_is_rejoined() -> None:
    result = normalize_ingredients("食品添加剂（柠檬\n酸、碳\n酸钙）")

    children = result.ingredients[0].children
    assert [item.canonical_name for item in children] == ["柠檬酸", "碳酸钙"]
    assert [item.raw_name for item in children] == ["柠檬酸", "碳酸钙"]
    assert {item.normalization_method for item in children} == {
        "dictionary_line_wrap_repair"
    }
    assert result.unknown_terms == ()


def test_original_and_confirmed_text_create_correction_record() -> None:
    result = normalize_ingredients("小麦粉、白砂糖", original_text="小麦粉、白砂糖")
    assert result.corrections == ()

    corrected = normalize_ingredients("小麦粉、白砂糖", original_text="小麦粉、白秒糖")
    assert corrected.corrections[0].actor == "user"
    assert corrected.corrections[0].field == "ingredients"
