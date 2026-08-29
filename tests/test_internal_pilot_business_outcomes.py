from pathlib import Path

from scripts.run_internal_pilot import run

ROOT = Path(__file__).resolve().parents[1]


def test_personal_pilot_compares_business_outcomes_not_workflow_status() -> None:
    report = run(ROOT / "docs/evaluation/internal_pilot_dataset_v1.json")

    assert report["case_count"] == 11
    assert report["evaluation_passed"] is True
    assert report["business_status_mismatches"] == []
    assert report["forbidden_claim_violation_cases"] == []
    outcomes = {
        item["case_id"]: item["actual_business_status"]
        for item in report["results"]
    }
    assert outcomes["case_004"] == "unknown"
    assert outcomes["case_006"] == "compatible"
    assert outcomes["case_007"] == "blocked"
    assert outcomes["case_009"] == "needs_confirmation"
    assert outcomes["case_020"] == "needs_confirmation"


def test_alternative_cases_are_not_double_counted_as_personal_cases() -> None:
    report = run(ROOT / "docs/evaluation/internal_pilot_dataset_v1.json")

    assert not {"case_016", "case_017", "case_018", "case_019"}.intersection(
        item["case_id"] for item in report["results"]
    )


def test_pilot_suite_summary_includes_alternative_release_blockers() -> None:
    source = (ROOT / "scripts" / "run_pilot_suite.py").read_text(encoding="utf-8")

    assert '"alternative_release_blockers"' in source
    assert 'summary["alternative_release_blockers"]' in source
