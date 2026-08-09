"""Command-line ingestion for an official standard PDF."""

from __future__ import annotations

import argparse
from pathlib import Path

from .ingestion import ingest_pdf
from .registry import get_document, validate_registry
from .serialization import save_ingestion_result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract an official food-standard PDF into clause-level JSON."
    )
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    validate_registry()
    document = get_document(args.document_id)
    result = ingest_pdf(document, args.pdf)
    save_ingestion_result(result, args.output)
    print(
        f"ingested {result.document_id}: {result.page_count} pages, "
        f"{len(result.clauses)} clauses, {len(result.warnings)} warnings"
    )


if __name__ == "__main__":
    main()
