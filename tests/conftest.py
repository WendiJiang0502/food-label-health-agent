from __future__ import annotations

import pytest

from food_label_agent.regulations.service import clear_regulation_caches


@pytest.fixture(autouse=True)
def use_offline_rag_profile_for_tests(monkeypatch):
    """Keep ordinary unit tests deterministic and free of remote RAG calls."""

    monkeypatch.setenv("FOOD_LABEL_RAG_PROFILE", "hybrid_tfidf")
    clear_regulation_caches()
    yield
    clear_regulation_caches()
