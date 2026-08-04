"""Privacy-preserving OCR benchmark runner and deterministic text metrics."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from food_label_agent.ocr.normalization import normalize_nutrition_text
from food_label_agent.ocr.paddle_provider import create_ocr_provider
from food_label_agent.ocr.quality import ImageQualityError
from food_label_agent.ocr.service import OCRService

_SPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_NUTRIENT_VALUE = re.compile(
    r"(反式脂肪酸|碳水化合物|蛋白质|能量|脂肪|钠)"
    r"[^\d-]*(-?\d+(?:\.\d+)?)(kj|mg|ml|g)"
)


def normalize_text(value: str) -> str:
    return _SPACE.sub("", value).lower()


def character_error_rate(expected: str, actual: str) -> float:
    reference = normalize_text(expected)
    hypothesis = normalize_text(actual)
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return _levenshtein(reference, hypothesis) / len(reference)


def token_recall(expected: Sequence[str], actual_text: str) -> float | None:
    normalized = [normalize_text(token) for token in expected if normalize_text(token)]
    if not normalized:
        return None
    haystack = normalize_text(actual_text)
    return sum(token in haystack for token in normalized) / len(normalized)


def numeric_token_metrics(
    expected_text: str, actual_text: str
) -> dict[str, float | None]:
    expected = Counter(_NUMBER.findall(normalize_text(expected_text)))
    if not expected:
        return {"precision": None, "recall": None, "f1": None}
    actual = Counter(_NUMBER.findall(normalize_text(actual_text)))
    matched = sum((expected & actual).values())
    recall = matched / sum(expected.values())
    precision = matched / sum(actual.values()) if actual else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {"precision": precision, "recall": recall, "f1": f1}


def nutrient_value_alignment_accuracy(
    expected_text: str, actual_text: str
) -> float | None:
    expected = extract_nutrition_facts(expected_text)
    if not expected:
        return None
    actual = extract_nutrition_facts(actual_text)
    matched = sum(actual.get(name) == value for name, value in expected.items())
    return matched / len(expected)


def extract_nutrition_facts(value: str) -> dict[str, tuple[float, str]]:
    normalized = normalize_nutrition_text(value)
    return {
        nutrient: (float(amount), unit)
        for nutrient, amount, unit in _NUTRIENT_VALUE.findall(normalized)
    }


async def evaluate_directory(images_dir: Path) -> dict[str, Any]:
    """Evaluate images locally; reports use content hashes, never source filenames."""

    provider = create_ocr_provider()
    service = OCRService(provider)
    samples: list[dict[str, Any]] = []
    issue_counts: Counter[str] = Counter()

    for path in sorted(images_dir.iterdir()):
        if not path.is_file() or path.name.endswith(".json"):
            continue
        content = path.read_bytes()
        detected = detect_image_type(content)
        if detected is None:
            continue
        suffix, media_type = detected
        sample_id = hashlib.sha256(content).hexdigest()[:12]
        try:
            response = await service.analyze(
                content=content,
                file_name=f"{sample_id}{suffix}",
                media_type=media_type,
            )
        except ImageQualityError as exc:
            codes = [issue.code for issue in exc.report.blocking_issues]
            issue_counts.update(codes)
            samples.append(
                {"sample_id": sample_id, "status": "blocked", "issues": codes}
            )
            continue

        fields = {field.name: field.raw_text for field in response.fields}
        sample: dict[str, Any] = {
            "sample_id": sample_id,
            "status": "recognized",
            "field_presence": sorted(name for name, text in fields.items() if text),
            "confirmation_required": sorted(
                field.name for field in response.fields if field.requires_confirmation
            ),
            "warnings": response.warnings,
        }
        annotation_path = path.with_suffix(path.suffix + ".json")
        if annotation_path.exists():
            annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
            sample["metrics"] = compare_fields(annotation, fields)
        samples.append(sample)

    recognized = sum(sample["status"] == "recognized" for sample in samples)
    return {
        "schema_version": "1.0",
        "provider": provider.name,
        "sample_count": len(samples),
        "recognized_count": recognized,
        "blocked_count": len(samples) - recognized,
        "blocking_issue_counts": dict(sorted(issue_counts.items())),
        "samples": samples,
    }


def detect_image_type(content: bytes) -> tuple[str, str] | None:
    """Return a canonical suffix/media type from bytes, independent of filenames."""

    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return ".webp", "image/webp"
    if len(content) >= 12 and content[4:8] == b"ftyp":
        return ".heic", "image/heic"
    return None


def compare_fields(
    annotation: Mapping[str, Any], actual_fields: Mapping[str, str]
) -> dict[str, Any]:
    expected_fields = annotation.get("fields", {})
    field_cer = {}
    for name, expected in expected_fields.items():
        expected_text = str(expected)
        actual_text = actual_fields.get(name, "")
        if name in {"nutrition_basis", "nutrition_table"}:
            expected_text = normalize_nutrition_text(expected_text)
            actual_text = normalize_nutrition_text(actual_text)
        field_cer[name] = round(
            character_error_rate(expected_text, actual_text), 4
        )
    combined = "\n".join(actual_fields.values())
    expected_combined = " ".join(str(value) for value in expected_fields.values())
    numeric = numeric_token_metrics(expected_combined, combined)
    return {
        "field_cer": field_cer,
        "allergen_recall": _round_optional(
            token_recall(annotation.get("allergens", []), combined)
        ),
        "numeric_token_precision": _round_optional(numeric["precision"]),
        "numeric_token_recall": _round_optional(numeric["recall"]),
        "numeric_token_f1": _round_optional(numeric["f1"]),
        "nutrient_value_alignment_accuracy": _round_optional(
            nutrient_value_alignment_accuracy(
                str(expected_fields.get("nutrition_table", "")),
                actual_fields.get("nutrition_table", ""),
            )
        ),
    }


def _round_optional(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _levenshtein(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a local, filename-anonymized OCR evaluation."
    )
    parser.add_argument("images", type=Path, help="Private image directory")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    report = asyncio.run(evaluate_directory(args.images.expanduser().resolve()))
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)


if __name__ == "__main__":
    main()
