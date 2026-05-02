"""Small evaluation harness for retrieval and no-answer behavior."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional

from .answer import answer_question
from .contracts import load_answer_contract_schema, validate_answer_contract
from .normalize import identifier_variants
from .store import GroundedStore
from .tools import ToolSession

REQUIRED_EVAL_COUNTS = {
    "single_unit_factual": 20,
    "mixed_vi_en": 10,
    "table_list_structure": 10,
    "multihop_single_doc": 10,
    "multidoc_synthesis": 10,
    "version_status_exception": 10,
    "no_answer": 10,
}

DEFAULT_TOOL_CALL_COST = 0.0001
DEFAULT_TAXONOMY_PATH = Path("eval/taxonomy.yaml")
HUMAN_REVIEWED_EVAL_SOURCES = {"human", "rewritten", "human_authored", "substantively_rewritten"}


@dataclass(frozen=True)
class EvalSetValidationResult:
    ok: bool
    total: int
    category_counts: Dict[str, int]
    auto_generated_count: int
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvalResult:
    total: int
    retrieval_total: int
    recall_at_k: float
    recall_by_category: Dict[str, float]
    no_answer_precision: float
    no_answer_recall: float
    p50_search_latency_ms: float
    p95_search_latency_ms: float
    p50_answer_latency_ms: float
    p95_answer_latency_ms: float
    avg_tool_calls: float
    p95_tool_calls: float
    avg_estimated_cost: float
    p95_estimated_cost: float
    answer_total: int
    answer_correctness: float
    citation_exactness: float
    hallucinated_citation_count: int
    tool_argument_error_count: int
    tool_argument_error_rate: float
    tool_limit_error_count: int
    tool_limit_error_rate: float
    failures: List[Dict[str, object]]
    warnings: List[str] = field(default_factory=list)


def load_jsonl(path: Path) -> List[Dict[str, object]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


@dataclass(frozen=True)
class EvalTaxonomy:
    category_counts: Dict[str, int]
    total_required_questions: int
    max_auto_generated_fraction: float


def validate_eval_set(path: Path, strict: bool = True, taxonomy_path: Optional[Path] = DEFAULT_TAXONOMY_PATH) -> EvalSetValidationResult:
    taxonomy = load_eval_taxonomy(taxonomy_path)
    required_counts = taxonomy.category_counts
    rows = load_jsonl(path)
    errors: List[str] = []
    warnings: List[str] = []
    counts: Dict[str, int] = {}
    auto_generated = 0
    for index, row in enumerate(rows):
        location = f"line {index + 1}"
        question = str(row.get("question", "")).strip()
        category = str(row.get("category", "")).strip()
        if not question:
            errors.append(f"{location}: missing question")
        if not category:
            errors.append(f"{location}: missing category")
        elif category not in required_counts:
            errors.append(f"{location}: unknown category {category}")
        if category == "no_answer":
            if row.get("insufficient_evidence") is not True:
                errors.append(f"{location}: no_answer rows must set insufficient_evidence=true")
            if row.get("expected_answer_contains") or row.get("expected_answer_points"):
                errors.append(f"{location}: no_answer rows must not provide expected answer content")
        if category == "version_status_exception":
            if not str(row.get("as_of") or "").strip() or not str(row.get("expected_doc_id") or "").strip():
                errors.append(f"{location}: version_status_exception rows must include as_of and expected_doc_id")
        counts[category] = counts.get(category, 0) + 1
        is_auto_generated = bool(row.get("auto_generated", False))
        if is_auto_generated:
            auto_generated += 1
        elif strict and str(row.get("source") or "").strip() not in HUMAN_REVIEWED_EVAL_SOURCES:
            errors.append(f"{location}: non-auto-generated eval rows must set source to human or rewritten")
        has_gold = bool(
            expected_unit_ids(row)
            or row.get("expected_text_contains")
            or row.get("expected_row_or_item")
            or row.get("expected_answer_contains")
            or row.get("expected_answer_points")
            or row.get("aliases_or_terms")
            or row.get("disallowed_answer_points")
            or row.get("expected_doc_id")
            or row.get("expected_doc_ids")
            or row.get("insufficient_evidence")
        )
        if not has_gold:
            errors.append(f"{location}: missing expected evidence or insufficient_evidence flag")
    if strict:
        if len(rows) != taxonomy.total_required_questions:
            errors.append(f"strict MVP eval must contain {taxonomy.total_required_questions} questions; found {len(rows)}")
        for category, required in required_counts.items():
            actual = counts.get(category, 0)
            if actual != required:
                errors.append(f"category {category} must contain {required} questions; found {actual}")
        if rows and auto_generated / len(rows) > taxonomy.max_auto_generated_fraction:
            errors.append(f"auto-generated fraction must be <= {taxonomy.max_auto_generated_fraction:.3f}; found {auto_generated / len(rows):.3f}")
    else:
        missing = sorted(set(required_counts) - set(counts))
        if missing:
            warnings.append(f"eval set missing categories: {', '.join(missing)}")
    return EvalSetValidationResult(not errors, len(rows), dict(sorted(counts.items())), auto_generated, errors, warnings)


def load_eval_taxonomy(path: Optional[Path] = DEFAULT_TAXONOMY_PATH) -> EvalTaxonomy:
    if path is None or not path.exists():
        return EvalTaxonomy(REQUIRED_EVAL_COUNTS, 80, 0.4)
    text = path.read_text(encoding="utf-8")
    return parse_eval_taxonomy(text)


def validate_eval_taxonomy(path: Path) -> List[str]:
    if not path.exists():
        return ["taxonomy file missing"]
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return ["taxonomy file missing or empty"]
    taxonomy = parse_eval_taxonomy(text)
    errors: List[str] = []
    if not taxonomy.category_counts:
        errors.append("taxonomy must define at least one category with required_count")
    for category, count in taxonomy.category_counts.items():
        if count <= 0:
            errors.append(f"category {category} required_count must be > 0")
    expected_total = sum(taxonomy.category_counts.values())
    if taxonomy.total_required_questions != expected_total:
        errors.append(f"total_required_questions must equal category count sum {expected_total}; found {taxonomy.total_required_questions}")
    if taxonomy.max_auto_generated_fraction < 0 or taxonomy.max_auto_generated_fraction > 1:
        errors.append("max_auto_generated_fraction must be between 0 and 1")
    return errors


def parse_eval_taxonomy(text: str) -> EvalTaxonomy:
    category_counts: Dict[str, int] = {}
    current_id = ""
    for line in text.splitlines():
        id_match = re.match(r"\s*-\s+id:\s*([A-Za-z0-9_-]+)\s*$", line)
        if id_match:
            current_id = id_match.group(1)
            continue
        count_match = re.match(r"\s*required_count:\s*(\d+)\s*$", line)
        if count_match and current_id:
            category_counts[current_id] = int(count_match.group(1))
            current_id = ""
    total_match = re.search(r"^\s*total_required_questions:\s*(\d+)\s*$", text, re.MULTILINE)
    max_auto_match = re.search(r"^\s*max_auto_generated_fraction:\s*([0-9.]+)\s*$", text, re.MULTILINE)
    return EvalTaxonomy(
        category_counts=category_counts,
        total_required_questions=int(total_match.group(1)) if total_match else sum(category_counts.values()),
        max_auto_generated_fraction=float(max_auto_match.group(1)) if max_auto_match else 0.4,
    )


def write_synthetic_mvp_eval(path: Path) -> None:
    rows: List[Mapping[str, object]] = []
    rows.extend(synthetic_eval_rows("single_unit_factual", 20, "Ai phê duyệt cuối cùng trong SOP {i}?", ["bộ phận nhân sự phê duyệt cuối cùng"], ["bộ phận nhân sự phê duyệt cuối cùng"]))
    rows.extend(synthetic_eval_rows("mixed_vi_en", 10, "HRM dùng để làm gì trong quy trình {i}?", ["hrm dùng để tạo yêu cầu", "lưu bằng chứng"], ["hrm dùng để tạo yêu cầu"]))
    rows.extend(synthetic_eval_rows("table_list_structure", 10, "Ai phê duyệt mua công cụ {i} với hạn mức 5000000 VND?", ["mua công cụ {i}", "quản lý trực tiếp"], ["quản lý trực tiếp"]))
    rows.extend(synthetic_eval_rows("multihop_single_doc", 10, "Trong SOP {i}, ai kiểm tra thông tin và ai phê duyệt cuối cùng?", ["quản lý trực tiếp kiểm tra", "bộ phận nhân sự phê duyệt"], ["quản lý trực tiếp kiểm tra", "bộ phận nhân sự phê duyệt"]))
    rows.extend(synthetic_eval_rows("multidoc_synthesis", 10, "HRM và endpoint /search_units liên quan gì đến bằng chứng?", ["hrm dùng để tạo yêu cầu", "/search_units"], ["hrm", "/search_units"]))
    rows.extend(synthetic_version_status_rows())
    for index in range(1, 11):
        rows.append(
            {
                "question": f"Quy định mua cổ phiếu cá nhân số {index} là gì?",
                "category": "no_answer",
                "insufficient_evidence": True,
                "auto_generated": False,
                "source": "rewritten",
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def synthetic_eval_rows(category: str, count: int, question_template: str, expected_text: List[str], expected_answer: List[str]) -> List[Mapping[str, object]]:
    rows: List[Mapping[str, object]] = []
    for index in range(1, count + 1):
        rows.append(
            {
                "question": question_template.format(i=((index - 1) % 5) + 1),
                "category": category,
                "expected_text_contains": [fragment.format(i=((index - 1) % 5) + 1) for fragment in expected_text],
                "expected_answer_contains": [fragment.format(i=((index - 1) % 5) + 1) for fragment in expected_answer],
                "auto_generated": False,
                "source": "rewritten",
            }
        )
    return rows


def synthetic_version_status_rows() -> List[Mapping[str, object]]:
    rows: List[Mapping[str, object]] = []
    for index in range(1, 11):
        doc_index = ((index - 1) % 5) + 1
        rows.append(
            {
                "question": f"Ngoại lệ khẩn cấp trong quy định {doc_index} phải xác nhận trong bao lâu?",
                "category": "version_status_exception",
                "expected_text_contains": ["trong vòng 24 giờ"],
                "expected_answer_contains": ["trong vòng 24 giờ"],
                "as_of": "2026-01-01",
                "expected_doc_id": f"synthetic_legal_{doc_index:02d}",
                "auto_generated": False,
                "source": "rewritten",
            }
        )
    return rows


def run_eval(store: GroundedStore, examples: Iterable[Dict[str, object]], k: int = 10) -> EvalResult:
    rows = list(examples)
    retrieval_total = 0
    retrieval_hits = 0
    retrieval_by_category: Dict[str, int] = {}
    retrieval_hits_by_category: Dict[str, int] = {}
    no_answer_total = 0
    no_answer_correct = 0
    supported_answer_total = 0
    supported_answer_incorrect = 0
    search_latencies_ms: List[float] = []
    answer_latencies_ms: List[float] = []
    tool_counts: List[int] = []
    estimated_costs: List[float] = []
    answer_total = 0
    answer_correct = 0
    citation_total = 0
    citation_exact = 0
    hallucinated_citation_count = 0
    tool_argument_error_count = 0
    tool_limit_error_count = 0
    tool_invocation_count = 0
    failures: List[Dict[str, object]] = []
    warnings: List[str] = []
    answer_schema = load_answer_contract_schema()
    for row in rows:
        question = str(row["question"])
        category = str(row.get("category") or "uncategorized")
        expected_units = set(expected_unit_ids(row))
        expected_text = expected_text_fragments(row)
        expected_answer = expected_answer_fragments(row)
        expected_citations = set(str(item) for item in row.get("expected_citation_unit_ids") or [])
        expected_docs = set(str(item) for item in row.get("expected_doc_ids") or [])
        aliases_or_terms = [str(item) for item in row.get("aliases_or_terms") or []]
        disallowed_answer = [str(item).lower() for item in row.get("disallowed_answer_points") or []]
        expected_doc_id = str(row.get("expected_doc_id") or "").strip()
        as_of = str(row.get("as_of") or "").strip()
        retrieval_expected_docs = set(expected_docs)
        if expected_doc_id and (expected_units or expected_text or not as_of):
            retrieval_expected_docs.add(expected_doc_id)
        expect_insufficient = bool(row.get("insufficient_evidence", False))
        if aliases_or_terms:
            resolved_terms = set(store.resolve_terms(question))
            missing_terms = [term for term in aliases_or_terms if term not in resolved_terms]
            if missing_terms:
                failures.append({"question": question, "type": "alias_term_miss", "missing_terms": missing_terms, "resolved_terms": sorted(resolved_terms)})
        if expected_doc_id and as_of:
            version_row = store.get_document(expected_doc_id)
            if version_row is None:
                failures.append({"question": question, "type": "version_expected_doc_missing", "expected_doc_id": expected_doc_id})
            else:
                resolved = store.get_applicable_version(str(version_row["doc_family_id"] or expected_doc_id), as_of=as_of)
                if resolved is None or str(resolved["doc_id"]) != expected_doc_id:
                    failures.append(
                        {
                            "question": question,
                            "type": "version_resolution_miss",
                            "as_of": as_of,
                            "expected_doc_id": expected_doc_id,
                            "resolved_doc_id": None if resolved is None else str(resolved["doc_id"]),
                        }
                    )
        if expected_units or expected_text or retrieval_expected_docs:
            retrieval_total += 1
            retrieval_by_category[category] = retrieval_by_category.get(category, 0) + 1
            start = time.perf_counter()
            hits = store.search_units(question, top_k=k)
            hit_ids = {hit.unit_id for hit in hits}
            hit_doc_ids = {hit.doc_id for hit in hits}
            hit_text = "\n".join(" ".join([*identifier_variants(hit.doc_id), hit.title, hit.heading_path, hit.raw_text]).lower() for hit in hits)
            search_latencies_ms.append((time.perf_counter() - start) * 1000)
            unit_match = bool(expected_units and hit_ids.intersection(expected_units))
            text_match = bool(expected_text and all(fragment in hit_text for fragment in expected_text))
            doc_match = bool(retrieval_expected_docs and retrieval_expected_docs.issubset(hit_doc_ids))
            if unit_match or text_match or doc_match:
                retrieval_hits += 1
                retrieval_hits_by_category[category] = retrieval_hits_by_category.get(category, 0) + 1
            else:
                failures.append(
                    {
                        "question": question,
                        "type": "retrieval_miss",
                        "expected_unit_ids": sorted(expected_units),
                        "expected_text_contains": expected_text,
                        "expected_doc_ids": sorted(retrieval_expected_docs),
                        "hit_unit_ids": sorted(hit_ids),
                        "hit_doc_ids": sorted(hit_doc_ids),
                    }
                )
        if expect_insufficient:
            no_answer_total += 1
            start_answer = time.perf_counter()
            try:
                answer = answer_question(ToolSession(store), question, top_k=k)
            except (TypeError, ValueError) as exc:
                tool_argument_error_count += 1
                tool_invocation_count += 1
                answer_latencies_ms.append((time.perf_counter() - start_answer) * 1000)
                failures.append({"question": question, "type": "tool_argument_error", "error": str(exc)})
                continue
            except RuntimeError as exc:
                tool_limit_error_count += 1
                tool_invocation_count += 1
                answer_latencies_ms.append((time.perf_counter() - start_answer) * 1000)
                failures.append({"question": question, "type": "tool_limit_error", "error": str(exc)})
                continue
            answer_latencies_ms.append((time.perf_counter() - start_answer) * 1000)
            answer_total += 1
            tool_invocation_count += 1
            tool_counts.append(len(answer.tool_calls))
            estimated_costs.append(estimate_query_cost(answer.tool_calls))
            contract_errors = validate_answer_contract(asdict(answer), answer_schema)
            if contract_errors:
                failures.append({"question": question, "type": "answer_contract_violation", "errors": contract_errors})
            if answer.insufficient_evidence:
                no_answer_correct += 1
                answer_correct += 1
            elif disallowed_answer and any(fragment in answer.answer.lower() for fragment in disallowed_answer):
                failures.append({"question": question, "type": "disallowed_answer_point_used", "disallowed_answer_points": disallowed_answer})
            else:
                failures.append({"question": question, "type": "no_answer_false_positive", "used_unit_ids": answer.used_unit_ids})
        elif expected_units or expected_text:
            supported_answer_total += 1
            start_answer = time.perf_counter()
            try:
                answer = answer_question(ToolSession(store), question, top_k=k)
            except (TypeError, ValueError) as exc:
                tool_argument_error_count += 1
                tool_invocation_count += 1
                answer_latencies_ms.append((time.perf_counter() - start_answer) * 1000)
                failures.append({"question": question, "type": "tool_argument_error", "error": str(exc)})
                continue
            except RuntimeError as exc:
                tool_limit_error_count += 1
                tool_invocation_count += 1
                answer_latencies_ms.append((time.perf_counter() - start_answer) * 1000)
                failures.append({"question": question, "type": "tool_limit_error", "error": str(exc)})
                continue
            answer_latencies_ms.append((time.perf_counter() - start_answer) * 1000)
            answer_total += 1
            tool_invocation_count += 1
            tool_counts.append(len(answer.tool_calls))
            estimated_costs.append(estimate_query_cost(answer.tool_calls))
            contract_errors = validate_answer_contract(asdict(answer), answer_schema)
            if contract_errors:
                failures.append({"question": question, "type": "answer_contract_violation", "errors": contract_errors})
            if answer.insufficient_evidence:
                supported_answer_incorrect += 1
                failures.append({"question": question, "type": "supported_answer_marked_insufficient", "expected_unit_ids": sorted(expected_units)})
            elif expected_answer and not all(fragment in answer.answer.lower() for fragment in expected_answer):
                failures.append({"question": question, "type": "answer_text_miss", "expected_answer_contains": expected_answer})
            elif expected_docs and not expected_docs.issubset(set(answer.used_doc_ids)):
                failures.append(
                    {
                        "question": question,
                        "type": "used_doc_ids_miss",
                        "expected_doc_ids": sorted(expected_docs),
                        "used_doc_ids": answer.used_doc_ids,
                    }
                )
            else:
                answer_correct += 1
            answer_citation_ids = {citation.unit_id for citation in answer.citations}
            if expected_citations:
                citation_total += len(expected_citations)
                citation_exact += len(expected_citations.intersection(answer_citation_ids))
                hallucinated_citation_count += len(answer_citation_ids - expected_citations)
                if not expected_citations.intersection(answer_citation_ids):
                    failures.append({"question": question, "type": "citation_gold_miss", "expected_citation_unit_ids": sorted(expected_citations)})
            else:
                for citation in answer.citations:
                    citation_total += 1
                    if citation.unit_id in answer.used_unit_ids:
                        citation_exact += 1
                    else:
                        hallucinated_citation_count += 1

    if not rows:
        warnings.append("eval set is empty")
    if retrieval_total == 0:
        warnings.append("no retrieval examples with expected_unit_ids")
    if no_answer_total == 0:
        warnings.append("no no-answer examples")

    recall = retrieval_hits / retrieval_total if retrieval_total else 0.0
    recall_by_category = {
        category: retrieval_hits_by_category.get(category, 0) / total
        for category, total in sorted(retrieval_by_category.items())
    }
    no_answer_precision = no_answer_correct / no_answer_total if no_answer_total else 0.0
    no_answer_recall = no_answer_correct / (no_answer_total + supported_answer_incorrect) if (no_answer_total + supported_answer_incorrect) else 0.0
    return EvalResult(
        total=len(rows),
        retrieval_total=retrieval_total,
        recall_at_k=recall,
        recall_by_category=recall_by_category,
        no_answer_precision=no_answer_precision,
        no_answer_recall=no_answer_recall,
        p50_search_latency_ms=percentile(search_latencies_ms, 50),
        p95_search_latency_ms=percentile(search_latencies_ms, 95),
        p50_answer_latency_ms=percentile(answer_latencies_ms, 50),
        p95_answer_latency_ms=percentile(answer_latencies_ms, 95),
        avg_tool_calls=sum(tool_counts) / len(tool_counts) if tool_counts else 0.0,
        p95_tool_calls=percentile([float(count) for count in tool_counts], 95),
        avg_estimated_cost=sum(estimated_costs) / len(estimated_costs) if estimated_costs else 0.0,
        p95_estimated_cost=percentile(estimated_costs, 95),
        answer_total=answer_total,
        answer_correctness=answer_correct / answer_total if answer_total else 0.0,
        citation_exactness=citation_exact / citation_total if citation_total else 1.0,
        hallucinated_citation_count=hallucinated_citation_count,
        tool_argument_error_count=tool_argument_error_count,
        tool_argument_error_rate=tool_argument_error_count / tool_invocation_count if tool_invocation_count else 0.0,
        tool_limit_error_count=tool_limit_error_count,
        tool_limit_error_rate=tool_limit_error_count / tool_invocation_count if tool_invocation_count else 0.0,
        failures=failures,
        warnings=warnings,
    )


def percentile(values: List[float], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def expected_unit_ids(row: Mapping[str, object]) -> List[str]:
    ids: List[str] = []
    for field in ["expected_unit_ids", "expected_component_unit_ids", "expected_citation_unit_ids"]:
        values = row.get(field) or []
        if isinstance(values, list):
            ids.extend(str(item) for item in values)
    return sorted(set(ids))


def expected_text_fragments(row: Mapping[str, object]) -> List[str]:
    fragments: List[str] = []
    for field in ["expected_text_contains", "expected_row_or_item"]:
        values = row.get(field) or []
        if isinstance(values, list):
            fragments.extend(str(item).lower() for item in values)
        elif values:
            fragments.append(str(values).lower())
    return fragments


def expected_answer_fragments(row: Mapping[str, object]) -> List[str]:
    fragments: List[str] = []
    for field in ["expected_answer_contains", "expected_answer_points"]:
        values = row.get(field) or []
        if isinstance(values, list):
            fragments.extend(str(item).lower() for item in values)
    return fragments


def estimate_query_cost(tool_calls: List[Mapping[str, object]], per_tool_call_cost: float = DEFAULT_TOOL_CALL_COST) -> float:
    """Return a deterministic MVP cost estimate for one answered query.

    The local sparse-first MVP has no model-provider spend. We still expose the
    documented metric as a configurable tool-call estimate so benchmark reports
    can track relative cost before a provider-specific pricing model exists.
    """

    return round(len(tool_calls) * per_tool_call_cost, 6)
