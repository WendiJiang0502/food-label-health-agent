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
from food_label_agent.ocr.provider import OCRProviderError
from food_label_agent.ocr.quality import ImageQualityError
from food_label_agent.ocr.service import OCRService

_SPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_NUTRIENT_VALUE = re.compile(
    r"(反式脂肪酸|反式脂肪|饱和脂肪酸|饱和脂肪|碳水化合物|蛋白质|能量|脂肪|糖|钠)"
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
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
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
        annotation_path = path.with_suffix(path.suffix + ".json")
        annotation = (
            json.loads(annotation_path.read_text(encoding="utf-8"))
            if annotation_path.exists()
            else None
        )
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
                {
                    "sample_id": sample_id,
                    "status": "blocked",
                    "issues": codes,
                    "expected_blocked": (
                        bool(annotation.get("expect_blocked")) if annotation else None
                    ),
                }
            )
            continue
        except OCRProviderError as exc:
            issue_counts.update([exc.code])
            samples.append(
                {
                    "sample_id": sample_id,
                    "status": "provider_error",
                    "issues": [exc.code],
                    "retryable": exc.retryable,
                }
            )
            if not exc.retryable:
                break
            continue

        fields = {field.name: field.raw_text for field in response.fields}
        sample: dict[str, Any] = {
            "sample_id": sample_id,
            "status": "recognized",
            "field_presence": sorted(name for name, text in fields.items() if text),
            "confirmation_required": sorted(
                field.name for field in response.fields if field.requires_confirmation
            ),
            "image_quality": (
                response.image_quality.model_dump(mode="json")
                if response.image_quality
                else None
            ),
            "evidence_quality": response.evidence_quality.model_dump(mode="json"),
            "warnings": response.warnings,
            "expected_blocked": (
                bool(annotation.get("expect_blocked")) if annotation else None
            ),
        }
        if annotation is not None:
            sample["metrics"] = compare_fields(annotation, fields)
            sample["annotation_status"] = annotation.get(
                "annotation_status", "unspecified"
            )
            sample["dataset_role"] = annotation.get("dataset_role", "unspecified")
        samples.append(sample)

    recognized = sum(sample["status"] == "recognized" for sample in samples)
    blocked = sum(sample["status"] == "blocked" for sample in samples)
    supervised = [sample for sample in samples if "metrics" in sample]
    release_eligible = [
        sample
        for sample in supervised
        if sample.get("annotation_status") == "double_reviewed_gold"
        and sample.get("dataset_role") == "blind_test"
    ]
    expected_low_quality = [
        sample for sample in samples if sample.get("expected_blocked") is True
    ]
    correctly_blocked = sum(
        sample["status"] == "blocked" for sample in expected_low_quality
    )
    return {
        "schema_version": "1.0",
        "provider": provider.name,
        "sample_count": len(samples),
        "recognized_count": recognized,
        "blocked_count": blocked,
        "provider_error_count": sum(
            sample["status"] == "provider_error" for sample in samples
        ),
        "supervised_count": len(supervised),
        "release_eligible_supervised_count": len(release_eligible),
        "annotation_status_counts": dict(
            sorted(
                Counter(
                    sample.get("annotation_status", "unspecified")
                    for sample in supervised
                ).items()
            )
        ),
        "dataset_role_counts": dict(
            sorted(
                Counter(
                    sample.get("dataset_role", "unspecified")
                    for sample in supervised
                ).items()
            )
        ),
        "aggregate_metrics": _aggregate_sample_metrics(supervised),
        "expected_low_quality_count": len(expected_low_quality),
        "low_quality_block_recall": (
            correctly_blocked / len(expected_low_quality)
            if expected_low_quality
            else None
        ),
        "blocking_issue_counts": dict(sorted(issue_counts.items())),
        "samples": samples,
    }


def _aggregate_sample_metrics(samples: list[dict[str, Any]]) -> dict[str, float | None]:
    def mean(values: list[float | None]) -> float | None:
        present = [value for value in values if value is not None]
        return round(sum(present) / len(present), 4) if present else None

    return {
        "ingredients_cer": mean(
            [
                sample["metrics"].get("field_cer", {}).get("ingredients")
                for sample in samples
            ]
        ),
        "allergen_recall": mean(
            [sample["metrics"].get("allergen_recall") for sample in samples]
        ),
        "numeric_token_recall": mean(
            [sample["metrics"].get("numeric_token_recall") for sample in samples]
        ),
        "nutrient_value_alignment_accuracy": mean(
            [
                sample["metrics"].get("nutrient_value_alignment_accuracy")
                for sample in samples
            ]
        ),
        "critical_fact_recall": _micro_critical_fact_recall(samples),
    }


def _micro_critical_fact_recall(samples: list[dict[str, Any]]) -> float | None:
    counts = [
        sample["metrics"].get("critical_fact_counts", {}) for sample in samples
    ]
    total = sum(int(item.get("total", 0)) for item in counts)
    if not total:
        return None
    matched = sum(int(item.get("matched", 0)) for item in counts)
    return round(matched / total, 4)


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
        field_cer[name] = round(character_error_rate(expected_text, actual_text), 4)
    combined = "\n".join(actual_fields.values())
    expected_combined = " ".join(str(value) for value in expected_fields.values())
    numeric = numeric_token_metrics(expected_combined, combined)
    ingredient_tokens = [
        str(token) for token in annotation.get("ingredient_tokens", [])
    ]
    expected_allergens = [str(token) for token in annotation.get("allergens", [])]
    expected_nutrition = extract_nutrition_facts(
        str(expected_fields.get("nutrition_table", ""))
    )
    actual_nutrition = extract_nutrition_facts(
        actual_fields.get("nutrition_table", "")
    )
    ingredient_matches = sum(
        normalize_text(token) in normalize_text(actual_fields.get("ingredients", ""))
        for token in ingredient_tokens
        if normalize_text(token)
    )
    allergen_matches = sum(
        normalize_text(token) in normalize_text(combined)
        for token in expected_allergens
        if normalize_text(token)
    )
    nutrition_matches = sum(
        actual_nutrition.get(name) == value
        for name, value in expected_nutrition.items()
    )
    critical_total = (
        len(ingredient_tokens) + len(expected_allergens) + len(expected_nutrition)
    )
    critical_matched = ingredient_matches + allergen_matches + nutrition_matches
    return {
        "field_cer": field_cer,
        "allergen_recall": _round_optional(
            token_recall(expected_allergens, combined)
        ),
        "ingredient_token_recall": _round_optional(
            token_recall(ingredient_tokens, actual_fields.get("ingredients", ""))
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
        "critical_fact_counts": {
            "matched": critical_matched,
            "total": critical_total,
        },
        "critical_fact_recall": (
            round(critical_matched / critical_total, 4)
            if critical_total
            else None
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
