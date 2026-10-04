"""Deduplicated official-source evidence tasks; never retain user queries/profiles."""

import json
from hashlib import sha256

from .knowledge import utc_now


def _schema(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS official_completion_tasks (
          product_id TEXT NOT NULL, field TEXT NOT NULL, gap TEXT NOT NULL,
          source_fingerprint TEXT NOT NULL, display_name TEXT NOT NULL,
          source_url TEXT, demand_count INTEGER NOT NULL, near_match_count INTEGER NOT NULL,
          last_requested_at TEXT NOT NULL, status TEXT NOT NULL,
          PRIMARY KEY(product_id, field, gap));
        CREATE TABLE IF NOT EXISTS official_completion_events (
          event_hash TEXT PRIMARY KEY);
    """)


def record_screening_gaps(store, screening, request_id):
    """Repeated requests do not inflate demand; failed products are not prioritized."""
    added = 0
    with store.connect() as db:
        _schema(db)
        for item in screening["items"]:
            if item["status"] != "unknown":
                continue
            gaps = {
                (
                    c["field"] if c["gap"] == "nutrition_field" else c["gap"],
                    c["gap"],
                    c.get("gap_state", "needs_review"),
                )
                for c in item["checks"]
                if c.get("gap")
            }
            # A generic packaging task does not store which allergy a person has.
            near = len(gaps) == 1 and any(
                c["status"] == "matched" for c in item["checks"]
            )
            for field, gap, gap_state in sorted(gaps):
                token = sha256(
                    json.dumps(
                        [
                            request_id,
                            item["candidate_id"],
                            field,
                            gap,
                            gap_state,
                            item["source_fingerprint"],
                        ],
                        ensure_ascii=False,
                    ).encode()
                ).hexdigest()
                inserted = db.execute(
                    "INSERT OR IGNORE INTO official_completion_events VALUES (?)",
                    (token,),
                ).rowcount
                if not inserted:
                    continue
                db.execute(
                    """INSERT INTO official_completion_tasks VALUES (?,?,?,?,?,?,1,?,?, ?)
                  ON CONFLICT(product_id,field,gap) DO UPDATE SET
                  source_fingerprint=excluded.source_fingerprint,
                  display_name=excluded.display_name, source_url=excluded.source_url,
                  demand_count=official_completion_tasks.demand_count+1,
                  near_match_count=official_completion_tasks.near_match_count+excluded.near_match_count,
                  last_requested_at=excluded.last_requested_at, status=excluded.status """,
                    (
                        item["candidate_id"],
                        field,
                        gap,
                        item["source_fingerprint"],
                        item["display_name"],
                        item.get("source_url"),
                        int(near),
                        utc_now(),
                        gap_state,
                    ),
                )
                added += 1
    return {"new_demand_events": added, "status": "recorded"}


def completion_snapshot(store):
    with store.connect() as db:
        _schema(db)
        rows = db.execute("""SELECT * FROM official_completion_tasks
          ORDER BY (status='not_declared') ASC,near_match_count DESC,demand_count DESC,product_id,field,gap""").fetchall()
    return {
        "total": len(rows),
        "items": [
            dict(r)
            | {
                "same_source_retry_allowed": r["status"]
                in {"needs_label", "needs_review"}
            }
            for r in rows
        ],
        "scope": "official_source_evidence_tasks",
        "note": "缺口出现频次不代表真实用户人数；照片到达后仍须匹配商品并审核。",
    }


def reconcile_completion_tasks(store, items, approved_products=()):
    """Re-evaluate existing demand against current evidence, never fabricate fields.

    source_available means a source field is present, NOT packaging approval.
    Unsupported/manual sources wait for evidence; this consumer does not repeatedly
    fetch a page that has already failed to supply the requested field.
    """
    from .evidence import nutrition_facts, source_flags
    from .ingredient_screening import field_gap_state

    by_id = {i["candidate_id"]: i for i in items}
    approved = {p["product_id"]: p for p in approved_products}
    changes = 0
    with store.connect() as db:
        _schema(db)
        db.execute("""CREATE TABLE IF NOT EXISTS official_completion_transitions (
            id INTEGER PRIMARY KEY, product_id TEXT NOT NULL, field TEXT NOT NULL,
            gap TEXT NOT NULL, from_status TEXT NOT NULL, to_status TEXT NOT NULL,
            source_fingerprint TEXT NOT NULL, changed_at TEXT NOT NULL)""")
        rows = db.execute("SELECT * FROM official_completion_tasks").fetchall()
        for row in rows:
            item = by_id.get(row["product_id"])
            version = row["source_fingerprint"]
            if item is None:
                status = "source_missing"
            elif item.get("review_status") == "rejected":
                status = "rejected"
            else:
                version = item.get("source_fingerprint") or "unknown"
                flags = source_flags(item)
                fields = item.get("extracted_fields") or {}
                product = approved.get(item.get("approved_product_id"))
                if item.get("review_status") == "approved" and product:
                    label = product.get("label") or {}
                    fields = {**fields, **label}
                if flags:
                    status = "needs_review"
                elif row["gap"] == "nutrition_field" and row[
                    "field"
                ] in nutrition_facts(fields):
                    status = "source_available"
                elif (
                    row["gap"] == "packaging_review"
                    and product
                    and item.get("review_status") == "approved"
                ):
                    status = "resolved"
                elif row["gap"] == "source_review":
                    status = "source_available"
                else:
                    status = field_gap_state(item, row["field"])
            if status != row["status"] or version != row["source_fingerprint"]:
                db.execute(
                    """UPDATE official_completion_tasks SET status=?, source_fingerprint=?
                    WHERE product_id=? AND field=? AND gap=?""",
                    (status, version, row["product_id"], row["field"], row["gap"]),
                )
                db.execute(
                    """INSERT INTO official_completion_transitions
                    (product_id,field,gap,from_status,to_status,source_fingerprint,changed_at)
                    VALUES (?,?,?,?,?,?,?)""",
                    (
                        row["product_id"],
                        row["field"],
                        row["gap"],
                        row["status"],
                        status,
                        version,
                        utc_now(),
                    ),
                )
                changes += 1
    return {"status": "completed", "checked_count": len(rows), "changed_count": changes}
