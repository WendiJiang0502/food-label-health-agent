from __future__ import annotations

import pytest

from food_label_agent.regulations.service import get_default_regulation_store


@pytest.fixture(autouse=True)
def use_offline_rag_profile_for_tests(monkeypatch):
    """Keep ordinary unit tests deterministic and free of remote RAG calls."""

    monkeypatch.setenv("FOOD_LABEL_RAG_PROFILE", "hybrid_tfidf")
    get_default_regulation_store.cache_clear()
    yield
    get_default_regulation_store.cache_clear()
