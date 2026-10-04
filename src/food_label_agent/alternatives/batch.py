"""Version-bound batch admission and exception review; never certifies allergy safety."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

from .field_evidence import external_field_evidence
from .knowledge import utc_now

POLICY_VERSION = "batch_admission_v1"
NUTRIENT_UNITS = {
    "sugars": "g",
    "protein": "g",
    "fat": "g",
    "saturated_fat": "g",
    "carbohydrate": "g",
    "dietary_fiber": "g",
    "sodium": "mg",
    "energy": "kJ",
}


def digest(value):
    return sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def revision(row):
    return digest([row["content_hash"], row["ocr_draft"]])


def normalized_specification(value):
    text = re.sub(r"\s+", "", str(value or "")).lower()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(kg|千克|公斤|g|克|ml|毫升|l|升)", text)
    if not match:
        return text
    amount, unit = Decimal(match[1]), match[2]
    if unit in {"kg", "千克", "公斤", "l", "升"}:
        amount *= 1000
    return f"{amount.normalize():f}{'ml' if unit in {'ml', '毫升', 'l', '升'} else 'g'}"


def barcode_valid(value):
    code = str(value or "")
    return (
        bool(re.fullmatch(r"\d{8}|\d{12}|\d{13}|\d{14}", code))
        and sum(
            int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(code[:-1]))
        )
        % 10
        == (-int(code[-1])) % 10
    )


def product_identity(raw):
    code = str(raw.get("code") or "")
    identity = {
        "barcode": code,
        "canonical_barcode": code.zfill(14) if barcode_valid(code) else None,
        "brand": str(raw.get("brands") or "").strip(),
        "variant_name": str(
            raw.get("product_name_zh") or raw.get("product_name") or ""
        ).strip(),
        "specification": normalized_specification(raw.get("quantity")),
        "region": "CN",
        "region_basis": "import_search_scope",
        "source_version": raw.get("last_modified_t"),
    }
    identity["missing"] = [
        key for key in ("brand", "variant_name", "specification") if not identity[key]
    ]
    if not identity["canonical_barcode"]:
        identity["missing"].append("valid_barcode")
    identity["identity_key"] = digest(
        {
            k: identity[k]
            for k in (
                "canonical_barcode",
                "brand",
                "variant_name",
                "specification",
                "region",
            )
        }
    )
    return identity


class StaleBatchError(ValueError):
    pass


class BatchKnowledge:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS image_text_cache (version TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS candidate_versions (
                    code TEXT NOT NULL, revision TEXT NOT NULL, raw TEXT NOT NULL,
                    identity TEXT NOT NULL, captured_at TEXT NOT NULL, PRIMARY KEY(code,revision)
                );
                CREATE TABLE IF NOT EXISTS knowledge_reviews (
                    id INTEGER PRIMARY KEY, code TEXT NOT NULL, revision TEXT NOT NULL,
                    field TEXT NOT NULL, evidence_id TEXT, action TEXT NOT NULL,
                    reviewer TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS batch_reports (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, report TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS enrichment_attempts (
                    code TEXT NOT NULL, kind TEXT NOT NULL, source_version TEXT NOT NULL,
                    status TEXT NOT NULL, attempt_count INTEGER NOT NULL, error_code TEXT,
                    content_hash TEXT, attempted_at TEXT NOT NULL, next_retry_at TEXT,
                    PRIMARY KEY(code,kind,source_version)
                );
            """)

    def _item(self, row, db):
        raw = json.loads(row["payload"])
        identity = product_identity(raw)
        rev = revision(row)
        fields = external_field_evidence(
            raw,
            json.loads(row["ocr_draft"]) if row["ocr_draft"] else None,
            version=row["content_hash"],
            checked_at=row["last_checked_at"],
        )
        reviews = db.execute(
            "SELECT * FROM knowledge_reviews WHERE code=? AND revision=? ORDER BY id",
            (row["id"], rev),
        ).fetchall()
        chosen = {}
        identity_reviewed = False
        dispositions = {}
        for review in reviews:
            if review["field"] == "identity":
                identity_reviewed = review["action"] == "adopt"
            elif review["action"] == "adopt":
                chosen[review["field"]] = review["evidence_id"]
            else:
                chosen.pop(review["field"], None)
            dispositions[review["field"]] = review["action"]
        observations = {v["evidence_id"]: v for v in fields["observations"]}
        approved = {
            name: observations[eid]
            for name, eid in chosen.items()
            if eid in observations
        }
        conflict_fields = set(fields["conflicts"]) - set(approved)
        old_identities = db.execute(
            "SELECT identity FROM candidate_versions WHERE code=? AND revision!=?",
            (row["id"], rev),
        ).fetchall()
        changed = any(
            json.loads(v[0])["identity_key"] != identity["identity_key"]
            for v in old_identities
        )
        identity_ok = not identity["missing"] and (not changed or identity_reviewed)
        identity["changed_since_previous_version"] = changed
        identity["reviewed_for_current_version"] = identity_reviewed
        try:
            age = (
                datetime.now(UTC) - datetime.fromisoformat(row["last_checked_at"])
            ).days
            fresh = 0 <= age <= 550
        except (ValueError, TypeError):
            fresh = False
        numeric = {}
        for value in fields["observations"]:
            if (
                value["tier"] == "external_unverified"
                and value["field"] not in conflict_fields
                and value["unit"] == NUTRIENT_UNITS.get(value["field"])
                and value["basis"] in {"per_100g", "per_100ml"}
            ):
                numeric[value["field"]] = value
        # Accepted observations may resolve disagreement, but cannot supply an unknown unit/basis.
        reviewed_numeric = {
            k: v
            for k, v in approved.items()
            if k in NUTRIENT_UNITS
            and v["unit"] == NUTRIENT_UNITS[k]
            and v["basis"] in {"per_100g", "per_100ml"}
        }
        exceptions = []
        if not identity_ok:
            exceptions.append(
                {
                    "field": "identity",
                    "reason": "identity_changed" if changed else "identity_incomplete",
                }
            )
        if not fresh:
            exceptions.append({"field": "freshness", "reason": "source_stale"})
        for field in sorted(conflict_fields):
            exceptions.append({"field": field, "reason": "conflicting_sources"})
        present = {v["field"] for v in fields["observations"]}
        for field in ("ingredients", "sugars", "protein", "fat", "sodium", "energy"):
            if field not in present:
                exceptions.append({"field": field, "reason": "missing_source_field"})
            elif field not in approved and field not in conflict_fields:
                exceptions.append({"field": field, "reason": "needs_review"})
        for field in present & set(NUTRIENT_UNITS):
            if not any(
                v["field"] == field and v["basis"] in {"per_100g", "per_100ml"}
                for v in fields["observations"]
            ):
                exceptions.append({"field": field, "reason": "basis_unknown"})
        for issue in exceptions:
            issue["deferred"] = dispositions.get(issue["field"]) == "defer"
        capabilities = {
            "searchable": bool(identity["variant_name"]),
            "source_numeric_fields": sorted(numeric) if identity_ok and fresh else [],
            "nutrition_comparison_fields": sorted(reviewed_numeric)
            if identity_ok and identity_reviewed and fresh
            else [],
            "ingredient_judgment": bool(
                approved.get("ingredients")
                and identity_ok
                and identity_reviewed
                and fresh
            ),
            "strict_restriction_judgment": False,
            "recommendation_eligible": False,
        }
        attempts = [
            dict(r)
            for r in db.execute(
                "SELECT kind,status,attempt_count,error_code,attempted_at,next_retry_at FROM enrichment_attempts WHERE code=? ORDER BY attempted_at DESC",
                (row["id"],),
            )
        ]
        from .refresh import full_label_image

        return {
            "id": row["id"],
            "revision": rev,
            "display_name": identity["variant_name"] or row["id"],
            "category": row["category"],
            "identity": identity,
            "source_url": f"https://world.openfoodfacts.org/product/{row['id']}",
            "images": {
                kind: full_label_image(raw, kind)
                for kind in ("ingredients", "nutrition")
            },
            "last_checked_at": row["last_checked_at"],
            "field_evidence": fields,
            "approved_fields": sorted(approved),
            "accepted_evidence_ids": {
                key: value["evidence_id"] for key, value in approved.items()
            },
            "exceptions": exceptions,
            "capabilities": capabilities,
            "attempts": attempts,
            "review_count": len(reviews),
            "policy_version": POLICY_VERSION,
        }

    def item(self, code):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM candidates WHERE id=?", (code,)).fetchone()
            return self._item(row, db) if row else None

    def snapshot(self, *, category=None, reason=None, query="", limit=50, offset=0):
        with self.store.connect() as db:
            rows = db.execute("SELECT * FROM candidates ORDER BY id").fetchall()
            items = [self._item(r, db) for r in rows]
        if category:
            items = [i for i in items if i["category"] == category]
        if reason:
            items = [
                i for i in items if any(e["reason"] == reason for e in i["exceptions"])
            ]
        if query:
            items = [
                i
                for i in items
                if query.casefold()
                in f"{i['display_name']} {i['id']} {i['identity']['brand']}".casefold()
            ]
        counts = Counter(e["reason"] for i in items for e in i["exceptions"])
        summary = {
            "total": len(items),
            "searchable": sum(i["capabilities"]["searchable"] for i in items),
            "source_numeric_ready": sum(
                bool(i["capabilities"]["source_numeric_fields"]) for i in items
            ),
            "nutrition_comparison_ready": sum(
                bool(i["capabilities"]["nutrition_comparison_fields"]) for i in items
            ),
            "ingredient_judgment_ready": sum(
                i["capabilities"]["ingredient_judgment"] for i in items
            ),
            "needs_review": sum(bool(i["exceptions"]) for i in items),
            "exception_counts": dict(counts),
        }
        return {
            "summary": summary,
            "items": items[offset : offset + min(limit, 100)],
            "offset": offset,
            "policy_version": POLICY_VERSION,
            "note": "来源数值齐备仅供来源资料比对；人工字段采用不会自动授予严格限制判断或最终推荐资格。",
        }

    def assess_all(self):
        with self.store.connect() as db:
            rows = db.execute("SELECT * FROM candidates").fetchall()
            for row in rows:
                raw = json.loads(row["payload"])
                draft = json.loads(row["ocr_draft"]) if row["ocr_draft"] else {}
                for image in draft.get("images", {}).values():
                    if image.get("source_url") and image.get("fields"):
                        db.execute(
                            "INSERT OR IGNORE INTO image_text_cache VALUES (?,?)",
                            (
                                digest([image["source_url"]]),
                                json.dumps(image, ensure_ascii=False),
                            ),
                        )
                db.execute(
                    "INSERT OR IGNORE INTO candidate_versions VALUES (?,?,?,?,?)",
                    (
                        row["id"],
                        revision(row),
                        row["payload"],
                        json.dumps(product_identity(raw), ensure_ascii=False),
                        utc_now(),
                    ),
                )
        result = self.snapshot(limit=0)
        with self.store.connect() as db:
            previous = db.execute(
                "SELECT report FROM batch_reports ORDER BY id DESC LIMIT 1"
            ).fetchone()
            baseline = json.loads(previous[0])["summary"] if previous else {}
            result["change_since_previous_batch"] = {
                key: result["summary"][key] - baseline.get(key, 0)
                for key in (
                    "nutrition_comparison_ready",
                    "ingredient_judgment_ready",
                    "source_numeric_ready",
                )
            }
            result["created_at"] = utc_now()
            db.execute(
                "INSERT INTO batch_reports(created_at,report) VALUES (?,?)",
                (result["created_at"], json.dumps(result, ensure_ascii=False)),
            )
        return result

    def review(self, selections, *, action, field, reviewer, note=""):
        if action not in {"adopt", "defer", "retry"} or not 1 <= len(selections) <= 50:
            raise ValueError("请选择 1–50 条记录以及有效操作")
        if field not in {
            "identity",
            "ingredients",
            "allergen_statement",
            "freshness",
            *NUTRIENT_UNITS,
        }:
            raise ValueError("不支持该复核字段")
        if (
            not isinstance(reviewer, str)
            or not 2 <= len(reviewer.strip()) <= 80
            or len(note) > 1000
        ):
            raise ValueError("请填写复核人标识和适当长度的备注")
        if action == "adopt" and field == "freshness":
            raise ValueError("时效只能由来源更新恢复")
        seen = set()
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            checked = []
            for selected in selections:
                code = str(selected.get("id") or "")
                if code in seen:
                    raise ValueError("批次中存在重复商品")
                seen.add(code)
                row = db.execute(
                    "SELECT * FROM candidates WHERE id=?", (code,)
                ).fetchone()
                if row is None or revision(row) != selected.get("revision"):
                    raise StaleBatchError(
                        "资料版本已更新，请重新加载后复核；本批次未写入"
                    )
                item = self._item(row, db)
                if action == "adopt":
                    if len(selections) > 1 and (
                        field in item["field_evidence"]["conflicts"]
                        or (
                            field == "identity"
                            and item["identity"]["changed_since_previous_version"]
                        )
                    ):
                        raise ValueError(
                            "来源冲突或身份变化必须逐条选择依据，不能批量采用"
                        )
                    if field == "identity":
                        if item["identity"]["missing"]:
                            raise ValueError("身份字段不完整，请先补齐来源资料")
                    else:
                        observation = next(
                            (
                                v
                                for v in item["field_evidence"]["observations"]
                                if v["evidence_id"] == selected.get("evidence_id")
                                and v["field"] == field
                            ),
                            None,
                        )
                        if not observation:
                            raise ValueError("所选字段证据已不存在")
                        if field in NUTRIENT_UNITS and (
                            observation["unit"] != NUTRIENT_UNITS[field]
                            or observation["basis"] not in {"per_100g", "per_100ml"}
                        ):
                            raise ValueError("不能采用计量口径不明的数值")
                checked.append((code, row, selected))
            for code, row, selected in checked:
                db.execute(
                    "INSERT INTO knowledge_reviews(code,revision,field,evidence_id,action,reviewer,note,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        code,
                        revision(row),
                        field,
                        selected.get("evidence_id") if action == "adopt" else None,
                        action,
                        reviewer.strip(),
                        note,
                        utc_now(),
                    ),
                )
                if action == "retry":
                    db.execute(
                        "UPDATE enrichment_attempts SET status='retry_requested',next_retry_at=NULL WHERE code=?",
                        (code,),
                    )
                    db.execute(
                        "INSERT INTO completion_queue VALUES (?,?,?,1,?,'pending') ON CONFLICT(product_id) DO UPDATE SET demand_count=demand_count+1,status='pending'",
                        (
                            f"off:{code}",
                            row["content_hash"],
                            json.dumps([field]),
                            utc_now(),
                        ),
                    )
        self.assess_all()
        return {
            "updated": len(checked),
            "action": action,
            "field": field,
            "note": "已记录本批次操作；不改变既有严格限制门禁。",
        }

    def cached_image_text(self, version):
        with self.store.connect() as db:
            row = db.execute(
                "SELECT payload FROM image_text_cache WHERE version=?", (version,)
            ).fetchone()
            return json.loads(row[0]) if row else None

    def cache_image_text(self, image):
        with self.store.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO image_text_cache VALUES (?,?)",
                (digest([image["source_url"]]), json.dumps(image, ensure_ascii=False)),
            )

    def attempt_due(self, code, kind, version):
        with self.store.connect() as db:
            row = db.execute(
                "SELECT * FROM enrichment_attempts WHERE code=? AND kind=? AND source_version=?",
                (code, kind, version),
            ).fetchone()
        if not row:
            return True
        if row["status"] in {"complete", "permanent_failure"}:
            return False
        return not row["next_retry_at"] or row["next_retry_at"] <= utc_now()

    def record_attempt(
        self, code, kind, version, *, status, error_code=None, content_hash=None
    ):
        from datetime import timedelta

        with self.store.connect() as db:
            old = db.execute(
                "SELECT attempt_count FROM enrichment_attempts WHERE code=? AND kind=? AND source_version=?",
                (code, kind, version),
            ).fetchone()
            count = (old[0] if old else 0) + 1
            if status == "transient_failure" and count >= 3:
                status = "permanent_failure"
            next_retry = (
                (datetime.now(UTC) + timedelta(days=min(2**count, 28))).isoformat(
                    timespec="seconds"
                )
                if status == "transient_failure"
                else None
            )
            db.execute(
                "INSERT OR REPLACE INTO enrichment_attempts VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    code,
                    kind,
                    version,
                    status,
                    count,
                    error_code,
                    content_hash,
                    utc_now(),
                    next_retry,
                ),
            )


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    from .knowledge import ProductKnowledgeStore

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = BatchKnowledge(ProductKnowledgeStore()).assess_all()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
