from food_label_agent.ocr.field_parser import OCRLine
from food_label_agent.ocr.models import BoundingBox, OCRFieldResult
from food_label_agent.ocr.nutrition_coordinates import (
    choose_best_nutrition_table,
    extract_coordinate_nutrition_table,
    has_complete_core_nutrition_table,
)


def line(
    text: str,
    x: float,
    y: float,
    confidence: float = 0.99,
    *,
    width: float = 0.12,
    height: float = 0.03,
) -> OCRLine:
    return OCRLine(
        text=text,
        confidence=confidence,
        bounding_box=BoundingBox(x=x, y=y, width=width, height=height),
    )


def test_coordinate_rows_recover_nutrient_value_relationships() -> None:
    field = extract_coordinate_nutrition_table(
        [
            line("每100克", 0.50, 0.10),
            line("能量", 0.20, 0.20),
            line("271千焦", 0.50, 0.205),
            line("蛋白质", 0.20, 0.25),
            line("3.2克", 0.50, 0.255),
            line("钠", 0.20, 0.30),
            line("55毫克", 0.50, 0.302),
            line("生产日期2026", 0.20, 0.50),
        ]
    )

    assert field is not None
    assert field.name == "nutrition_table"
    assert field.requires_confirmation is True
    assert field.nutrition_table is not None
    assert field.nutrition_table.rows == [
        ["项目", "每100克"],
        ["能量", "271千焦"],
        ["蛋白质", "3.2克"],
        ["钠", "55毫克"],
    ]
    assert has_complete_core_nutrition_table(field) is False


def test_vertical_or_distant_values_are_not_joined_into_rows() -> None:
    assert (
        extract_coordinate_nutrition_table(
            [
                line("蛋白质", 0.20, 0.20),
                line("3.2克", 0.21, 0.50),
                line("脂肪", 0.20, 0.25),
                line("3.6克", 0.90, 0.25),
            ]
        )
        is None
    )


def test_best_table_prefers_more_complete_nutrient_coverage() -> None:
    partial = OCRFieldResult(
        name="nutrition_table_1",
        label="结构化表格",
        raw_text="每100克 能量271千焦 蛋白质3.2克",
        confidence=0.99,
        requires_confirmation=False,
    )
    complete = OCRFieldResult(
        name="nutrition_table_ocr",
        label="坐标表格",
        raw_text=(
            "每100克 能量271千焦 蛋白质3.2克 脂肪3.6克 "
            "碳水化合物4.9克 钠55毫克 钙100毫克"
        ),
        confidence=0.84,
        requires_confirmation=True,
    )

    selected = choose_best_nutrition_table([partial, complete])

    assert selected is not None
    assert selected.name == "nutrition_table"
    assert selected.raw_text == complete.raw_text
    assert selected.requires_confirmation is True


def test_incomplete_table_is_visibly_downgraded() -> None:
    partial = OCRFieldResult(
        name="nutrition_table_1",
        label="结构化表格",
        raw_text="每100克 能量271千焦 蛋白质3.2克",
        confidence=0.97,
        requires_confirmation=False,
    )

    selected = choose_best_nutrition_table([partial])

    assert selected is not None
    assert selected.confidence == 0.5
    assert "识别不完整" in selected.label
    assert selected.requires_confirmation is True


def test_complete_core_table_can_skip_heavy_structure_pipeline() -> None:
    complete = OCRFieldResult(
        name="nutrition_table",
        label="营养成分表",
        raw_text=("每100克 能量271千焦 蛋白质3.2克 脂肪3.6克 碳水化合物4.9克 钠55毫克"),
        confidence=0.84,
        requires_confirmation=True,
    )

    assert has_complete_core_nutrition_table(complete) is True


def test_complete_names_with_wrong_nutrient_unit_cannot_skip_fallback() -> None:
    mismatched = OCRFieldResult(
        name="nutrition_table",
        label="营养成分表",
        raw_text=("每100克 能量3.2克 蛋白质3.2克 脂肪3.6克 碳水化合物4.9克 钠55毫克"),
        confidence=0.84,
        requires_confirmation=True,
    )

    assert has_complete_core_nutrition_table(mismatched) is False


def test_value_cannot_be_reused_or_assigned_to_wrong_nutrient_unit() -> None:
    field = extract_coordinate_nutrition_table(
        [
            line("每份", 0.50, 0.10),
            line("能量", 0.20, 0.20),
            line("31千焦", 0.50, 0.20),
            line("蛋白质", 0.20, 0.205),
            line("脂肪", 0.20, 0.30),
            line("0克", 0.50, 0.30),
        ]
    )

    assert field is not None
    assert "能量\t31千焦" in field.raw_text
    assert "蛋白质\t31千焦" not in field.raw_text
    assert field.raw_text.count("31千焦") == 1


def test_row_order_prevents_folded_label_from_stealing_next_value() -> None:
    field = extract_coordinate_nutrition_table(
        [
            line("每100克", 0.70, 0.10),
            line("蛋白质", 0.20, 0.20, height=0.05),
            line("11.8克", 0.50, 0.20),
            line("脂肪", 0.20, 0.29, height=0.10),
            line("12.7克", 0.50, 0.25),
            line("1.2克", 0.50, 0.30),
        ]
    )

    assert field is not None
    assert "蛋白质\t11.8克" in field.raw_text
    assert "脂肪\t12.7克" in field.raw_text
    assert "脂肪\t1.2克" not in field.raw_text


def test_split_number_and_unit_are_joined_on_same_row() -> None:
    field = extract_coordinate_nutrition_table(
        [
            line("每100克", 0.50, 0.10),
            line("能量", 0.10, 0.20),
            line("1091千焦", 0.40, 0.20),
            line("钠", 0.10, 0.30),
            line("389", 0.40, 0.30),
            line("mg", 0.53, 0.30, width=0.06),
        ]
    )

    assert field is not None
    assert "钠\t389mg" in field.raw_text


def test_inline_multilingual_nutrition_row_is_recovered() -> None:
    field = extract_coordinate_nutrition_table(
        [
            line("每100克", 0.50, 0.10),
            line("能量 energy 1380千焦(kJ)", 0.10, 0.20, width=0.60),
            line(
                "碳水化合物/carbohydrate 57.0克(g)",
                0.10,
                0.30,
                width=0.70,
            ),
        ]
    )

    assert field is not None
    assert "能量\t1380千焦" in field.raw_text
    assert "碳水化合物\t57.0克" in field.raw_text


def test_milligrams_cannot_match_gram_nutrients_or_adjacent_rows() -> None:
    field = extract_coordinate_nutrition_table(
        [
            line("每100克", 0.50, 0.10),
            line("能量", 0.10, 0.20),
            line("271千焦", 0.40, 0.20),
            line("脂肪 53毫克", 0.10, 0.30, width=0.50),
            line("碳水化合物", 0.10, 0.40),
            line("43.68", 0.40, 0.40),
            line("钠", 0.10, 0.45),
            line("389", 0.40, 0.45),
            line("mg", 0.53, 0.45, width=0.06),
        ]
    )

    assert field is not None
    assert "钠\t389mg" in field.raw_text
    assert "脂肪\t53毫克" not in field.raw_text
    assert "碳水化合物\t389mg" not in field.raw_text
