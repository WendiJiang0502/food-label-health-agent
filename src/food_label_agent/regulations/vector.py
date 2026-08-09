"""Auditable sparse embeddings for offline regulation vector retrieval.

The implementation intentionally avoids a remote embedding service.  It builds
TF-IDF vectors over each already date-filtered candidate set and enriches the
text with a small, reviewable domain-concept map for common Chinese paraphrases.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from .bm25 import tokenize

_DOMAIN_CONCEPTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "allergencrosscontactconcept",
        ("可能含有", "可能带入", "同线生产", "同一生产线", "共用生产线", "交叉污染"),
    ),
    (
        "milkallergenconcept",
        ("乳清", "牛奶", "奶粉", "乳粉", "酪蛋白", "乳制品", "乳及乳制品"),
    ),
    (
        "allergenlabelconcept",
        ("过敏原", "致敏物质", "过敏提示", "致敏提示"),
    ),
    (
        "nutritionclaimconcept",
        ("营养声称", "无糖", "低糖", "0蔗糖", "零蔗糖", "无蔗糖", "不添加糖"),
    ),
    (
        "foodadditiveconcept",
        ("食品添加剂", "防腐剂", "护色剂", "甜味剂", "增稠剂", "稳定剂"),
    ),
)


def expand_domain_concepts(text: str) -> str:
    """Append stable concept tokens when reviewed Chinese aliases are present."""

    compact = "".join(text.casefold().split())
    concepts = [
        concept
        for concept, aliases in _DOMAIN_CONCEPTS
        if any(alias.casefold() in compact for alias in aliases)
    ]
    return " ".join((text, *concepts))


@dataclass(frozen=True, slots=True)
class VectorHit:
    index: int
    score: float


class TfidfVectorIndex:
    """Cosine retrieval over sublinear TF-IDF sparse embedding vectors."""

    def __init__(self, documents: Iterable[str]) -> None:
        tokenized = [
            tokenize(expand_domain_concepts(document)) for document in documents
        ]
        document_frequency: Counter[str] = Counter()
        for tokens in tokenized:
            document_frequency.update(set(tokens))
        count = len(tokenized)
        self._idf = {
            term: math.log((1 + count) / (1 + frequency)) + 1.0
            for term, frequency in document_frequency.items()
        }
        self._vectors = tuple(self._vector(tokens) for tokens in tokenized)

    def search(self, query: str) -> tuple[VectorHit, ...]:
        query_vector = self._vector(tokenize(expand_domain_concepts(query)))
        if not query_vector:
            return ()
        hits: list[VectorHit] = []
        for index, document_vector in enumerate(self._vectors):
            score = sum(
                weight * document_vector.get(term, 0.0)
                for term, weight in query_vector.items()
            )
            if score > 0:
                hits.append(VectorHit(index=index, score=score))
        return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.index)))

    def _vector(self, tokens: Iterable[str]) -> dict[str, float]:
        frequencies = Counter(token for token in tokens if token in self._idf)
        weighted = {
            term: (1.0 + math.log(frequency)) * self._idf[term]
            for term, frequency in frequencies.items()
        }
        norm = math.sqrt(sum(value * value for value in weighted.values()))
        if not norm:
            return {}
        return {term: value / norm for term, value in weighted.items()}
