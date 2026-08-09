"""Small dependency-free BM25 index suitable for clause-level baselines."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

_LATIN_OR_NUMBER = re.compile(r"[a-z]+|\d+(?:\.\d+)*", re.IGNORECASE)
_HAN_RUN = re.compile(r"[\u3400-\u9fff]+")


def tokenize(text: str) -> tuple[str, ...]:
    """Tokenize standards using Latin terms plus Chinese uni/bi/tri-grams."""

    compact = text.casefold().replace("\u3000", " ")
    tokens = list(_LATIN_OR_NUMBER.findall(compact))
    for run in _HAN_RUN.findall(compact):
        tokens.extend(run)
        tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
        tokens.extend(run[index : index + 3] for index in range(len(run) - 2))
    return tuple(tokens)


@dataclass(frozen=True, slots=True)
class BM25Hit:
    index: int
    score: float


class BM25Index:
    def __init__(
        self,
        documents: Iterable[str],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        tokenized = [tokenize(document) for document in documents]
        self._term_frequencies = [Counter(tokens) for tokens in tokenized]
        self._lengths = [len(tokens) for tokens in tokenized]
        self._average_length = (
            sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        )
        self._k1 = k1
        self._b = b
        document_frequency: Counter[str] = Counter()
        for tokens in tokenized:
            document_frequency.update(set(tokens))
        count = len(tokenized)
        self._idf = {
            term: math.log(1 + (count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def search(self, query: str) -> tuple[BM25Hit, ...]:
        query_terms = Counter(tokenize(query))
        hits: list[BM25Hit] = []
        for index, frequencies in enumerate(self._term_frequencies):
            score = 0.0
            length = self._lengths[index]
            length_ratio = (
                length / self._average_length if self._average_length else 0.0
            )
            for term, query_frequency in query_terms.items():
                term_frequency = frequencies.get(term, 0)
                if not term_frequency:
                    continue
                denominator = term_frequency + self._k1 * (
                    1 - self._b + self._b * length_ratio
                )
                score += (
                    self._idf.get(term, 0.0)
                    * term_frequency
                    * (self._k1 + 1)
                    / denominator
                    * query_frequency
                )
            if score > 0:
                hits.append(BM25Hit(index=index, score=score))
        return tuple(sorted(hits, key=lambda hit: hit.score, reverse=True))
