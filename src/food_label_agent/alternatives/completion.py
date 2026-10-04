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
                (c["field"] if c["gap"] == "nutrition_field" else c["gap"], c["gap"])
                for c in item["checks"]
                if c.get("gap")
            }
            # A generic packaging task does not store which allergy a person has.
            near = len(gaps) == 1 and any(
                c["status"] == "matched" for c in item["checks"]
            )
            for field, gap in sorted(gaps):
                token = sha256(
                    json.dumps(
                        [
                            request_id,
                            item["candidate_id"],
                            field,
                            gap,
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
                    """INSERT INTO official_completion_tasks VALUES (?,?,?,?,?,?,1,?,?, 'pending')
                  ON CONFLICT(product_id,field,gap) DO UPDATE SET
                  source_fingerprint=excluded.source_fingerprint,
                  display_name=excluded.display_name, source_url=excluded.source_url,
                  demand_count=official_completion_tasks.demand_count+1,
                  near_match_count=official_completion_tasks.near_match_count+excluded.near_match_count,
                  last_requested_at=excluded.last_requested_at, status='pending' """,
                    (
                        item["candidate_id"],
                        field,
                        gap,
                        item["source_fingerprint"],
                        item["display_name"],
                        item.get("source_url"),
                        int(near),
                        utc_now(),
                    ),
                )
                added += 1
    return {"new_demand_events": added, "status": "recorded"}


def completion_snapshot(store):
    with store.connect() as db:
        _schema(db)
        rows = db.execute("""SELECT * FROM official_completion_tasks
          ORDER BY near_match_count DESC,demand_count DESC,product_id,field,gap""").fetchall()
    return {
        "total": len(rows),
        "items": [dict(r) for r in rows],
        "scope": "official_source_evidence_tasks",
        "note": "缺口出现频次不代表真实用户人数；照片到达后仍须匹配商品并审核。",
    }
