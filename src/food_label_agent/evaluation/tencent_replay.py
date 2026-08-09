"""Replay private Tencent OCR line evidence without making another cloud request."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from food_label_agent.ocr.config import OCRSettings
from food_label_agent.ocr.evidence_quality import assess_ocr_evidence
from food_label_agent.ocr.field_parser import OCRLine, parse_food_label_fields
from food_label_agent.ocr.models import BoundingBox
from food_label_agent.ocr.nutrition_coordinates import (
    extract_coordinate_nutrition_table,
)


def replay_report(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    report = []
    settings = OCRSettings(provider="tencent")
    for sample in payload:
        width = int(sample["width"])
        height = int(sample["height"])
        lines = [_line(item, width=width, height=height) for item in sample["lines"]]
        fields = parse_food_label_fields(lines, settings)
        table = extract_coordinate_nutrition_table(lines)
        if table is not None:
            fields.append(table)
        evidence = assess_ocr_evidence(fields)
        report.append(
            {
                "file_name": sample["file_name"],
                "fields": {field.name: field.raw_text for field in fields},
                "confirmation_required": [
                    field.name for field in fields if field.requires_confirmation
                ],
                "evidence_status": evidence.status,
                "evidence_issues": [
                    issue.model_dump(mode="json") for issue in evidence.issues
                ],
                "nutrition_issues": (
                    [
                        issue.model_dump(mode="json")
                        for issue in table.nutrition_table.issues
                    ]
                    if table is not None and table.nutrition_table is not None
                    else []
                ),
            }
        )
    return report


def _line(item: dict[str, Any], *, width: int, height: int) -> OCRLine:
    points = item.get("polygon") or []
    box = None
    if points:
        left = min(float(point["x"]) for point in points) / width
        top = min(float(point["y"]) for point in points) / height
        right = max(float(point["x"]) for point in points) / width
        bottom = max(float(point["y"]) for point in points) / height
        if right > left and bottom > top:
            box = BoundingBox(x=left, y=top, width=right - left, height=bottom - top)
    confidence = float(item.get("confidence", 0))
    if confidence > 1:
        confidence /= 100
    return OCRLine(
        text=str(item.get("text", "")).strip(),
        confidence=max(0.0, min(confidence, 1.0)),
        bounding_box=box,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Private raw Tencent OCR JSON")
    parser.add_argument("--output", type=Path, help="Optional local JSON report")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    report = replay_report(payload)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
