"""Export the official catalog acquisition gaps as a deterministic JSON report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .catalog import OfficialChinaCatalog


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit official catalog brand, identity, nutrition and packaging evidence"
    )
    parser.add_argument("--category", help="Limit the report to one catalog category")
    parser.add_argument("--output", type=Path, help="Also write the JSON report here")
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Return a non-zero exit status while the quality gate is blocked",
    )
    args = parser.parse_args()
    report = OfficialChinaCatalog().coverage(category=args.category)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    quality_passed = bool(report.get("catalog_quality", {}).get("quality_gate_passed"))
    return 1 if args.enforce and not quality_passed else 0


if __name__ == "__main__":
    raise SystemExit(main())
