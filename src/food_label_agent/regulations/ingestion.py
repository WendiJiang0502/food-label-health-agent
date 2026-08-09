"""Structure-aware ingestion for official food-standard PDFs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .models import RegulationClause, StandardDocument

_SECTION_HEADING = re.compile(
    r"^(?:"
    r"\d+\.\d+(?:\.\d+){0,3}\s*\S"
    r"|(?:[1-9]|1\d)\s+[\u3400-\u9fff]"
    r"|[A-Z]\.(?:\d+(?:\.\d+)*)?(?:\s+|$)"
    r"|附录\s*[A-Z]"
    r"|前\s*言$"
    r"|引\s*言$"
    r")"
)
_DOMAIN_KEYWORDS = (
    "配料表",
    "复合配料",
    "食品添加剂",
    "致敏物质",
    "过敏原",
    "可能含有",
    "营养成分表",
    "营养声称",
    "能量",
    "蛋白质",
    "脂肪",
    "碳水化合物",
    "糖",
    "钠",
    "NRV",
)


@dataclass(frozen=True, slots=True)
class PageText:
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class IngestionResult:
    document_id: str
    document_hash: str
    page_count: int
    clauses: tuple[RegulationClause, ...]
    warnings: tuple[str, ...]


def extract_pdf_pages(pdf_path: Path) -> tuple[tuple[PageText, ...], str]:
    """Extract page text and the original-file hash from a PDF."""

    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError(
            "PDF ingestion requires pdfplumber. Install project dependencies first."
        ) from exc

    payload = pdf_path.read_bytes()
    with pdfplumber.open(pdf_path) as document:
        pages = tuple(
            PageText(
                page_number=index,
                text=page.extract_text(x_tolerance=2, y_tolerance=3) or "",
            )
            for index, page in enumerate(document.pages, start=1)
        )

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF ingestion requires pypdf for page-count verification. "
            "Install project dependencies first."
        ) from exc
    verified_page_count = len(PdfReader(pdf_path).pages)
    if verified_page_count != len(pages):
        raise ValueError(
            "PDF page-count verification failed: "
            f"pdfplumber={len(pages)}, pypdf={verified_page_count}"
        )
    return pages, sha256(payload).hexdigest()


def ingest_pdf(
    document: StandardDocument,
    pdf_path: Path,
) -> IngestionResult:
    pages, document_hash = extract_pdf_pages(pdf_path)
    return ingest_pages(document, pages, document_hash=document_hash)


def ingest_pages(
    document: StandardDocument,
    pages: tuple[PageText, ...],
    *,
    document_hash: str,
) -> IngestionResult:
    """Split extracted pages at standard headings, clauses, and appendices."""

    warnings = [
        f"page_{page.page_number}_has_little_extractable_text"
        for page in pages
        if len(_normalize_text(page.text)) < 20
    ]
    sections: list[tuple[str, str, int, int]] = []
    current_heading = "文档开始"
    current_lines: list[str] = []
    current_start = pages[0].page_number if pages else 1
    current_end = current_start

    def flush() -> None:
        nonlocal current_lines
        body = "\n".join(current_lines).strip()
        if body or current_heading != "文档开始":
            sections.append((current_heading, body, current_start, current_end))
        current_lines = []

    for page in pages:
        current_end = page.page_number
        for line in _normalized_lines(page.text):
            if _SECTION_HEADING.match(line):
                flush()
                current_heading = line
                current_start = page.page_number
                current_end = page.page_number
            else:
                current_lines.append(line)
    flush()

    clauses = tuple(
        _section_to_clause(
            document,
            heading=heading,
            body=body,
            page_start=page_start,
            page_end=page_end,
            document_hash=document_hash,
        )
        for heading, body, page_start, page_end in sections
        if heading != "文档开始"
    )
    if not clauses:
        warnings.append("no_structured_sections_extracted")
    return IngestionResult(
        document_id=document.document_id,
        document_hash=document_hash,
        page_count=len(pages),
        clauses=clauses,
        warnings=tuple(warnings),
    )


def _section_to_clause(
    document: StandardDocument,
    *,
    heading: str,
    body: str,
    page_start: int,
    page_end: int,
    document_hash: str,
) -> RegulationClause:
    identity = f"{document.document_id}\n{heading}\n{page_start}\n{body}".encode()
    chunk_hash = sha256(identity).hexdigest()
    evidence_id = f"reg.cn.{document.document_id.casefold()}.{chunk_hash[:16]}"
    evidence_text = "\n".join(value for value in (heading, body) if value)
    keywords = tuple(
        keyword for keyword in _DOMAIN_KEYWORDS if keyword in evidence_text
    )
    return RegulationClause(
        evidence_id=evidence_id,
        source_id=document.document_id,
        standard_number=document.standard_number,
        title=document.title,
        section=heading,
        evidence_text=evidence_text,
        jurisdiction=document.jurisdiction,
        published_on=document.published_on,
        effective_from=document.effective_from,
        effective_to=document.effective_to,
        source_url=document.pdf_url or document.official_page_url,
        authority_level=document.authority_level,
        source_type=document.source_type,
        topics=document.topics,
        keywords=keywords,
        document_hash=document_hash,
        page_start=page_start,
        page_end=page_end,
    )


def _normalized_lines(text: str) -> tuple[str, ...]:
    return tuple(
        normalized
        for line in text.replace("\r", "\n").split("\n")
        if (normalized := " ".join(line.split()))
    )


def _normalize_text(text: str) -> str:
    return " ".join(text.split())
