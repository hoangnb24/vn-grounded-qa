"""Baseline evaluators used by milestone decision gates."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Dict, Iterable, List

from .answer import has_sufficient_support
from .eval import EvalResult
from .store import GroundedStore


@dataclass(frozen=True)
class BaselineResult:
    name: str
    total: int
    answer_correctness: float
    p95_latency_ms: float
    failures: List[Dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class BaselineComparison:
    baseline_name: str
    total: int
    sparse_correctness: float
    baseline_correctness: float
    sparse_to_baseline_ratio: float
    correctness_gap: float
    decision: str
    explanation: str
    sparse_failures: List[Dict[str, object]] = field(default_factory=list)
    baseline_failures: List[Dict[str, object]] = field(default_factory=list)


def run_thin_rag_baseline(store: GroundedStore, examples: Iterable[Dict[str, object]], top_k: int = 10) -> BaselineResult:
    """Run a dependency-free thin RAG comparison baseline.

    This baseline retrieves top-k units and answers by directly stuffing their
    text into an extractive response. It is intentionally simple: it provides a
    repeatable local comparison point before introducing a model provider.
    """

    rows = list(examples)
    correct = 0
    latencies: List[float] = []
    failures: List[Dict[str, object]] = []
    for row in rows:
        question = str(row["question"])
        expected_answer = [str(item).lower() for item in row.get("expected_answer_contains") or row.get("expected_text_contains") or []]
        expect_insufficient = bool(row.get("insufficient_evidence", False))
        start = time.perf_counter()
        hits = store.search_units(question, top_k=top_k)
        stuffed_answer = "\n".join(hit.raw_text for hit in hits[:5]).lower()
        supported = has_sufficient_support(question, [hit.__dict__ for hit in hits[:5]])
        latencies.append((time.perf_counter() - start) * 1000)
        if expect_insufficient:
            if not supported:
                correct += 1
            else:
                failures.append({"question": question, "type": "baseline_no_answer_false_positive"})
        elif expected_answer and all(fragment in stuffed_answer for fragment in expected_answer):
            correct += 1
        elif not expected_answer and hits:
            correct += 1
        else:
            failures.append({"question": question, "type": "baseline_answer_miss"})

    return BaselineResult(
        name="thin_rag_extractive",
        total=len(rows),
        answer_correctness=correct / len(rows) if rows else 0.0,
        p95_latency_ms=percentile(latencies, 95),
        failures=failures,
    )


def compare_sparse_to_baseline(sparse: EvalResult, baseline: BaselineResult) -> BaselineComparison:
    if baseline.answer_correctness == 0:
        ratio = 1.0 if sparse.answer_correctness > 0 else 0.0
    else:
        ratio = sparse.answer_correctness / baseline.answer_correctness
    gap = max(0.0, baseline.answer_correctness - sparse.answer_correctness)
    decision = "go" if ratio >= 0.85 else "revise"
    return BaselineComparison(
        baseline_name=baseline.name,
        total=baseline.total,
        sparse_correctness=sparse.answer_correctness,
        baseline_correctness=baseline.answer_correctness,
        sparse_to_baseline_ratio=ratio,
        correctness_gap=gap,
        decision=decision,
        explanation=baseline_gap_explanation(sparse, baseline, ratio, gap),
        sparse_failures=sparse.failures,
        baseline_failures=baseline.failures,
    )


def baseline_gap_explanation(sparse: EvalResult, baseline: BaselineResult, ratio: float, gap: float) -> str:
    if baseline.total == 0:
        return "Baseline comparison has no examples; provide a governed eval set before making the sparse-first decision."
    if ratio >= 0.85:
        return "Sparse bounded-tools performance is within the documented 85% baseline threshold."
    sparse_failure_types = sorted({str(failure.get("type")) for failure in sparse.failures})
    baseline_failure_types = sorted({str(failure.get("type")) for failure in baseline.failures})
    return (
        f"Sparse bounded-tools is below the 85% threshold by ratio {ratio:.3f} "
        f"with correctness gap {gap:.3f}. Sparse failure types: {', '.join(sparse_failure_types) or 'none'}. "
        f"Baseline failure types: {', '.join(baseline_failure_types) or 'none'}. "
        "Inspect shared retrieval misses before changing model prompting; tune corpus coverage, aliases, segmentation, or field weights from observed failures."
    )


def baseline_comparison_markdown(comparison: BaselineComparison) -> str:
    lines = [
        "# M5 Baseline Comparison",
        "",
        f"**Decision:** `{comparison.decision}`",
        f"**Baseline:** `{comparison.baseline_name}`",
        f"**Examples:** {comparison.total}",
        "",
        "## Metrics",
        "",
        f"- Sparse correctness: {comparison.sparse_correctness:.3f}",
        f"- Baseline correctness: {comparison.baseline_correctness:.3f}",
        f"- Sparse/baseline ratio: {comparison.sparse_to_baseline_ratio:.3f}",
        f"- Correctness gap: {comparison.correctness_gap:.3f}",
        "",
        "## Explanation",
        "",
        comparison.explanation,
        "",
        "## Sparse Failures",
        "",
    ]
    lines.extend(format_failure_lines(comparison.sparse_failures))
    lines.extend(["", "## Baseline Failures", ""])
    lines.extend(format_failure_lines(comparison.baseline_failures))
    lines.append("")
    return "\n".join(lines)


def format_failure_lines(failures: List[Dict[str, object]], limit: int = 20) -> List[str]:
    if not failures:
        return ["- None"]
    lines = []
    for failure in failures[:limit]:
        lines.append(f"- `{failure.get('type', 'unknown')}`: {failure.get('question', '')}")
    if len(failures) > limit:
        lines.append(f"- ... {len(failures) - limit} more")
    return lines


def write_baseline_comparison_report(comparison: BaselineComparison, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(comparison, default=lambda obj: obj.__dict__, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        path.write_text(baseline_comparison_markdown(comparison), encoding="utf-8")


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
