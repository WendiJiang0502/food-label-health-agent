"""Validate the real-label manifest before it enters evaluation."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evaluation/real_labels/manifest.json"
VALID_STATUSES = {"blocked", "compatible", "unknown", "needs_confirmation"}


def main() -> None:
    if not MANIFEST.exists():
        print(f"manifest_missing: {MANIFEST}")
        raise SystemExit(2)
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    errors: list[str] = []
    ids: set[str] = set()
    task_count = 0
    for case in cases:
        label_id = case.get("label_id")
        if not label_id or label_id in ids:
            errors.append(f"duplicate_or_missing_label_id:{label_id}")
        ids.add(label_id)
        if not case.get("image_path"):
            errors.append(f"image_path_missing:{label_id}")
        facts = case.get("confirmed_facts", {})
        if not facts.get("ingredients"):
            errors.append(f"ingredients_not_confirmed:{label_id}")
        for task in case.get("tasks", []):
            task_count += 1
            task_id = task.get("task_id")
            if not task_id or not task.get("question"):
                errors.append(f"task_incomplete:{label_id}:{task_id}")
            if task.get("expected_status") not in VALID_STATUSES:
                errors.append(f"invalid_expected_status:{label_id}:{task_id}")
            for field in ("expected_findings", "required_evidence", "must_not_claim"):
                if not isinstance(task.get(field), list):
                    errors.append(f"{field}_must_be_list:{label_id}:{task_id}")
    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    print(f"valid: labels={len(cases)} tasks={task_count}")


if __name__ == "__main__":
    main()
