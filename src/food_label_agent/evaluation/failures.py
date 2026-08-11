"""Structured failure corpus that becomes permanent deterministic regression."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from food_label_agent.domain.models import UserConstraint
from food_label_agent.domain.types import ConstraintKind
from food_label_agent.ingredients.allergens import evaluate_constraints
from food_label_agent.ingredients.normalization import normalize_ingredients

CORPUS_SCHEMA_VERSION = "failure_corpus_v1"
DEFAULT_CORPUS_PATH = Path(__file__).with_name("data") / "regression_cases.json"


@dataclass(frozen=True, slots=True)
class FailureCorpusEvaluation:
    schema_version: str
    case_count: int
    passed_count: int
    failed_case_ids: tuple[str, ...]
    evaluation_passed: bool
    release_blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["failed_case_ids"] = list(self.failed_case_ids)
        result["release_blockers"] = list(self.release_blockers)
        return result


def evaluate_failure_corpus(
    path: str | Path = DEFAULT_CORPUS_PATH,
) -> FailureCorpusEvaluation:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version", ""))
    if schema_version != CORPUS_SCHEMA_VERSION:
        raise ValueError("Unsupported failure corpus schema")
    failed = []
    cases = payload.get("cases", [])
    seen_ids: set[str] = set()
    for case in cases:
        case_id = str(case["id"])
        if case_id in seen_ids:
            raise ValueError(f"Duplicate failure case id: {case_id}")
        seen_ids.add(case_id)
        normalized = normalize_ingredients(str(case["ingredients"]))
        finding = evaluate_constraints(
            normalized,
            [
                UserConstraint(
                    kind=ConstraintKind.ALLERGY,
                    canonical_value=str(case["constraint"]),
                    severity="severe",
                )
            ],
            allergen_statement=str(case.get("allergen_statement", "")),
        )[0]
        if (
            finding.risk_level.value != case["expected_risk"]
            or finding.reason_code != case["expected_reason"]
            or not finding.evidence_ids
        ):
            failed.append(case_id)
    blockers = ("known_failure_case_regressed",) if failed else ()
    return FailureCorpusEvaluation(
        schema_version=schema_version,
        case_count=len(cases),
        passed_count=len(cases) - len(failed),
        failed_case_ids=tuple(failed),
        evaluation_passed=not failed,
        release_blockers=blockers,
    )
