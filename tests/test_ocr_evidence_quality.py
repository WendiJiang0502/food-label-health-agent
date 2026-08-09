from food_label_agent.ocr.evidence_quality import assess_ocr_evidence
from food_label_agent.ocr.models import (
    BoundingBox,
    NutritionTableData,
    OCRFieldResult,
    OCRLineEvidence,
)


def test_unclassified_text_never_satisfies_ingredient_evidence() -> None:
    report = assess_ocr_evidence(
        [
            OCRFieldResult(
                name="unclassified_text",
                label="未定位到配料表",
                raw_text="产品名称 面包 生产日期 2026-01-01",
                confidence=0.5,
                requires_confirmation=True,
            )
        ]
    )

    assert report.status == "needs_confirmation"
    assert [issue.code for issue in report.issues] == ["INGREDIENT_HEADING_NOT_FOUND"]


def test_single_ingredient_food_is_not_rejected_for_being_short() -> None:
    report = assess_ocr_evidence(
        [
            OCRFieldResult(
                name="ingredients",
                label="配料表",
                raw_text="生牛乳",
                confidence=0.99,
                requires_confirmation=True,
            )
        ]
    )

    assert report.status == "passed"


def test_empty_manual_ingredient_field_is_blocking() -> None:
    report = assess_ocr_evidence(
        [
            OCRFieldResult(
                name="ingredients",
                label="配料表（未识别，请手动补充）",
                raw_text="",
                confidence=0.0,
                requires_confirmation=True,
            )
        ]
    )

    assert report.status == "needs_confirmation"
    assert report.issues[0].code == "INGREDIENT_TEXT_MISSING"


def test_contaminated_or_unbalanced_ingredients_are_blocking() -> None:
    report = assess_ocr_evidence(
        [
            OCRFieldResult(
                name="ingredients",
                label="配料表",
                raw_text="小麦粉、白砂糖（植物油、食盐 生产日期2026-01-01",
                confidence=0.96,
                requires_confirmation=False,
            )
        ]
    )

    assert report.status == "needs_confirmation"
    assert {issue.code for issue in report.issues} == {
        "INGREDIENT_BOUNDARY_CONTAMINATED",
        "INGREDIENT_BRACKET_MISMATCH",
    }


def test_large_gap_between_ingredient_lines_requests_review() -> None:
    report = assess_ocr_evidence(
        [
            OCRFieldResult(
                name="ingredients",
                label="配料表",
                raw_text="小麦粉、白砂糖\n植物油、食盐",
                confidence=0.92,
                requires_confirmation=True,
                evidence_lines=[
                    OCRLineEvidence(
                        text="小麦粉、白砂糖",
                        confidence=0.95,
                        bounding_box=BoundingBox(x=0.1, y=0.1, width=0.8, height=0.04),
                    ),
                    OCRLineEvidence(
                        text="植物油、食盐",
                        confidence=0.90,
                        bounding_box=BoundingBox(x=0.1, y=0.30, width=0.8, height=0.04),
                    ),
                ],
            )
        ]
    )

    assert report.status == "review_recommended"
    assert report.issues[0].code == "INGREDIENT_LINES_FRAGMENTED"


def test_detected_basis_without_structured_table_is_explicit() -> None:
    report = assess_ocr_evidence(
        [
            OCRFieldResult(
                name="ingredients",
                label="配料表",
                raw_text="生牛乳、白砂糖、乳酸菌",
                confidence=0.90,
                requires_confirmation=True,
            ),
            OCRFieldResult(
                name="nutrition_basis",
                label="营养标示口径",
                raw_text="每100克",
                confidence=0.99,
                requires_confirmation=False,
            ),
        ]
    )

    assert report.status == "needs_confirmation"
    assert report.issues[0].code == "NUTRITION_TABLE_NOT_STRUCTURED"


def test_partial_nutrition_table_never_passes_evidence_gate() -> None:
    report = assess_ocr_evidence(
        [
            OCRFieldResult(
                name="ingredients",
                label="配料表",
                raw_text="牛肉、水、食用盐",
                confidence=0.84,
                requires_confirmation=True,
            ),
            OCRFieldResult(
                name="nutrition_basis",
                label="营养标示口径",
                raw_text="每100克",
                confidence=0.99,
                requires_confirmation=False,
            ),
            OCRFieldResult(
                name="nutrition_table",
                label="营养成分表",
                raw_text="每100克 能量691千焦 蛋白质11.8克",
                confidence=0.84,
                requires_confirmation=True,
                nutrition_table=NutritionTableData(
                    rows=[["能量", "691千焦"], ["蛋白质", "11.8克"]]
                ),
            ),
        ]
    )

    assert report.status == "needs_confirmation"
    assert report.issues[0].code == "NUTRITION_CORE_FIELDS_INCOMPLETE"


def test_partial_table_without_separate_basis_never_passes_evidence_gate() -> None:
    report = assess_ocr_evidence(
        [
            OCRFieldResult(
                name="ingredients",
                label="配料表",
                raw_text="小麦粉、食用盐",
                confidence=0.84,
                requires_confirmation=True,
            ),
            OCRFieldResult(
                name="nutrition_table",
                label="营养成分表",
                raw_text="项目 口径待确认 能量271千焦 钠55毫克",
                confidence=0.50,
                requires_confirmation=True,
            ),
        ]
    )

    assert report.status == "needs_confirmation"
    assert report.issues[0].code == "NUTRITION_CORE_FIELDS_INCOMPLETE"


def test_trailing_delimiter_or_single_character_fragment_is_blocking() -> None:
    for ingredients in ("大米、黄豆、食用盐，", "水、黑豆、小麦、食"):
        report = assess_ocr_evidence(
            [
                OCRFieldResult(
                    name="ingredients",
                    label="配料表",
                    raw_text=ingredients,
                    confidence=0.84,
                    requires_confirmation=True,
                )
            ]
        )

        assert report.status == "needs_confirmation"
        assert "INGREDIENT_TEXT_SUSPECTED_TRUNCATION" in {
            issue.code for issue in report.issues
        }
