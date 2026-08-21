"""Dense embedding and independent reranking providers for RAG 2.0."""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_RAG_PROFILE = "hybrid_dense_rerank"


class RAGProviderError(RuntimeError):
    pass


class DenseEmbeddingProvider(Protocol):
    provider: str
    model: str

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...


class IndependentReranker(Protocol):
    provider: str
    model: str

    def rank(
        self, query: str, candidates: Sequence[dict[str, str]]
    ) -> tuple[str, ...]: ...


Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class RAG2Settings:
    profile: str = DEFAULT_RAG_PROFILE
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 1024
    reranker_model: str = "gpt-5.6-terra"
    timeout_seconds: float = 20.0
    api_key: str | None = None

    @classmethod
    def from_environment(cls) -> RAG2Settings:
        profile = os.getenv("FOOD_LABEL_RAG_PROFILE", DEFAULT_RAG_PROFILE).strip()
        if profile not in {
            "bm25",
            "hybrid_tfidf",
            "hybrid_dense",
            "hybrid_dense_rerank",
        }:
            raise ValueError("Unsupported FOOD_LABEL_RAG_PROFILE")
        dimensions = int(os.getenv("FOOD_LABEL_RAG_EMBEDDING_DIMENSIONS", "1024"))
        if not 128 <= dimensions <= 3072:
            raise ValueError("Embedding dimensions must be between 128 and 3072")
        timeout = float(os.getenv("FOOD_LABEL_RAG_TIMEOUT_SECONDS", "20"))
        if not 1 <= timeout <= 120:
            raise ValueError("RAG timeout must be between 1 and 120 seconds")
        return cls(
            profile=profile,
            embedding_model=os.getenv(
                "FOOD_LABEL_RAG_EMBEDDING_MODEL", "text-embedding-3-large"
            ).strip(),
            embedding_dimensions=dimensions,
            reranker_model=os.getenv(
                "FOOD_LABEL_RAG_RERANKER_MODEL", "gpt-5.6-terra"
            ).strip(),
            timeout_seconds=timeout,
            api_key=os.getenv("OPENAI_API_KEY") or None,
        )


class OpenAIDenseEmbeddingProvider:
    provider = "openai"

    def __init__(
        self, settings: RAG2Settings, *, transport: Transport | None = None
    ) -> None:
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions
        self.api_key = settings.api_key
        self.timeout = settings.timeout_seconds
        self._transport = transport or _post_json
        self._cache: dict[str, tuple[float, ...]] = {}

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not self.api_key:
            raise RAGProviderError("rag_embedding_api_key_missing")
        clean = tuple(" ".join(text.split()) for text in texts)
        if any(not text for text in clean):
            raise RAGProviderError("rag_embedding_empty_input")
        missing = tuple(
            dict.fromkeys(text for text in clean if text not in self._cache)
        )
        if missing:
            response = self._transport(
                OPENAI_EMBEDDINGS_URL,
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                {
                    "model": self.model,
                    "input": list(missing),
                    "dimensions": self.dimensions,
                    "encoding_format": "float",
                },
                self.timeout,
            )
            rows = sorted(response.get("data", []), key=lambda item: item["index"])
            if len(rows) != len(missing):
                raise RAGProviderError("rag_embedding_response_invalid")
            for text, row in zip(missing, rows, strict=True):
                self._cache[text] = _normalize(
                    tuple(float(x) for x in row["embedding"])
                )
        return tuple(self._cache[text] for text in clean)


class OpenAIIndependentReranker:
    provider = "openai"

    def __init__(
        self, settings: RAG2Settings, *, transport: Transport | None = None
    ) -> None:
        self.model = settings.reranker_model
        self.api_key = settings.api_key
        self.timeout = settings.timeout_seconds
        self._transport = transport or _post_json

    def rank(self, query: str, candidates: Sequence[dict[str, str]]) -> tuple[str, ...]:
        if not self.api_key:
            raise RAGProviderError("rag_reranker_api_key_missing")
        ids = [item["evidence_id"] for item in candidates]
        if not ids:
            return ()
        response = self._transport(
            OPENAI_RESPONSES_URL,
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            {
                "model": self.model,
                "instructions": (
                    "Score every supplied official regulation clause from 0 to 100 for "
                    "how directly it answers the Chinese food-label query. Provide one "
                    "score for every supplied evidence ID. Do not answer the query."
                ),
                "input": json.dumps(
                    {"query": query, "candidates": list(candidates)},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "regulation_rerank",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "scores": {
                                    "type": "object",
                                    "properties": {
                                        evidence_id: {
                                            "type": "integer",
                                            "minimum": 0,
                                            "maximum": 100,
                                        }
                                        for evidence_id in ids
                                    },
                                    "required": ids,
                                    "additionalProperties": False,
                                }
                            },
                            "required": ["scores"],
                            "additionalProperties": False,
                        },
                    }
                },
                "reasoning": {"effort": "low"},
                "max_output_tokens": max(256, len(ids) * 32),
                "store": False,
            },
            self.timeout,
        )
        try:
            parsed = json.loads(_response_output_text(response))
            scores = parsed["scores"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RAGProviderError("rag_reranker_response_invalid") from exc
        if not isinstance(scores, dict) or set(scores) != set(ids):
            raise RAGProviderError("rag_reranker_response_invalid")
        original_position = {
            evidence_id: index for index, evidence_id in enumerate(ids)
        }
        return tuple(
            sorted(
                ids,
                key=lambda evidence_id: (
                    -int(scores[evidence_id]),
                    original_position[evidence_id],
                ),
            )
        )


def create_semantic_providers(
    settings: RAG2Settings,
) -> tuple[DenseEmbeddingProvider | None, IndependentReranker | None]:
    if settings.profile in {"bm25", "hybrid_tfidf"}:
        return None, None
    dense = OpenAIDenseEmbeddingProvider(settings)
    reranker = (
        OpenAIIndependentReranker(settings)
        if settings.profile == "hybrid_dense_rerank"
        else None
    )
    return dense, reranker


def rag2_public_status(settings: RAG2Settings | None = None) -> dict[str, Any]:
    configured = settings or RAG2Settings.from_environment()
    uses_remote = configured.profile in {"hybrid_dense", "hybrid_dense_rerank"}
    return {
        "profile": configured.profile,
        "embedding_model": configured.embedding_model if uses_remote else None,
        "reranker_model": (
            configured.reranker_model
            if configured.profile == "hybrid_dense_rerank"
            else None
        ),
        "configured": not uses_remote or bool(configured.api_key),
        "remote_processing": uses_remote,
    }


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding dimensions do not match")
    return sum(a * b for a, b in zip(left, right, strict=True))


def _normalize(vector: tuple[float, ...]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        raise RAGProviderError("rag_embedding_zero_vector")
    return tuple(value / norm for value in vector)


def _response_output_text(response: dict[str, Any]) -> str:
    if response.get("status") != "completed":
        raise RAGProviderError("rag_reranker_response_incomplete")
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return str(content.get("text", ""))
    raise RAGProviderError("rag_reranker_response_missing_output")


def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise RAGProviderError("rag_provider_unavailable") from exc
