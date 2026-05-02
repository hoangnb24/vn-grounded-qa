"""Milestone decision report generation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class FailureReview:
    check: str
    layer: str
    evidence: str
    details: List[str] = field(default_factory=list)
    next_action: str = ""


@dataclass(frozen=True)
class DecisionReport:
    milestone: str
    decision: str
    source: str
    passed_checks: List[str]
    failed_reviews: List[FailureReview]
    stop_reason: str = ""


def build_decision_report(gate_report_path: Path, stop_reason: str = "") -> DecisionReport:
    data = json.loads(gate_report_path.read_text(encoding="utf-8"))
    milestone = str(data.get("milestone") or "Unknown")
    gate_decision = str(data.get("decision") or "revise")
    decision = "stop" if stop_reason else gate_decision
    checks = data.get("checks") or []
    passed: List[str] = []
    failed: List[FailureReview] = []
    for check in checks:
        name = str(check.get("name") or "unnamed check")
        if check.get("ok") is True:
            passed.append(name)
            continue
        failed.append(review_failed_check(check))
    return DecisionReport(
        milestone=milestone,
        decision=decision,
        source=str(gate_report_path),
        passed_checks=passed,
        failed_reviews=failed,
        stop_reason=stop_reason,
    )


def review_failed_check(check: Dict[str, Any]) -> FailureReview:
    name = str(check.get("name") or "unnamed check")
    evidence = str(check.get("evidence") or "")
    details = [str(detail) for detail in check.get("details") or []]
    layer = classify_failure_layer(name, details)
    return FailureReview(
        check=name,
        layer=layer,
        evidence=evidence,
        details=details,
        next_action=next_action_for_layer(layer, name),
    )


def classify_failure_layer(name: str, details: Iterable[str] = ()) -> str:
    text = " ".join([name, *details]).lower()
    if any(term in text for term in ["risk", "owner", "mitigation", "legal regression", "shadow", "license"]):
        return "governance"
    if any(term in text for term in ["corpus", "manifest", "provenance", "parser", "parse", "parsing", "heading", "archetype"]):
        return "ingestion"
    if any(term in text for term in ["retrieval", "recall", "search", "fts", "mixed vietnamese"]):
        return "retrieval"
    if any(term in text for term in ["tool", "argument", "loop"]):
        return "orchestration"
    if any(term in text for term in ["answer", "citation", "hallucinated", "no-answer", "insufficient"]):
        return "synthesis"
    if any(term in text for term in ["baseline", "quality", "latency", "pipeline", "scale", "eval"]):
        return "evaluation"
    return "evaluation"


def next_action_for_layer(layer: str, check_name: str) -> str:
    if layer == "ingestion":
        return "Fix corpus registration, parser output, heading recovery, or provenance before retesting downstream layers."
    if layer == "retrieval":
        return "Inspect missed expected units, then tune aliases, segmentation, field weighting, or query handling from observed failures."
    if layer == "orchestration":
        return "Review tool traces for invalid arguments, repeated searches, or breached call ceilings."
    if layer == "synthesis":
        return "Compare answer text and citations against retrieved units, then adjust support checks or citation selection."
    if layer == "governance":
        return "Fill the governed manifest, risk owner, legal pack, shadow-pack, or license evidence required by the release gate."
    return "Inspect benchmark examples and gate metrics, then document whether the result supports go, revise, or stop."


def decision_report_markdown(report: DecisionReport) -> str:
    lines = [
        f"# {report.milestone} Decision Report",
        "",
        f"**Decision:** `{report.decision}`",
        f"**Source gate report:** `{report.source}`",
    ]
    if report.stop_reason:
        lines.extend(["", f"**Stop reason:** {report.stop_reason}"])

    lines.extend(["", "## Passed Checks", ""])
    if report.passed_checks:
        lines.extend(f"- {check}" for check in report.passed_checks)
    else:
        lines.append("- None")

    lines.extend(["", "## Failed Checks and Failure Review", ""])
    if report.failed_reviews:
        for review in report.failed_reviews:
            lines.extend(
                [
                    f"### {review.check}",
                    "",
                    f"- Layer: `{review.layer}`",
                    f"- Evidence: `{review.evidence}`",
                    f"- Next action: {review.next_action}",
                ]
            )
            if review.details:
                lines.append("- Details:")
                lines.extend(f"  - {detail}" for detail in review.details)
            lines.append("")
    else:
        lines.append("- None")

    lines.extend(
        [
            "## Decision Discipline",
            "",
            "- Do not label retrieval failures as prompt problems without missed-unit evidence.",
            "- Do not label versioning failures as model reasoning issues without provenance review.",
            "- Re-run the gate after the next action and attach the new JSON report.",
            "",
        ]
    )
    return "\n".join(lines)


def write_decision_report(gate_report_path: Path, out_path: Path, stop_reason: str = "") -> DecisionReport:
    report = build_decision_report(gate_report_path, stop_reason=stop_reason)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(decision_report_markdown(report), encoding="utf-8")
    return report
