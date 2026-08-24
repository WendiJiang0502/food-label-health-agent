"""Reproducible component-version snapshot for every evaluation report."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from food_label_agent import __version__
from food_label_agent.graph.planner import PlannerSettings
from food_label_agent.ingredients.additives import ADDITIVE_DICTIONARY_VERSION
from food_label_agent.ingredients.allergens import RULESET_METADATA
from food_label_agent.ingredients.normalization import INGREDIENT_NORMALIZATION_VERSION
from food_label_agent.mcp.contracts import MCP_TOOLS
from food_label_agent.nutrition.rules import RULESET_METADATA as NUTRITION_RULESET
from food_label_agent.ocr.config import OCRSettings
from food_label_agent.persistence.sqlite import AGENT_STATE_SCHEMA_VERSION
from food_label_agent.regulations.semantic import RAG2Settings
from food_label_agent.regulations.serialization import SCHEMA_VERSION
from food_label_agent.regulations.service import DATA_DIR, get_default_regulation_store


@dataclass(frozen=True, slots=True)
class VersionSnapshot:
    generated_at: str
    git_commit: str
    git_dirty: bool
    package_version: str
    agent_state_schema: int
    allergen_ruleset: str
    nutrition_ruleset: str
    ingredient_normalization: str
    additive_dictionary: str
    regulation_schema: str
    regulation_retrieval: str
    regulation_clause_count: int
    regulation_content_hash: str
    ocr_provider: str
    ocr_model: str
    ocr_sdk_version: str | None
    planner_provider: str
    planner_model: str | None
    product_catalog: str
    mcp_tools: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["mcp_tools"] = list(self.mcp_tools)
        return result


def build_version_snapshot() -> VersionSnapshot:
    settings = OCRSettings.from_environment()
    planner = PlannerSettings.from_environment()
    return VersionSnapshot(
        generated_at=datetime.now(UTC).isoformat(),
        git_commit=_git("rev-parse", "HEAD") or "unknown",
        git_dirty=bool(_git("status", "--porcelain")),
        package_version=__version__,
        agent_state_schema=AGENT_STATE_SCHEMA_VERSION,
        allergen_ruleset=str(RULESET_METADATA["id"]),
        nutrition_ruleset=str(NUTRITION_RULESET["id"]),
        ingredient_normalization=INGREDIENT_NORMALIZATION_VERSION,
        additive_dictionary=ADDITIVE_DICTIONARY_VERSION,
        regulation_schema=SCHEMA_VERSION,
        regulation_retrieval=RAG2Settings.from_environment().profile,
        regulation_clause_count=len(get_default_regulation_store().clauses),
        regulation_content_hash=_directory_hash(DATA_DIR),
        ocr_provider=settings.provider,
        ocr_model=_ocr_model(settings),
        ocr_sdk_version=_ocr_sdk_version(settings.provider),
        planner_provider=planner.provider,
        planner_model=planner.model if planner.provider != "deterministic" else None,
        product_catalog=os.getenv(
            "FOOD_LABEL_PRODUCT_CATALOG", "official_cn_expanded"
        ),
        mcp_tools=tuple(sorted(item.name for item in MCP_TOOLS if item.implemented)),
    )


def _git(*arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _directory_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(path.glob("*.json")):
        digest.update(file_path.name.encode())
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        digest.update(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        )
    return "sha256:" + digest.hexdigest()


def _ocr_model(settings: OCRSettings) -> str:
    if settings.provider == "tencent":
        table = (
            "RecognizeTableAccurateOCR"
            if settings.tencent_table_enabled
            else "coordinate-table"
        )
        return f"GeneralAccurateOCR+{table}"
    if settings.provider == "paddle":
        return settings.version
    return "synthetic-demo"


def _ocr_sdk_version(provider: str) -> str | None:
    package = {
        "tencent": "tencentcloud-sdk-python-ocr",
        "paddle": "paddleocr",
    }.get(provider)
    if package is None:
        return None
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None
