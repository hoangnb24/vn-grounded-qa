"""Shared data contracts for ingestion, retrieval, and answering."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class DocumentMeta:
    doc_id: str
    source_uri: str
    source_hash: str
    format: str
    parser_name: str
    parser_version: str
    doc_family_id: str = ""
    ingest_time: str = field(default_factory=utc_now_iso)
    title: str = ""
    doc_type: str = "unknown"
    language: str = "vi"
    version_label: str = ""
    status: str = "active"
    effective_from: str = ""
    effective_to: str = ""


@dataclass(frozen=True)
class ParsedBlock:
    block_id: str
    block_type: str
    text: str
    order: int
    page_no: int = 1
    parent_block_id: Optional[str] = None
    bbox: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedIR:
    document_meta: DocumentMeta
    pages: List[Dict[str, Any]]
    blocks: List[ParsedBlock]
    quality: Dict[str, Any]


@dataclass(frozen=True)
class ContentUnit:
    unit_id: str
    doc_id: str
    parent_unit_id: Optional[str]
    unit_type: str
    heading_path: str
    ordinal_path: str
    sequence_no: int
    page_start: int
    page_end: int
    raw_text: str
    normalized_text: str
    vi_segmented_text: str
    ascii_folded_text: str
    glossary_terms: str = ""
    table_text: str = ""
    unit_hash: str = ""


@dataclass(frozen=True)
class SearchHit:
    unit_id: str
    doc_id: str
    title: str
    heading_path: str
    page_start: int
    page_end: int
    raw_text: str
    score: float
    doc_family_id: str = ""
    version_label: str = ""
    effective_from: str = ""
    effective_to: str = ""


@dataclass(frozen=True)
class Citation:
    unit_id: str
    doc_id: str
    title: str
    heading_path: str
    page_start: int
    page_end: int


@dataclass(frozen=True)
class GroundedAnswer:
    answer: str
    citations: List[Citation]
    confidence_label: str
    insufficient_evidence: bool
    used_doc_ids: List[str]
    used_unit_ids: List[str]
    tool_calls: List[Dict[str, Any]]
