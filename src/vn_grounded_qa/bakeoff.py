"""Parser bakeoff and ingestion quality scorecards."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from .corpus import load_manifest
from .parsers import SUPPORTED_PARSERS, parse_file, units_from_ir


@dataclass(frozen=True)
class ParserDocScore:
    doc_id: str
    archetype: str
    parser_name: str
    parse_success: bool
    fatal_error: str = ""
    block_count: int = 0
    unit_count: int = 0
    heading_path_usable: bool = False
    provenance_complete: bool = False
    parser_warnings: List[str] = field(default_factory=list)
    expected_heading_paths: List[str] = field(default_factory=list)
    recovered_heading_paths: List[str] = field(default_factory=list)
    missing_heading_paths: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParserBakeoffReport:
    ok: bool
    parser_name: str
    document_count: int
    parse_success_rate: float
    heading_path_recovery_rate: float
    provenance_completeness_rate: float
    archetype_summary: Dict[str, Dict[str, float]]
    documents: List[ParserDocScore] = field(default_factory=list)
    gate_errors: List[str] = field(default_factory=list)


def run_fallback_bakeoff(manifest_path: Path) -> ParserBakeoffReport:
    return run_parser_bakeoff(manifest_path, "fallback")


def run_parser_bakeoff(manifest_path: Path, parser: str) -> ParserBakeoffReport:
    if parser not in SUPPORTED_PARSERS:
        raise ValueError(f"Unsupported parser: {parser}")
    manifest = load_manifest(manifest_path)
    docs = manifest.get("documents", [])
    if not isinstance(docs, list):
        raise ValueError("documents must be a list")

    scores: List[ParserDocScore] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        scores.append(score_document(manifest_path.parent, doc, parser))
    return summarize_scores(parser, scores)


def score_document(manifest_dir: Path, doc: Mapping[str, object], parser: str = "fallback") -> ParserDocScore:
    doc_id = str(doc.get("doc_id", ""))
    archetype = str(doc.get("archetype", "unknown"))
    source_uri = str(doc.get("source_uri", ""))
    path = Path(source_uri)
    if not path.is_absolute():
        path = manifest_dir / path

    try:
        ir = parse_file(path, parser=parser)
        units = units_from_ir(ir)
        heading_units = [unit for unit in units if unit.heading_path.strip()]
        recovered_heading_paths = sorted({unit.heading_path for unit in heading_units})
        expected_heading_paths = [str(item) for item in doc.get("expected_heading_paths") or []]
        missing_heading_paths = [heading for heading in expected_heading_paths if heading not in recovered_heading_paths]
        heading_path_usable = not missing_heading_paths if expected_heading_paths else bool(heading_units) or archetype in {"faq"}
        provenance_complete = all(
            [
                ir.document_meta.doc_id,
                ir.document_meta.source_uri,
                ir.document_meta.source_hash,
                ir.document_meta.format,
                ir.document_meta.parser_name,
                ir.document_meta.parser_version,
                ir.document_meta.ingest_time,
            ]
        )
        return ParserDocScore(
            doc_id=doc_id,
            archetype=archetype,
            parser_name=ir.document_meta.parser_name,
            parse_success=True,
            block_count=len(ir.blocks),
            unit_count=len(units),
            heading_path_usable=heading_path_usable,
            provenance_complete=provenance_complete,
            parser_warnings=[str(item) for item in ir.quality.get("parser_warnings") or []],
            expected_heading_paths=expected_heading_paths,
            recovered_heading_paths=recovered_heading_paths,
            missing_heading_paths=missing_heading_paths,
        )
    except Exception as exc:  # noqa: BLE001 - reports must capture parser failures.
        return ParserDocScore(
            doc_id=doc_id,
            archetype=archetype,
            parser_name=parser,
            parse_success=False,
            fatal_error=str(exc),
        )


def summarize_scores(parser_name: str, scores: List[ParserDocScore]) -> ParserBakeoffReport:
    document_count = len(scores)
    parse_success_rate = rate(score.parse_success for score in scores)
    heading_rate = rate(score.heading_path_usable for score in scores if score.parse_success)
    provenance_rate = rate(score.provenance_complete for score in scores if score.parse_success)
    archetype_summary: Dict[str, Dict[str, float]] = {}
    for archetype in sorted({score.archetype for score in scores}):
        subset = [score for score in scores if score.archetype == archetype]
        archetype_summary[archetype] = {
            "document_count": float(len(subset)),
            "parse_success_rate": rate(score.parse_success for score in subset),
            "heading_path_recovery_rate": rate(score.heading_path_usable for score in subset if score.parse_success),
            "provenance_completeness_rate": rate(score.provenance_complete for score in subset if score.parse_success),
        }

    gate_errors = []
    if parse_success_rate < 0.90:
        gate_errors.append(f"parse success below M1 gate: {parse_success_rate:.3f} < 0.900")
    if heading_rate < 0.85:
        gate_errors.append(f"heading path recovery below M1 gate: {heading_rate:.3f} < 0.850")
    if provenance_rate < 1.0:
        gate_errors.append(f"provenance completeness below M1 gate: {provenance_rate:.3f} < 1.000")
    return ParserBakeoffReport(
        ok=not gate_errors,
        parser_name=parser_name,
        document_count=document_count,
        parse_success_rate=parse_success_rate,
        heading_path_recovery_rate=heading_rate,
        provenance_completeness_rate=provenance_rate,
        archetype_summary=archetype_summary,
        documents=scores,
        gate_errors=gate_errors,
    )


def rate(values) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(1 for item in items if item) / len(items)


def write_report(report: ParserBakeoffReport, path: Optional[Path]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, default=lambda obj: obj.__dict__, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
