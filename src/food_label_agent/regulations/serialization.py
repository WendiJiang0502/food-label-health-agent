"""Stable JSON persistence for ingested regulation chunks."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .ingestion import IngestionResult
from .models import RegulationClause

SCHEMA_VERSION = "regulation_chunks_v1"


def save_ingestion_result(result: IngestionResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "document_id": result.document_id,
        "document_hash": result.document_hash,
        "page_count": result.page_count,
        "warnings": list(result.warnings),
        "clauses": [asdict(clause) for clause in result.clauses],
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_clause_index(index_path: Path) -> tuple[RegulationClause, ...]:
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported regulation index schema: {index_path}")
    clauses = []
    for value in payload.get("clauses", []):
        value["topics"] = tuple(value.get("topics", ()))
        value["keywords"] = tuple(value.get("keywords", ()))
        clauses.append(RegulationClause(**value))
    return tuple(clauses)
