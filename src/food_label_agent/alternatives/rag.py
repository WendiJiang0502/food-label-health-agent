"""Product evidence RAG: hybrid retrieval, provenance and demand-driven gaps.

Retrieval never promotes external data or OCR drafts into verified labels.
The recommendation service independently checks every catalog candidate.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256

from food_label_agent.regulations.bm25 import BM25Index
from food_label_agent.regulations.semantic import (
    OpenAIDenseEmbeddingProvider,
    OpenAIIndependentReranker,
    RAG2Settings,
    cosine_similarity,
    rag2_public_status,
)
from food_label_agent.regulations.vector import TfidfVectorIndex

from .batch import BatchKnowledge
from .catalog import CATEGORY_LABELS, USE_CASES
from .field_evidence import catalog_field_evidence
from .intent import parse_product_intent
from .knowledge import ProductKnowledgeStore

logger = logging.getLogger(__name__)

_HEALTH_WORDS = {
    "sugar_control": "糖含量 糖更少",
    "blood_sugar": "糖含量 碳水化合物",
    "blood_pressure": "钠含量 盐更少",
    "blood_lipids": "脂肪 饱和脂肪",
    "weight": "能量",
    "gut": "膳食纤维",
    "child": "糖含量 钠含量",
}
_NUTRIENTS = {
    "sugars_100g": "糖",
    "sodium_100g": "钠",
    "fat_100g": "脂肪",
    "saturated-fat_100g": "饱和脂肪",
    "fiber_100g": "膳食纤维",
    "proteins_100g": "蛋白质",
    "carbohydrates_100g": "碳水化合物",
    "energy-kj_100g": "能量千焦",
    "energy-kcal_100g": "能量千卡",
}


def ingredient_gaps(raw, query=""):
    fields = set()
    if raw.get("ingredients_text_zh") or raw.get("ingredients_text"):
        fields.add("ingredients")
    nutrients = raw.get("nutriments") or {}
    for key in _NUTRIENTS:
        if nutrients.get(key) is not None:
            fields.add(key)
    required = {"ingredients"}
    intent = parse_product_intent(query)
    nutrient_keys = {
        "sugars": "sugars_100g",
        "sodium": "sodium_100g",
        "protein": "proteins_100g",
        "fat": "fat_100g",
        "saturated_fat": "saturated-fat_100g",
        "dietary_fiber": "fiber_100g",
        "energy": "energy-kj_100g",
    }
    required.update(nutrient_keys[g["nutrient"]] for g in intent["nutrition_goals"])
    if intent["preparation"]:
        required.add("preparation_evidence")
    for signals, key in (
        (("糖",), "sugars_100g"),
        (("钠", "盐"), "sodium_100g"),
        (("蛋白",), "proteins_100g"),
        (("脂肪",), "fat_100g"),
        (("饱和脂肪",), "saturated-fat_100g"),
        (("纤维",), "fiber_100g"),
        (("能量", "热量"), "energy-kj_100g"),
    ):
        if any(word in query for word in signals):
            required.add(key)
    return sorted(required - fields), fields


def _document(product_id, name, text, tier, source_url, version, categories, **extra):
    text = text[:12000]
    digest = sha256(f"{product_id}\0{tier}\0{version}\0{text}".encode()).hexdigest()
    return {
        "product_id": product_id,
        "display_name": name,
        "text": text,
        "evidence_id": f"product:{digest[:24]}",
        "evidence_hash": digest,
        "tier": tier,
        "source_url": source_url,
        "source_version": version,
        "categories": categories,
        **extra,
    }


def product_rag_public_status():
    settings = RAG2Settings.from_environment()
    return rag2_public_status(
        replace(
            settings,
            profile=os.getenv("FOOD_LABEL_PRODUCT_RAG_PROFILE", settings.profile),
        )
    )


class ProductRAG:
    def __init__(self, store=None, *, profile=None, embedding=None, reranker=None):
        self.store = store or ProductKnowledgeStore(
            os.getenv("FOOD_LABEL_PRODUCT_RAG_DB") or None
        )
        settings = RAG2Settings.from_environment()
        self.profile = profile or os.getenv(
            "FOOD_LABEL_PRODUCT_RAG_PROFILE", settings.profile
        )
        if self.profile not in {
            "bm25",
            "hybrid_tfidf",
            "hybrid_dense",
            "hybrid_dense_rerank",
        }:
            raise ValueError("Unsupported product RAG profile")
        settings = replace(settings, profile=self.profile)
        self.embedding = embedding or (
            OpenAIDenseEmbeddingProvider(settings) if "dense" in self.profile else None
        )
        self.reranker = reranker or (
            OpenAIIndependentReranker(
                settings,
                document_kind="product evidence record",
                schema_name="product_rerank",
            )
            if self.profile == "hybrid_dense_rerank"
            else None
        )

    def _documents(self, request, records, query):
        categories = list(
            dict.fromkeys([request.category, *request.substitute_categories])
        )
        documents = []
        if request.jurisdiction != "CN":
            return documents
        known_ids = set()
        for record in records:
            if (
                record.region != request.region
                or record.category not in categories
                or record.product_id in request.exclude_product_ids
            ):
                continue
            label = record.label
            reviewed = label.source_verified_at or label.confirmed_at
            if (
                reviewed > request.applicable_date
                or request.applicable_date - reviewed > timedelta(days=550)
                or (
                    label.valid_through
                    and label.valid_through < request.applicable_date
                )
            ):
                continue
            text = "\n".join(
                [
                    record.display_name,
                    record.brand,
                    CATEGORY_LABELS.get(record.category, record.category),
                    record.use_case,
                    label.ingredients_text or "",
                    label.allergen_statement or "",
                    label.nutrition_basis_text or "",
                    json.dumps(label.nutrition_rows or [], ensure_ascii=False),
                ]
            )
            documents.append(
                _document(
                    record.product_id,
                    record.display_name,
                    text,
                    "catalog_evidence",
                    label.source_url,
                    label.content_hash,
                    [record.category],
                    field_evidence=catalog_field_evidence(record),
                    missing_fields=[],
                    verified_at=str(label.source_verified_at or label.confirmed_at),
                    checked_at=None,
                    catalog_candidate=True,
                )
            )
            known_ids.add(record.product_id)
        # The imported discovery corpus currently covers China-tagged candidates only.
        if request.region != "CN":
            return documents
        with self.store.connect() as db:
            marks = ",".join("?" for _ in categories)
            rows = db.execute(
                f"SELECT * FROM candidates WHERE id IN (SELECT id FROM memberships WHERE category IN ({marks})) ORDER BY id",
                categories,
            ).fetchall()
        batch = BatchKnowledge(self.store)
        for row in rows:
            if row["last_checked_at"][:10] > request.applicable_date.isoformat():
                continue
            pid = f"off:{row['id']}"
            if pid in known_ids or pid in request.exclude_product_ids:
                continue
            raw = json.loads(row["payload"])
            name = raw.get("product_name_zh") or raw.get("product_name") or row["id"]
            missing, _ = ingredient_gaps(raw, query)
            fields = self.store.field_evidence(row["id"])
            admission = batch.item(row["id"])
            missing = sorted(
                set(missing) | {f"conflict:{field}" for field in fields["conflicts"]}
            )
            text = "\n".join(
                [
                    name,
                    raw.get("brands") or "",
                    CATEGORY_LABELS.get(row["category"], row["category"]),
                    USE_CASES.get(row["category"], ""),
                    raw.get("ingredients_text_zh") or raw.get("ingredients_text") or "",
                    json.dumps(raw.get("nutriments") or {}, ensure_ascii=False),
                ]
            )
            url = f"https://world.openfoodfacts.org/product/{row['id']}"
            documents.append(
                _document(
                    pid,
                    name,
                    text,
                    "external_unverified",
                    url,
                    row["content_hash"],
                    categories,
                    field_evidence=fields,
                    admission={
                        "capabilities": admission["capabilities"],
                        "accepted_evidence_ids": admission["accepted_evidence_ids"],
                        "policy_version": admission["policy_version"],
                    },
                    missing_fields=missing or ["label_review"],
                    verified_at=None,
                    checked_at=row["last_checked_at"],
                    catalog_candidate=False,
                )
            )
            if row["ocr_draft"]:
                draft = json.loads(row["ocr_draft"])
                for kind, evidence in draft.get("images", {}).items():
                    content = "\n".join(
                        str(field.get("raw_text") or "")
                        for field in evidence.get("fields", [])
                    )
                    if content.strip():
                        documents.append(
                            _document(
                                pid,
                                name,
                                f"{name}\n{kind}\n{content}",
                                "ocr_draft",
                                evidence.get("source_url"),
                                evidence.get("image_sha256"),
                                categories,
                                field_evidence={
                                    **fields,
                                    "observations": [
                                        f
                                        for f in fields["observations"]
                                        if f["source_version"]
                                        == evidence.get("image_sha256")
                                    ],
                                },
                                missing_fields=["label_review"],
                                verified_at=None,
                                checked_at=evidence.get("captured_at"),
                                catalog_candidate=False,
                            )
                        )
        return documents

    def _vectors(self, documents):
        provider_key = f"{self.embedding.provider}:{self.embedding.model}:{getattr(self.embedding, 'dimensions', '')}"
        keys = [
            sha256(f"{provider_key}\0{doc['text']}".encode()).hexdigest()
            for doc in documents
        ]
        vectors = {}
        with self.store.connect() as db:
            for key in keys:
                row = db.execute(
                    "SELECT vector FROM product_vectors WHERE cache_key=?", (key,)
                ).fetchone()
                if row:
                    vectors[key] = tuple(json.loads(row[0]))
        missing = list(dict.fromkeys(key for key in keys if key not in vectors))
        texts = dict(zip(keys, (doc["text"] for doc in documents), strict=True))
        for start in range(0, len(missing), 32):
            batch = missing[start : start + 32]
            embedded = self.embedding.embed([texts[key] for key in batch])
            if len(embedded) != len(batch):
                raise ValueError("Product embedding count mismatch")
            with self.store.connect() as db:
                for key, vector in zip(batch, embedded, strict=True):
                    vectors[key] = vector
                    db.execute(
                        "INSERT OR REPLACE INTO product_vectors VALUES (?,?)",
                        (key, json.dumps(vector)),
                    )
        return [vectors[key] for key in keys]

    def search(self, request, records):
        query = " ".join(
            filter(
                None,
                [
                    request.retrieval_query,
                    request.current_product_name,
                    CATEGORY_LABELS.get(request.category, request.category),
                    *(
                        _HEALTH_WORDS.get(concern, "")
                        for concern in request.health_concerns
                    ),
                ],
            )
        )
        documents = self._documents(request, records, query)
        if not documents:
            return {
                "search_intent": parse_product_intent(request.retrieval_query),
                "status": "no_evidence",
                "profile": self.profile,
                "items": [],
                "ranked_product_ids": [],
                "warnings": [],
                "queued_count": 0,
            }
        texts = [doc["text"] for doc in documents]
        lexical = [hit.index for hit in BM25Index(texts).search(query)]
        rankings = [lexical]
        warnings = []
        effective = self.profile
        try:
            if self.embedding:
                vectors = self._vectors(documents)
                qvector = self.embedding.embed([query])[0]
                rankings.append(
                    sorted(
                        range(len(documents)),
                        key=lambda i: -cosine_similarity(qvector, vectors[i]),
                    )
                )
            elif self.profile == "hybrid_tfidf":
                rankings.append(
                    [hit.index for hit in TfidfVectorIndex(texts).search(query)]
                )
        except Exception:
            logger.exception(
                "Product embedding failed; using explicit keyword fallback"
            )
            # Explicit, visible degradation; deterministic safety gates still run.
            warnings.append("product_embedding_unavailable")
            effective = "bm25"
        scores = {}
        for ranking in rankings:
            for rank, index in enumerate(ranking):
                scores[index] = scores.get(index, 0) + 1 / (60 + rank + 1)
        ordered = sorted(scores, key=lambda i: (-scores[i], i))
        if self.reranker and effective != "bm25" and ordered:
            selected = ordered[:20]
            ids = {documents[i]["evidence_id"]: i for i in selected}
            try:
                ranked = self.reranker.rank(
                    query,
                    [
                        {
                            "evidence_id": documents[i]["evidence_id"],
                            "text": documents[i]["text"],
                        }
                        for i in selected
                    ],
                )
                if len(ranked) != len(ids) or set(ranked) != set(ids):
                    raise ValueError(
                        "Reranker returned unknown or missing evidence IDs"
                    )
                ordered = [ids[eid] for eid in ranked] + ordered[len(selected) :]
            except Exception:
                logger.exception("Product reranking failed; retaining hybrid order")
                warnings.append("product_reranker_unavailable")
                effective = "hybrid_dense"
        items = []
        queued = set()
        for index in ordered[:20]:
            doc = documents[index]
            if not doc["catalog_candidate"] and doc["product_id"] not in queued:
                related = [
                    item
                    for item in documents
                    if item["product_id"] == doc["product_id"]
                    and not item["catalog_candidate"]
                ]
                missing = sorted(
                    {field for item in related for field in item["missing_fields"]}
                )
                version = sha256(
                    "\0".join(
                        sorted(item["evidence_hash"] for item in related)
                    ).encode()
                ).hexdigest()
                self.store.prioritize(doc["product_id"], version, missing)
                queued.add(doc["product_id"])
            items.append(
                {key: value for key, value in doc.items() if key != "text"}
                | {
                    "excerpt": doc["text"][:500],
                    "recommendation_eligible": False,
                    "retrieval_score": scores[index],
                }
            )
        return {
            "search_intent": parse_product_intent(request.retrieval_query),
            "status": "degraded" if warnings else "retrieved",
            "profile": effective,
            "requested_profile": self.profile,
            "items": items,
            "ranked_product_ids": list(
                dict.fromkeys(documents[i]["product_id"] for i in ordered)
            ),
            "warnings": warnings,
            "queued_count": len(queued),
            "explanation": "检索相关性用于寻找候选；推荐仍需通过标签证据和个人约束复核。",
        }
