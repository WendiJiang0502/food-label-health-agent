"""Replaceable catalog adapter for reviewed product-label evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .models import ProductRecord

DATA_PATH = Path(__file__).with_name("data") / "curated_products.json"


class ProductCatalog(Protocol):
    def search(self, *, category: str, region: str) -> tuple[ProductRecord, ...]: ...


class JsonProductCatalog:
    """Read a small reviewed catalog; production adapters keep this boundary."""

    def __init__(self, path: str | Path = DATA_PATH) -> None:
        self.path = Path(path)

    def search(self, *, category: str, region: str) -> tuple[ProductRecord, ...]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        records = tuple(ProductRecord.model_validate(item) for item in payload)
        return tuple(
            item
            for item in records
            if item.category == category and item.region == region
        )
