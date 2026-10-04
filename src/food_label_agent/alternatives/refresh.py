"""Scheduled source checks and ingredient completion; run as a separate worker."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import logging
import os
import re
import signal
import sqlite3
import threading
import time
from hashlib import sha256
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .batch import BatchKnowledge, digest
from .catalog import (
    CATEGORY_TAGS,
    OFF_FIELDS,
    OpenFoodFactsCatalog,
    _fetch_json,
    _selected_image,
)
from .discovery import OfficialProductDiscovery
from .knowledge import ProductKnowledgeStore, utc_now

logger = logging.getLogger(__name__)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_label_image(url: str) -> tuple[bytes, str]:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "images.openfoodfacts.org"
        or parsed.port not in (None, 443)
        or parsed.username
    ):
        raise ValueError("Unsupported packaging image origin")
    with build_opener(_NoRedirect).open(
        Request(url, headers={"User-Agent": "LabelLensHealth/0.3"}), timeout=15
    ) as response:
        content = response.read(10_000_001)
        media_type = response.headers.get_content_type()
    if len(content) > 10_000_000:
        raise ValueError("Packaging image exceeds size limit")
    return content, media_type


def full_label_image(raw, kind):
    url = _selected_image(raw, kind) or raw.get(f"image_{kind}_url")
    if not url:
        return None
    # OFF documents full/100/200/400 renditions of the SAME selected revision.
    # Never switch language, revision or SKU while choosing a larger image.
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.hostname == "images.openfoodfacts.org":
        path = re.sub(r"\.(?:100|200|400)\.jpg$", ".full.jpg", parsed.path)
        return parsed._replace(path=path).geturl()
    return url


class KnowledgeRefreshWorker:
    def __init__(
        self,
        store=None,
        discovery=None,
        *,
        fetch_json=None,
        request_delay=7.0,
        categories=None,
        ocr_service=None,
        fetch_image=fetch_label_image,
    ):
        self.store = store or ProductKnowledgeStore()
        self.batch = BatchKnowledge(self.store)
        self.discovery = discovery or OfficialProductDiscovery()
        self.fetch_json = fetch_json or _fetch_json
        self.request_delay = request_delay
        self.categories = categories or ["breakfast_cereal", "dairy", "drink"]
        if any(category not in CATEGORY_TAGS for category in self.categories):
            raise ValueError("Unsupported refresh category")
        self.ocr_service = ocr_service
        if ocr_service and ocr_service.provider.synthetic:
            raise ValueError("Synthetic OCR cannot enrich product evidence")
        self.fetch_image = fetch_image
        self._request_lock = threading.Lock()
        self._next_request = 0.0

    def _refresh_category(self, category):
        snapshots = {}

        def fetch(url, headers, timeout):
            # One limiter covers searches and concurrent detail requests.
            with self._request_lock:
                time.sleep(max(0, self._next_request - time.monotonic()))
                try:
                    payload = self.fetch_json(url, headers, timeout)
                finally:
                    self._next_request = time.monotonic() + self.request_delay
                if not isinstance(payload, dict):
                    raise TypeError("Invalid product API response")
                if "/search?" in url and not isinstance(payload.get("products"), list):
                    raise ValueError("Missing products in API response")
                products = payload.get("products", [])
                if isinstance(payload.get("product"), dict):
                    products = [payload["product"]]
                for raw in products:
                    if isinstance(raw, dict) and raw.get("code"):
                        snapshots[str(raw["code"])] = raw
                return payload

        catalog = OpenFoodFactsCatalog(fetch_json=fetch, page_size=50)
        result = catalog.search(category=category, region="CN")
        failures = 0
        # Rotate through retained candidates that have fallen out of the search page.
        with self.store.connect() as db:
            retained = db.execute(
                "SELECT id FROM candidates WHERE id IN (SELECT id FROM memberships WHERE category=?) ORDER BY last_checked_at,id",
                (category,),
            ).fetchall()
        rechecked = 0
        for row in retained:
            if row["id"] in snapshots:
                continue
            if rechecked >= 5:
                break
            rechecked += 1
            try:
                catalog._fetch_detail(row["id"])
            except Exception:
                logger.exception("Retained candidate recheck failed for %s", row["id"])
                failures += 1
        for raw in snapshots.values():
            try:
                self.store.ingest(raw, category)
            except (ValueError, TypeError, OverflowError, OSError):
                failures += 1
        detail_failed = any(
            item.get("reason_code") == "LIVE_CATALOG_RECORD_UNAVAILABLE"
            for item in result.rejected
        )
        return ("partial" if failures or detail_failed else "completed"), {
            "received_count": len(snapshots),
            "invalid_record_count": failures,
            "detail_request_failed": detail_failed,
            "page_limit": 50,
            "retained_rechecked_count": rechecked,
        }

    def _complete_candidates(self):
        """Revisit every retained identity; preserve unknown fields and failures."""
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT c.id,c.category FROM candidates c LEFT JOIN completion_queue q ON q.product_id='off:'||c.id "
                "ORDER BY CASE WHEN q.status='pending' THEN 0 ELSE 1 END,COALESCE(q.demand_count,0) DESC,c.last_checked_at,c.id"
            ).fetchall()
        failures = 0
        for row in rows:
            try:
                query = urlencode({"fields": OFF_FIELDS})
                with self._request_lock:
                    time.sleep(max(0, self._next_request - time.monotonic()))
                    try:
                        payload = self.fetch_json(
                            f"https://world.openfoodfacts.org/api/v2/product/{row['id']}?{query}",
                            {
                                "User-Agent": os.getenv(
                                    "FOOD_LABEL_OPENFOODFACTS_USER_AGENT",
                                    "LabelLensHealth/0.3 product-evidence-refresh",
                                )
                            },
                            8.0,
                        )
                    finally:
                        self._next_request = time.monotonic() + self.request_delay
                raw = payload.get("product")
                if not isinstance(raw, dict) or str(raw.get("code")) != row["id"]:
                    raise ValueError("Detail response does not match requested barcode")
                self.store.ingest(raw, row["category"])
                from .rag import ingredient_gaps

                _, available = ingredient_gaps(raw)
                self.store.reconcile_gaps(row["id"], available)
            except Exception:
                failures += 1
                logger.exception("Detail completion failed for candidate %s", row["id"])
        return {
            "attempted_count": len(rows),
            "failed_count": failures,
            "scope": "retained_candidate_details",
        }

    def _enrich_images(self):
        if not self.ocr_service:
            return
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT candidates.* FROM candidates LEFT JOIN ocr_attempts USING(id) "
                "LEFT JOIN completion_queue q ON q.product_id='off:'||candidates.id "
                "WHERE COALESCE(json_extract(ocr_draft,'$.complete'),0)=0 "
                "ORDER BY CASE WHEN q.status='pending' THEN 0 ELSE 1 END,COALESCE(q.demand_count,0) DESC,COALESCE(ocr_attempts.attempted_at,''),first_seen_at"
            ).fetchall()
        attempted = failures = missing = 0
        for row in rows:
            raw = json.loads(row["payload"])
            previous = json.loads(row["ocr_draft"]) if row["ocr_draft"] else {}
            images = dict(previous.get("images", {}))
            candidate_attempted = False
            for kind, required in (
                ("ingredients", "ingredients"),
                ("nutrition", "nutrition_table"),
            ):
                url = full_label_image(raw, kind)
                if not url:
                    missing += 1
                    continue
                version = digest([url])
                if images.get(kind, {}).get("source_url") == url:
                    continue
                cached = self.batch.cached_image_text(version)
                if cached:
                    images[kind] = cached
                    candidate_attempted = True
                    continue
                if not self.batch.attempt_due(row["id"], kind, version):
                    continue
                attempted += 1
                candidate_attempted = True
                with self.store.connect() as db:
                    db.execute(
                        "INSERT OR REPLACE INTO ocr_attempts VALUES (?,?)",
                        (row["id"], utc_now()),
                    )
                content = None
                try:
                    content, media_type = self.fetch_image(url)
                    response = asyncio.run(
                        self.ocr_service.analyze(
                            content=content, file_name=kind, media_type=media_type
                        )
                    )
                    fields = [
                        field.model_dump(mode="json") for field in response.fields
                    ]
                    if not any(
                        field.get("name") == required
                        and (
                            str(field.get("raw_text") or "").strip()
                            or (field.get("nutrition_table") or {}).get("rows")
                        )
                        for field in fields
                    ):
                        raise ValueError(
                            "OCR did not extract the expected label section"
                        )
                    images[kind] = {
                        "source_url": url,
                        "image_sha256": sha256(content).hexdigest(),
                        "captured_at": utc_now(),
                        "fields": fields,
                    }
                    self.batch.cache_image_text(images[kind])
                    self.batch.record_attempt(
                        row["id"],
                        kind,
                        version,
                        status="complete",
                        content_hash=sha256(content).hexdigest(),
                    )
                except Exception as exc:
                    self.batch.record_attempt(
                        row["id"],
                        kind,
                        version,
                        status="permanent_failure"
                        if isinstance(exc, ValueError)
                        or type(exc).__name__ == "ImageQualityError"
                        else "transient_failure",
                        error_code=type(exc).__name__,
                        content_hash=sha256(content).hexdigest() if content else None,
                    )
                    failures += 1
                    logger.exception(
                        "Packaging OCR failed for candidate %s (%s)", row["id"], kind
                    )
            if candidate_attempted and images:
                self.store.save_ocr_draft(
                    row["id"],
                    {
                        "source_record_version": raw.get("last_modified_t"),
                        "images": images,
                        "complete": all(
                            kind in images for kind in ("ingredients", "nutrition")
                        ),
                        "requires_identity_and_label_review": True,
                    },
                    expected_hash=row["content_hash"],
                )
        return {
            "attempted_count": attempted,
            "failed_count": failures,
            "missing_image_count": missing,
            "scope": "unverified_drafts",
        }

    def run_once(self, *, force=False):
        self.store.path.parent.mkdir(parents=True, exist_ok=True)
        with self.store.path.with_suffix(".worker.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"status": "already_running"}
            jobs = {}
            for category in self.categories:
                name = f"openfoodfacts:{category}"
                if not force and not self.store.due(name):
                    continue
                try:
                    status, summary = self._refresh_category(category)
                except Exception:
                    logger.exception("Product refresh failed for %s", category)
                    status, summary = (
                        "unavailable",
                        {"message": "来源暂时不可用，保留上次资料"},
                    )
                self.store.record_run(name, status, summary)
                jobs[name] = status
            if force or self.store.due("product_details"):
                summary = self._complete_candidates()
                status = "partial" if summary["failed_count"] else "completed"
                self.store.record_run("product_details", status, summary)
                jobs["product_details"] = status
            if self.ocr_service and (force or self.store.due("packaging_ocr")):
                summary = self._enrich_images()
                status = "partial" if summary["failed_count"] else "completed"
                self.store.record_run("packaging_ocr", status, summary)
                jobs["packaging_ocr"] = status
            if force or self.store.due("official_sources"):
                try:
                    result = self.discovery.refresh()
                    status, summary = (
                        result.status,
                        {
                            key: value
                            for key, value in result.summary.items()
                            if key != "items"
                        },
                    )
                except Exception:
                    logger.exception("Official discovery refresh failed")
                    status, summary = (
                        "unavailable",
                        {"message": "官方来源暂时不可用，保留上次资料"},
                    )
                self.store.record_run("official_sources", status, summary)
                jobs["official_sources"] = status
            # Local reconciliation runs even between monthly network refreshes:
            # new reviewed photos can close/reopen gaps without another API call.
            from .application import AlternativeEvidenceService

            try:
                _, summary = AlternativeEvidenceService(
                    self.discovery, self.store
                ).synchronize()
                completion_status = "completed"
            except (OSError, ValueError, sqlite3.Error):
                logger.exception("Official evidence reconciliation failed")
                summary = {"message": "补齐对账失败，保留现有任务"}
                completion_status = "unavailable"
            self.store.record_run("official_completion", completion_status, summary)
            jobs["official_completion"] = completion_status
            if any(job != "official_completion" for job in jobs) or self.store.due(
                "batch_assessment"
            ):
                report = self.batch.assess_all()
                self.store.record_run(
                    "batch_assessment", "completed", report["summary"]
                )
            return {
                "status": "partial"
                if any(status != "completed" for status in jobs.values())
                else "completed",
                "jobs": jobs,
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--ocr",
        action=argparse.BooleanOptionalAction,
        default=os.getenv("FOOD_LABEL_KNOWLEDGE_OCR", "1") == "1",
        help="Use configured real OCR for packaging drafts (enabled by default)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    ocr = None
    if args.ocr:
        from food_label_agent.ocr.paddle_provider import create_ocr_provider
        from food_label_agent.ocr.service import OCRService

        os.environ.setdefault("FOOD_LABEL_OCR_PROVIDER", "tencent")
        ocr = OCRService(create_ocr_provider())
    categories = [
        part.strip()
        for part in os.getenv(
            "FOOD_LABEL_KNOWLEDGE_CATEGORIES", "breakfast_cereal,dairy,drink"
        ).split(",")
        if part.strip()
    ]
    worker = KnowledgeRefreshWorker(categories=categories, ocr_service=ocr)
    stopped = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.set())
    while not stopped.is_set():
        print(
            json.dumps(worker.run_once(force=args.force), ensure_ascii=False),
            flush=True,
        )
        if args.once:
            break
        args.force = False
        stopped.wait(30)


if __name__ == "__main__":
    main()
