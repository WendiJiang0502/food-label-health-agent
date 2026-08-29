"""Operator CLI for capturing, reviewing, and attaching package evidence."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .models import PackagingSnapshotEvidence, ProductRecord
from .packaging_evidence import PackagingEvidenceStore, attach_verified_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    capture = commands.add_parser("capture")
    capture.add_argument("--store", required=True)
    capture.add_argument("--image", required=True)
    capture.add_argument("--kind", choices=("ingredients", "nutrition", "combined"), required=True)
    capture.add_argument(
        "--artifact-type",
        choices=("packaging_photo", "official_page_capture"),
        required=True,
    )
    capture.add_argument("--source-url", required=True)
    capture.add_argument("--captured-at", type=date.fromisoformat, required=True)
    capture.add_argument("--sku", required=True)
    capture.add_argument("--specification", required=True)
    capture.add_argument("--reviewer", required=True)
    capture.add_argument("--allowed-host", action="append")
    capture.add_argument("--output", required=True)

    review = commands.add_parser("review")
    review.add_argument("--store", required=True)
    review.add_argument("--snapshot", required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--reviewed-at", type=date.fromisoformat, required=True)
    review.add_argument("--reject", action="store_true")
    review.add_argument("--output", required=True)

    attach = commands.add_parser("attach")
    attach.add_argument("--product", required=True)
    attach.add_argument("--snapshot", required=True)
    attach.add_argument("--output", required=True)

    args = parser.parse_args()
    if args.command == "capture":
        snapshot = PackagingEvidenceStore(args.store).ingest(
            Path(args.image).read_bytes(),
            evidence_kind=args.kind,
            artifact_type=args.artifact_type,
            source_url=args.source_url,
            captured_at=args.captured_at,
            sku=args.sku,
            specification=args.specification,
            reviewer_id=args.reviewer,
            allowed_hosts=set(args.allowed_host) if args.allowed_host else None,
        )
        _write_json(args.output, snapshot.model_dump(mode="json"))
        return
    snapshot = PackagingSnapshotEvidence.model_validate(
        _read_json(args.snapshot)
    )
    if args.command == "review":
        reviewed = PackagingEvidenceStore(args.store).add_second_review(
            snapshot,
            reviewer_id=args.reviewer,
            reviewed_at=args.reviewed_at,
            approve=not args.reject,
        )
        _write_json(args.output, reviewed.model_dump(mode="json"))
        return
    product = ProductRecord.model_validate(_read_json(args.product))
    attached = attach_verified_snapshot(product, snapshot)
    _write_json(args.output, attached.model_dump(mode="json"))


def _read_json(path: str) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str, payload: object) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(destination)


if __name__ == "__main__":
    main()
