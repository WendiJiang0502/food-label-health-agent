from food_label_agent.ocr.config import OCRSettings
from food_label_agent.ocr.ppstructure_provider import (
    PPStructureNutritionParser,
    parse_table_html,
)

TABLE_HTML = """
<table>
  <tr><th>项目</th><th>每100克</th><th>NRV%</th></tr>
  <tr><td>能量</td><td>1200 kJ</td><td>14%</td></tr>
  <tr><td>蛋白质</td><td>8.0 g</td><td>13%</td></tr>
</table>
"""


class FakeStructureEngine:
    def predict(self, image_path: str):
        assert image_path == "/tmp/label.jpg"
        return [
            {
                "res": {
                    "table_res_list": [
                        {
                            "pred_html": TABLE_HTML,
                            "table_ocr_pred": {"rec_scores": [0.98, 0.96, 0.97]},
                        }
                    ]
                }
            }
        ]


def test_html_rows_preserve_table_relationships() -> None:
    assert parse_table_html(TABLE_HTML)[1] == ["能量", "1200 kJ", "14%"]


def test_structure_adapter_emits_typed_nutrition_table() -> None:
    captured_options = {}

    def factory(**options):
        captured_options.update(options)
        return FakeStructureEngine()

    parser = PPStructureNutritionParser(
        OCRSettings(provider="paddle", table_parser="ppstructure"),
        engine_factory=factory,
    )

    fields = parser.analyze("/tmp/label.jpg")

    assert len(fields) == 1
    assert fields[0].name == "nutrition_table_1"
    assert fields[0].confidence == 0.97
    assert fields[0].nutrition_table is not None
    assert fields[0].nutrition_table.rows[2][0] == "蛋白质"
    assert fields[0].requires_confirmation is False
    assert captured_options["ocr_version"] == "PP-OCRv5"
