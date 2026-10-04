"""Shared alternative-search evidence orchestration for every user entrypoint."""

import logging
import os
import sqlite3
from contextlib import contextmanager

from .completion import reconcile_completion_tasks, record_screening_gaps
from .discovery import OfficialProductDiscovery
from .evidence import (
    active_knowledge_store,
    active_official_items,
    sync_official_evidence,
)
from .knowledge import ProductKnowledgeStore
from .source_screening import screen_official_sources

logger = logging.getLogger(__name__)


class AlternativeEvidenceService:
    def __init__(self, discovery=None, store=None):
        self.discovery = discovery or OfficialProductDiscovery()
        self.store = store or ProductKnowledgeStore(
            os.getenv("FOOD_LABEL_PRODUCT_RAG_DB")
            or self.discovery.queue_path.with_name("product-knowledge.sqlite3")
        )

    def synchronize(self):
        summary = self.discovery.status()
        index = sync_official_evidence(self.store, summary["items"])
        approved = self.discovery.approved_products()
        completion = reconcile_completion_tasks(self.store, summary["items"], approved)
        return summary, {"index": index, "completion": completion}

    @contextmanager
    def scope(self, items):
        token = active_knowledge_store.set(self.store)
        snapshot_token = active_official_items.set(items)
        try:
            yield
        finally:
            active_knowledge_store.reset(token)
            active_official_items.reset(snapshot_token)

    def prepare(self):
        try:
            summary, _ = self.synchronize()
            return {"status": "cached", "summary": summary, "warnings": []}
        except (OSError, ValueError, sqlite3.Error):
            logger.exception("Official evidence synchronization unavailable")
            return {
                "status": "unavailable",
                "summary": {"items": []},
                "warnings": ["official_evidence_unavailable"],
            }

    def enrich(self, result, request, discovery):
        # Screening and retrieval see the same source snapshot for this request.
        result["discovery"] = discovery
        screening = screen_official_sources(discovery["summary"]["items"], request)
        if discovery["status"] == "unavailable":
            screening["status"] = "unavailable"
        try:
            screening["completion_queue"] = record_screening_gaps(
                self.store, screening, request.request_id
            )
        except (OSError, sqlite3.Error):
            screening["completion_queue"] = {"status": "unavailable"}
        result["source_screening"] = screening
        return result
