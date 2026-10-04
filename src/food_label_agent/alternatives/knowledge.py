"""Durable discovery evidence. Importing a source never certifies its label."""

from __future__ import annotations

import calendar
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

from .discovery import default_discovery_queue_path


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def next_calendar_month(value: str) -> str:
    current = datetime.fromisoformat(value)
    year = current.year + (current.month == 12)
    month = current.month % 12 + 1
    day = min(current.day, calendar.monthrange(year, month)[1])
    return current.replace(year=year, month=month, day=day).isoformat()


class ProductKnowledgeStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(
            path
            or os.getenv("FOOD_LABEL_PRODUCT_RAG_DB")
            or default_discovery_queue_path().with_name("product-knowledge.sqlite3")
        )

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS official_evidence (
                    product_id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY, category TEXT NOT NULL, payload TEXT NOT NULL,
                    content_hash TEXT NOT NULL, first_seen_at TEXT NOT NULL,
                    last_checked_at TEXT NOT NULL, last_changed_at TEXT NOT NULL,
                    source_updated_at TEXT, verified_at TEXT, review_status TEXT NOT NULL,
                    missing_fields TEXT NOT NULL, ocr_draft TEXT
                );
                CREATE TABLE IF NOT EXISTS memberships (
                    id TEXT NOT NULL, category TEXT NOT NULL, PRIMARY KEY(id, category)
                );
                INSERT OR IGNORE INTO memberships SELECT id, category FROM candidates;
                CREATE TABLE IF NOT EXISTS ocr_attempts (
                    id TEXT PRIMARY KEY, attempted_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS field_observations (
                    product_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(product_id, evidence_id)
                );
                CREATE TABLE IF NOT EXISTS product_vectors (
                    cache_key TEXT PRIMARY KEY, vector TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS completion_queue (
                    product_id TEXT PRIMARY KEY, evidence_hash TEXT NOT NULL,
                    missing_fields TEXT NOT NULL, demand_count INTEGER NOT NULL,
                    requested_at TEXT NOT NULL, status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    job TEXT PRIMARY KEY, status TEXT NOT NULL, last_attempt_at TEXT NOT NULL,
                    last_success_at TEXT, next_check_at TEXT NOT NULL,
                    summary TEXT NOT NULL
                );
            """)
            with db:
                yield db
        finally:
            db.close()

    def ingest(
        self, raw: dict[str, Any], category: str, *, checked_at: str | None = None
    ) -> None:
        from .catalog import _map_open_food_facts_product

        code = str(raw.get("code") or "").strip()
        if not code:
            return
        now = checked_at or utc_now()
        _, rejection = _map_open_food_facts_product(raw, category)
        missing = rejection.get("missing_fields", []) if rejection else []
        # Source timestamps and completion flags are not proof of label review.
        evidence = {
            key: value
            for key, value in raw.items()
            if key not in {"last_modified_t", "states_tags", "completeness", "checked"}
        }
        digest = sha256(
            json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        modified = raw.get("last_modified_t")
        source_date = (
            datetime.fromtimestamp(int(modified), UTC).isoformat() if modified else None
        )
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO memberships VALUES (?,?)", (code, category)
            )
            old = db.execute("SELECT * FROM candidates WHERE id=?", (code,)).fetchone()
            changed = bool(old and old["content_hash"] != digest)
            status = (
                "change_detected"
                if changed or (old and old["review_status"] == "change_detected")
                else ("needs_label" if missing else "needs_review")
            )
            db.execute(
                """INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET category=excluded.category, payload=excluded.payload,
                content_hash=excluded.content_hash, last_checked_at=excluded.last_checked_at,
                last_changed_at=excluded.last_changed_at, source_updated_at=excluded.source_updated_at,
                verified_at=excluded.verified_at, review_status=excluded.review_status,
                missing_fields=excluded.missing_fields, ocr_draft=excluded.ocr_draft""",
                (
                    code,
                    category,
                    json.dumps(raw, ensure_ascii=False),
                    digest,
                    old["first_seen_at"] if old else now,
                    now,
                    now if changed or not old else old["last_changed_at"],
                    source_date,
                    None if changed or not old else old["verified_at"],
                    status,
                    json.dumps(missing),
                    None if changed or not old else old["ocr_draft"],
                ),
            )

        self.field_evidence(code)

    def field_evidence(self, code: str) -> dict:
        from .field_evidence import external_field_evidence

        with self.connect() as db:
            row = db.execute("SELECT * FROM candidates WHERE id=?", (code,)).fetchone()
            if not row:
                return {"observations": [], "conflicts": [], "status": "not_found"}
            fields = external_field_evidence(
                json.loads(row["payload"]),
                json.loads(row["ocr_draft"]) if row["ocr_draft"] else None,
                version=row["content_hash"],
                checked_at=row["last_checked_at"],
            )
            for item in fields["observations"]:
                db.execute(
                    "INSERT OR IGNORE INTO field_observations VALUES (?,?,?)",
                    (
                        f"off:{code}",
                        item["evidence_id"],
                        json.dumps(item, ensure_ascii=False),
                    ),
                )
            queued = db.execute(
                "SELECT missing_fields FROM completion_queue WHERE product_id=?",
                (f"off:{code}",),
            ).fetchone()
            if queued:
                remaining = {
                    f for f in json.loads(queued[0]) if not f.startswith("conflict:")
                }
                remaining.update(f"conflict:{field}" for field in fields["conflicts"])
                db.execute(
                    "UPDATE completion_queue SET missing_fields=?,status=? WHERE product_id=?",
                    (
                        json.dumps(sorted(remaining)),
                        "pending" if remaining else "needs_review",
                        f"off:{code}",
                    ),
                )
            return fields

    def backfill_field_evidence(self) -> dict:
        with self.connect() as db:
            codes = [row[0] for row in db.execute("SELECT id FROM candidates")]
        count = conflicts = 0
        for code in codes:
            fields = self.field_evidence(code)
            count += len(fields["observations"])
            conflicts += bool(fields["conflicts"])
        return {
            "products": len(codes),
            "current_observations": count,
            "products_with_conflicts": conflicts,
        }

    def record_run(
        self,
        job: str,
        status: str,
        summary: dict,
        *,
        interval_hours: int | None = None,
        attempted_at: str | None = None,
    ) -> None:
        now = attempted_at or utc_now()
        if interval_hours is None:
            # Monthly jobs keep their cadence even if a source is unavailable.
            due = next_calendar_month(now)
        else:
            delay = interval_hours if status == "completed" else min(interval_hours, 1)
            due = (datetime.fromisoformat(now) + timedelta(hours=delay)).isoformat()
        with self.connect() as db:
            db.execute(
                """INSERT INTO runs VALUES (?,?,?,?,?,?) ON CONFLICT(job) DO UPDATE SET
                status=excluded.status, last_attempt_at=excluded.last_attempt_at,
                last_success_at=COALESCE(excluded.last_success_at,runs.last_success_at),
                next_check_at=excluded.next_check_at, summary=excluded.summary""",
                (
                    job,
                    status,
                    now,
                    now if status == "completed" else None,
                    due,
                    json.dumps(summary),
                ),
            )

    def due(self, job: str, *, now: str | None = None) -> bool:
        with self.connect() as db:
            row = db.execute(
                "SELECT next_check_at FROM runs WHERE job=?", (job,)
            ).fetchone()
        return not row or datetime.fromisoformat(row[0]) <= datetime.fromisoformat(
            now or utc_now()
        )

    def snapshot(
        self, *, category: str | None = None, query: str = "", limit: int = 20
    ) -> dict:
        with self.connect() as db:
            where, args = (
                (
                    "WHERE id IN (SELECT id FROM memberships WHERE category=?)",
                    [category],
                )
                if category
                else ("", [])
            )
            rows = db.execute(
                f"SELECT * FROM candidates {where} ORDER BY last_checked_at DESC,id",
                args,
            ).fetchall()
            runs = [dict(row) for row in db.execute("SELECT * FROM runs ORDER BY job")]
        items = []
        for row in rows:
            raw = json.loads(row["payload"])
            name = raw.get("product_name_zh") or raw.get("product_name") or row["id"]
            if (
                query
                and query.casefold()
                not in f"{name} {raw.get('brands', '')} {raw.get('ingredients_text_zh') or raw.get('ingredients_text', '')}".casefold()
            ):
                continue
            items.append(
                {
                    "id": row["id"],
                    "display_name": name,
                    "category": row["category"],
                    "source_url": f"https://world.openfoodfacts.org/product/{row['id']}",
                    "last_checked_at": row["last_checked_at"],
                    "source_updated_at": row["source_updated_at"],
                    "verified_at": row["verified_at"],
                    "review_status": row["review_status"],
                    "missing_fields": json.loads(row["missing_fields"]),
                    "has_ocr_draft": bool(row["ocr_draft"]),
                    "recommendation_eligible": False,
                }
            )
        for run in runs:
            run["summary"] = json.loads(run["summary"])
            run["overdue"] = datetime.fromisoformat(
                run["next_check_at"]
            ) < datetime.now(UTC)
        return {
            "candidate_count": len(items),
            "items": items[: max(0, min(limit, 100))],
            "runs": runs,
            "attribution": "Open Food Facts · ODbL",
            "scope": "discovery_only",
        }

    def prioritize(
        self, product_id: str, evidence_hash: str, missing_fields: list[str]
    ) -> None:
        # Store field gaps and popularity, never a user's query or health profile.
        with self.connect() as db:
            old = db.execute(
                "SELECT missing_fields FROM completion_queue WHERE product_id=?",
                (product_id,),
            ).fetchone()
            missing = sorted(
                set(missing_fields) | set(json.loads(old[0]) if old else [])
            )
            db.execute(
                """INSERT INTO completion_queue VALUES (?,?,?,1,?,'pending')
                ON CONFLICT(product_id) DO UPDATE SET evidence_hash=excluded.evidence_hash,
                missing_fields=excluded.missing_fields, demand_count=completion_queue.demand_count+1,
                requested_at=excluded.requested_at, status='pending'""",
                (product_id, evidence_hash, json.dumps(missing), utc_now()),
            )

    def reconcile_gaps(self, code: str, available_fields: set[str]) -> None:
        with self.connect() as db:
            row = db.execute(
                "SELECT missing_fields FROM completion_queue WHERE product_id=?",
                (f"off:{code}",),
            ).fetchone()
            if row:
                remaining = sorted(set(json.loads(row[0])) - available_fields)
                db.execute(
                    "UPDATE completion_queue SET missing_fields=?,status=? WHERE product_id=?",
                    (
                        json.dumps(remaining),
                        "pending" if remaining else "needs_review",
                        f"off:{code}",
                    ),
                )

    def coverage(self) -> dict:
        """Measure source availability, separately from human verification."""
        from .catalog import _selected_image

        with self.connect() as db:
            rows = db.execute("SELECT * FROM candidates ORDER BY id").fetchall()
        counts = {
            "total": len(rows),
            "ingredients_text_present": 0,
            "ingredients_image_present": 0,
            "nutrition_image_present": 0,
            "core_nutrition_present": 0,
            "sugars_present": 0,
            "ocr_draft_present": 0,
            "reviewed": 0,
        }
        gaps = []
        for row in rows:
            raw = json.loads(row["payload"])
            nutrients = raw.get("nutriments") or {}
            availability = {
                "ingredients_text_present": bool(
                    raw.get("ingredients_text_zh") or raw.get("ingredients_text")
                ),
                "ingredients_image_present": bool(
                    _selected_image(raw, "ingredients")
                    or raw.get("image_ingredients_url")
                ),
                "nutrition_image_present": bool(
                    _selected_image(raw, "nutrition") or raw.get("image_nutrition_url")
                ),
                "core_nutrition_present": all(
                    nutrients.get(key) is not None
                    for key in (
                        "proteins_100g",
                        "fat_100g",
                        "carbohydrates_100g",
                        "sodium_100g",
                    )
                )
                and any(
                    nutrients.get(key) is not None
                    for key in ("energy-kj_100g", "energy-kcal_100g")
                ),
                "sugars_present": nutrients.get("sugars_100g") is not None,
                "ocr_draft_present": bool(row["ocr_draft"]),
                "reviewed": bool(row["verified_at"]),
            }
            for key, present in availability.items():
                counts[key] += int(present)
            gaps.append(
                {
                    "id": row["id"],
                    "display_name": raw.get("product_name_zh")
                    or raw.get("product_name")
                    or row["id"],
                    "missing": [
                        key for key, value in availability.items() if not value
                    ],
                    "source_url": f"https://world.openfoodfacts.org/product/{row['id']}",
                }
            )
        return {
            "counts": counts,
            "gaps": gaps,
            "note": "字段存在仅表示来源提供数据，不代表完整、准确或已核实。",
        }

    def save_ocr_draft(self, code: str, draft: dict, *, expected_hash: str) -> None:
        with self.connect() as db:
            result = db.execute(
                "UPDATE candidates SET ocr_draft=? WHERE id=? AND content_hash=?",
                (json.dumps(draft, ensure_ascii=False), code, expected_hash),
            )
            if result.rowcount != 1:
                raise ValueError(
                    "Candidate changed during OCR; retry with current evidence"
                )
        self.field_evidence(code)
