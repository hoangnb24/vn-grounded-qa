"""Milestone gate reports."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .baselines import compare_sparse_to_baseline, run_thin_rag_baseline
from .bakeoff import run_parser_bakeoff
from .corpus import validate_architecture_manifest, validate_pack_manifest
from .eval import EvalResult, load_jsonl, run_eval, validate_eval_taxonomy
from .readiness import validate_project_license
from .risks import validate_risk_register
from .store import GroundedStore


@dataclass(frozen=True)
class GateCheck:
    name: str
    ok: bool
    evidence: str
    details: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class GateReport:
    milestone: str
    decision: str
    checks: List[GateCheck]


def run_m0_gate(manifest_path: Path, taxonomy_path: Path) -> GateReport:
    checks: List[GateCheck] = []
    corpus = validate_architecture_manifest(manifest_path, strict_m0=True)
    checks.append(
        GateCheck(
            "architecture corpus registered",
            corpus.ok and not corpus.warnings,
            str(manifest_path),
            [*corpus.errors, *corpus.warnings],
        )
    )
    taxonomy_errors = validate_eval_taxonomy(taxonomy_path)
    taxonomy_ok = not taxonomy_errors
    checks.append(GateCheck("evaluation taxonomy valid", taxonomy_ok, str(taxonomy_path), taxonomy_errors))
    decision = gate_decision(checks, stop=corpus.document_count == 0 or not taxonomy_ok)
    return GateReport("M0", decision, checks)


def run_m1_gate(manifest_path: Path, parser: str) -> GateReport:
    checks: List[GateCheck] = []
    corpus = validate_architecture_manifest(manifest_path, strict_m0=True)
    checks.append(
        GateCheck(
            "architecture corpus ready",
            corpus.ok and not corpus.warnings,
            str(manifest_path),
            [*corpus.errors, *corpus.warnings],
        )
    )
    bakeoff = run_parser_bakeoff(manifest_path, parser)
    checks.append(
        GateCheck(
            f"{parser} parser bakeoff",
            bakeoff.ok,
            str(manifest_path),
            bakeoff.gate_errors,
        )
    )
    checks.append(
        GateCheck(
            "parse success >= 90%",
            bakeoff.parse_success_rate >= 0.90,
            f"{bakeoff.parse_success_rate:.3f}",
        )
    )
    checks.append(
        GateCheck(
            "heading path recovery >= 85%",
            bakeoff.heading_path_recovery_rate >= 0.85,
            f"{bakeoff.heading_path_recovery_rate:.3f}",
        )
    )
    checks.append(
        GateCheck(
            "provenance completeness = 100%",
            bakeoff.provenance_completeness_rate >= 1.0,
            f"{bakeoff.provenance_completeness_rate:.3f}",
        )
    )
    decision = gate_decision(checks, stop=bakeoff.document_count == 0)
    return GateReport("M1", decision, checks)


def run_m2_gate(db_path: Path, eval_path: Path) -> GateReport:
    checks: List[GateCheck] = []
    examples = load_jsonl(eval_path)
    store = GroundedStore(db_path)
    store.init_schema()
    try:
        result_at_10 = run_eval(store, examples, k=10)
        result_at_20 = run_eval(store, examples, k=20)
    finally:
        store.close()

    single_hop = single_hop_recall(result_at_10)
    mixed = result_at_10.recall_by_category.get("mixed_vi_en")
    multihop = multi_hop_recall(result_at_20)
    failures = m2_failures_for_thresholds(result_at_10, result_at_20, examples)
    checks.append(GateCheck("single-hop Recall@10 >= 0.90", single_hop is not None and single_hop >= 0.90, "missing" if single_hop is None else f"{single_hop:.3f}"))
    checks.append(GateCheck("multi-hop component Recall@20 >= 0.80", multihop is not None and multihop >= 0.80, "missing" if multihop is None else f"{multihop:.3f}"))
    checks.append(GateCheck("mixed Vietnamese-English Recall@10 >= 0.80", mixed is not None and mixed >= 0.80, "missing" if mixed is None else f"{mixed:.3f}"))
    checks.append(GateCheck("search-only p95 <= 400ms", result_at_10.p95_search_latency_ms <= 400.0, f"{result_at_10.p95_search_latency_ms:.3f}ms"))
    checks.append(GateCheck("eval failures = 0", not failures, str(len(failures)), [failure["type"] + ": " + failure["question"] for failure in failures]))
    decision = gate_decision(checks, stop=result_at_10.total == 0 or result_at_20.total == 0)
    return GateReport("M2", decision, checks)


def run_m3_gate(db_path: Path, eval_path: Path) -> GateReport:
    store = GroundedStore(db_path)
    store.init_schema()
    try:
        result = run_eval(store, load_jsonl(eval_path), k=10)
    finally:
        store.close()

    checks = [
        GateCheck("avg tool calls <= 4", result.avg_tool_calls <= 4.0, f"{result.avg_tool_calls:.3f}"),
        GateCheck("p95 tool calls <= 6", result.p95_tool_calls <= 6.0, f"{result.p95_tool_calls:.3f}"),
        GateCheck("argument error rate < 2%", result.tool_argument_error_rate < 0.02, f"{result.tool_argument_error_rate:.3f}", [failure["type"] + ": " + failure["question"] for failure in result.failures if failure["type"] == "tool_argument_error"]),
        GateCheck("infinite loop rate = 0", result.tool_limit_error_rate == 0.0, f"{result.tool_limit_error_rate:.3f}", [failure["type"] + ": " + failure["question"] for failure in result.failures if failure["type"] == "tool_limit_error"]),
        GateCheck("tool limit errors = 0", result.tool_limit_error_count == 0, str(result.tool_limit_error_count), [failure["type"] + ": " + failure["question"] for failure in result.failures if failure["type"] == "tool_limit_error"]),
    ]
    decision = gate_decision(checks, stop=result.total == 0)
    return GateReport("M3", decision, checks)


def run_m4_gate(db_path: Path, eval_path: Path) -> GateReport:
    store = GroundedStore(db_path)
    store.init_schema()
    try:
        result = run_eval(store, load_jsonl(eval_path), k=10)
    finally:
        store.close()

    checks = [
        GateCheck("answer correctness >= 75%", result.answer_correctness >= 0.75, f"{result.answer_correctness:.3f}"),
        GateCheck("citation exactness >= 95%", result.citation_exactness >= 0.95, f"{result.citation_exactness:.3f}"),
        GateCheck("hallucinated citations = 0", result.hallucinated_citation_count == 0, str(result.hallucinated_citation_count)),
        GateCheck("no-answer precision >= 90%", result.no_answer_precision >= 0.90, f"{result.no_answer_precision:.3f}"),
        GateCheck("full-pipeline p95 <= 8s", result.p95_answer_latency_ms <= 8000.0, f"{result.p95_answer_latency_ms:.3f}ms"),
        GateCheck("eval failures = 0", not result.failures, str(len(result.failures)), [failure["type"] + ": " + failure["question"] for failure in result.failures]),
    ]
    decision = gate_decision(checks, stop=result.total == 0)
    return GateReport("M4", decision, checks)


def run_m5_gate(db_path: Path, eval_path: Path) -> GateReport:
    store = GroundedStore(db_path)
    store.init_schema()
    try:
        examples = load_jsonl(eval_path)
        sparse = run_eval(store, examples, k=10)
        baseline = run_thin_rag_baseline(store, examples, top_k=10)
    finally:
        store.close()

    comparison = compare_sparse_to_baseline(sparse, baseline)
    checks = [
        GateCheck("thin RAG baseline executed", baseline.total > 0, f"{baseline.name}:{baseline.total}"),
        GateCheck("sparse correctness measured", sparse.answer_total > 0, f"{sparse.answer_correctness:.3f}"),
        GateCheck("sparse >= 85% of thin RAG correctness", comparison.sparse_to_baseline_ratio >= 0.85, f"{comparison.sparse_to_baseline_ratio:.3f}"),
    ]
    if sparse.answer_correctness < baseline.answer_correctness:
        checks.append(GateCheck("gap explanation required", False, f"{comparison.correctness_gap:.3f}", [comparison.explanation]))
    decision = gate_decision(checks, stop=baseline.total == 0)
    return GateReport("M5", decision, checks)


def run_m6_gate(db_path: Path, base_eval_path: Path, scale_eval_path: Path) -> GateReport:
    store = GroundedStore(db_path)
    store.init_schema()
    try:
        base = run_eval(store, load_jsonl(base_eval_path), k=10)
        scale = run_eval(store, load_jsonl(scale_eval_path), k=10)
        provenance_errors = provenance_version_errors(store)
    finally:
        store.close()

    quality_drop = max(0.0, base.answer_correctness - scale.answer_correctness)
    checks = [
        GateCheck("quality drop <= 5 points on larger packs", quality_drop <= 0.05, f"{quality_drop:.3f}"),
        GateCheck("pipeline p95 <= 10s", scale.p95_answer_latency_ms <= 10000.0, f"{scale.p95_answer_latency_ms:.3f}ms"),
        GateCheck("provenance/version errors = 0", not provenance_errors, str(len(provenance_errors)), provenance_errors),
        GateCheck("scale eval failures = 0", not scale.failures, str(len(scale.failures)), [failure["type"] + ": " + failure["question"] for failure in scale.failures]),
    ]
    decision = gate_decision(checks, stop=base.total == 0 or scale.total == 0)
    return GateReport("M6", decision, checks)


def run_release_gate(
    manifest_path: Path,
    db_path: Path,
    eval_path: Path,
    scale_eval_path: Path,
    parser: str = "fallback",
    legal_pack_path: Path = Path("corpus/legal-regression/manifest.json"),
    shadow_pack_path: Path = Path("corpus/production-shadow/manifest.json"),
    pyproject_path: Path = Path("pyproject.toml"),
    readme_path: Path = Path("README.md"),
    strict_risk_owners: bool = False,
) -> GateReport:
    m0 = run_m0_gate(manifest_path, Path("eval/taxonomy.yaml"))
    m1 = run_m1_gate(manifest_path, parser)
    m2 = run_m2_gate(db_path, eval_path)
    m4 = run_m4_gate(db_path, eval_path)
    m6 = run_m6_gate(db_path, eval_path, scale_eval_path)
    legal_pack = validate_pack_manifest(legal_pack_path, "legal_regression")
    shadow_pack = validate_pack_manifest(shadow_pack_path, "production_shadow")
    checks = [
        GateCheck("corpus registered and provenance-complete", m0.decision == "go" and m1.decision == "go", f"M0={m0.decision}, M1={m1.decision}"),
        GateCheck("parsing benchmarked for all archetypes", m1.decision == "go", f"M1={m1.decision}"),
        GateCheck("retrieval thresholds met", m2.decision == "go", f"M2={m2.decision}"),
        GateCheck("citation hallucinations = 0", m4.checks[2].ok, m4.checks[2].evidence, m4.checks[2].details),
        GateCheck("no-answer behavior verified", m4.checks[3].ok, m4.checks[3].evidence, m4.checks[3].details),
        GateCheck("legal regression pack registered", legal_pack.ok and not legal_pack.warnings, f"{legal_pack_path}:{legal_pack.document_count}", [*legal_pack.errors, *legal_pack.warnings]),
        GateCheck("shadow corpus registered", shadow_pack.ok and not shadow_pack.warnings, f"{shadow_pack_path}:{shadow_pack.document_count}", [*shadow_pack.errors, *shadow_pack.warnings]),
        GateCheck("shadow or scale corpus tested", m6.decision == "go", f"M6={m6.decision}"),
        risk_check(validate_risk_register(Path("docs/RISK_REGISTER.md"), strict_owners=strict_risk_owners), strict_risk_owners=strict_risk_owners),
        license_check(validate_project_license(pyproject_path, readme_path)),
    ]
    decision = gate_decision(checks, stop=any(report.decision == "stop" for report in [m0, m1, m2, m4, m6]))
    return GateReport("Release", decision, checks)


def gate_decision(checks: List[GateCheck], stop: bool = False) -> str:
    if stop:
        return "stop"
    return "go" if all(check.ok for check in checks) else "revise"


def provenance_version_errors(store: GroundedStore) -> List[str]:
    errors: List[str] = []
    rows = store.conn.execute(
        """
        SELECT doc_id, doc_family_id, source_uri, source_hash, parser_name, parser_version,
               effective_from, effective_to
        FROM documents
        """
    ).fetchall()
    for row in rows:
        for field in ["doc_id", "doc_family_id", "source_uri", "source_hash", "parser_name", "parser_version"]:
            if not str(row[field] or "").strip():
                errors.append(f"{row['doc_id']}: missing {field}")
        if row["effective_from"] and row["effective_to"] and row["effective_from"] > row["effective_to"]:
            errors.append(f"{row['doc_id']}: effective_from after effective_to")
    errors.extend(store.version_conflicts())
    return errors


def risk_check(result, strict_risk_owners: bool = False) -> GateCheck:
    return GateCheck(
        "open risks documented with owners/mitigations" if not strict_risk_owners else "open risks documented with deployment owners/mitigations",
        result.ok,
        f"docs/RISK_REGISTER.md:{result.risk_count}",
        result.errors,
    )


def license_check(result) -> GateCheck:
    return GateCheck(result.name, result.ok, result.evidence, result.details)


def m2_failures_for_thresholds(result_at_10: EvalResult, result_at_20: EvalResult, examples: List[dict]) -> List[dict]:
    category_by_question = {str(row.get("question")): str(row.get("category") or "") for row in examples}
    retrieval_failure_types = {
        "alias_term_miss",
        "retrieval_miss",
        "version_expected_doc_missing",
        "version_resolution_miss",
    }
    failures: List[dict] = []
    seen = set()
    for result, categories in [
        (result_at_10, {"single_unit_factual", "mixed_vi_en", "table_list_structure"}),
        (result_at_20, {"multihop_single_doc", "multidoc_synthesis"}),
    ]:
        for failure in result.failures:
            question = str(failure.get("question") or "")
            category = category_by_question.get(question, "")
            failure_type = str(failure.get("type") or "")
            if failure_type not in retrieval_failure_types:
                continue
            if category not in categories:
                continue
            key = (question, failure_type)
            if key in seen:
                continue
            seen.add(key)
            failures.append(failure)
    return failures


def single_hop_recall(result: EvalResult):
    values = [
        value
        for category, value in result.recall_by_category.items()
        if category
        in {
            "single_unit_factual",
            "technical_markdown",
            "legal",
            "policy_sop",
            "table_list_structure",
        }
    ]
    if not values:
        return None
    return sum(values) / len(values)


def multi_hop_recall(result: EvalResult):
    values = [
        value
        for category, value in result.recall_by_category.items()
        if category in {"multihop_single_doc", "multidoc_synthesis"}
    ]
    if not values:
        return None
    return sum(values) / len(values)


def write_gate_report(report: GateReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, default=lambda obj: obj.__dict__, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
