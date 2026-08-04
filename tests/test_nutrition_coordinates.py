from food_label_agent.ocr.field_parser import OCRLine
from food_label_agent.ocr.models import BoundingBox, OCRFieldResult
from food_label_agent.ocr.nutrition_coordinates import (
    choose_best_nutrition_table,
    extract_coordinate_nutrition_table,
    has_complete_core_nutrition_table,
)


def line(text: str, x: float, y: float, confidence: float = 0.99) -> OCRLine:
    return OCRLine(
        text=text,
        confidence=confidence,
        bounding_box=BoundingBox(x=x, y=y, width=0.12, height=0.03),
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
        raw_text="每100克 能量271千焦 蛋白质3.2克 脂肪3.6克 钠55毫克 钙100毫克",
        confidence=0.84,
        requires_confirmation=True,
    )

    selected = choose_best_nutrition_table([partial, complete])

    assert selected is not None
    assert selected.name == "nutrition_table"
    assert selected.raw_text == complete.raw_text
    assert selected.requires_confirmation is True


def test_complete_core_table_can_skip_heavy_structure_pipeline() -> None:
    complete = OCRFieldResult(
        name="nutrition_table",
        label="营养成分表",
        raw_text=(
            "每100克 能量271千焦 蛋白质3.2克 脂肪3.6克 "
            "碳水化合物4.9克 钠55毫克"
        ),
        confidence=0.84,
        requires_confirmation=True,
    )

    assert has_complete_core_nutrition_table(complete) is True


def test_complete_names_with_wrong_nutrient_unit_cannot_skip_fallback() -> None:
    mismatched = OCRFieldResult(
        name="nutrition_table",
        label="营养成分表",
        raw_text=(
            "每100克 能量3.2克 蛋白质3.2克 脂肪3.6克 "
            "碳水化合物4.9克 钠55毫克"
        ),
        confidence=0.84,
        requires_confirmation=True,
    )

    assert has_complete_core_nutrition_table(mismatched) is False
