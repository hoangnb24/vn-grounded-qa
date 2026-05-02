"""Bounded semantic helpers for LLM-assisted answering."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterable, List, Set

from pydantic import BaseModel

from .llm import LLMError, complete_json, load_config, metadata_from_config
from .semantic_models import AnswerDraft, EvidenceDecision, QueryPlan


def plan_query(question: str) -> QueryPlan:
    prompt = "\n".join(
        [
            "Plan retrieval for a Vietnamese grounded-QA system.",
            "Return only structured JSON that matches the supplied schema.",
            "Do not answer the question.",
            f"Question: {question}",
        ]
    )
    return complete_json(prompt, QueryPlan)


def judge_evidence(question: str, hits: list[dict]) -> EvidenceDecision:
    allowed = {str(hit.get("unit_id") or "") for hit in hits}
    prompt = "\n".join(
        [
            "Judge whether the supplied evidence units can answer the question.",
            "Use only the listed unit_id values. Do not invent documents, citations, or unit IDs.",
            "If evidence is missing, contradictory, or version-unclear, mark it accordingly.",
            f"Question: {question}",
            "Evidence units:",
            json.dumps([prompt_unit(hit) for hit in hits], ensure_ascii=False),
        ]
    )
    decision = complete_json(prompt, EvidenceDecision)
    validate_known_unit_ids(decision.required_unit_ids, allowed, "required_unit_ids")
    validate_known_unit_ids([judgment.unit_id for judgment in decision.judgments], allowed, "judgments.unit_id")
    return decision


def compose_answer(question: str, units: list[dict], decision: EvidenceDecision) -> AnswerDraft:
    allowed = {str(unit.get("unit_id") or "") for unit in units}
    prompt = "\n".join(
        [
            "Compose a concise Vietnamese answer using only supplied evidence text.",
            "Do not create citations or cite documents. Return used_unit_ids only from the supplied units.",
            "If the decision is not answerable, return confidence_label insufficient and no used_unit_ids.",
            f"Question: {question}",
            "Evidence decision:",
            decision.model_dump_json(),
            "Readable units:",
            json.dumps([prompt_unit(unit) for unit in units], ensure_ascii=False),
        ]
    )
    draft = complete_json(prompt, AnswerDraft)
    validate_known_unit_ids(draft.used_unit_ids, allowed, "used_unit_ids")
    return draft


def validate_known_unit_ids(unit_ids: Iterable[str], allowed: Set[str], field: str) -> None:
    unknown = sorted({str(unit_id) for unit_id in unit_ids if str(unit_id) not in allowed})
    if unknown:
        config = load_config()
        raise LLMError(
            "llm_unknown_unit_id",
            f"LLM returned unknown {field}: {', '.join(unknown)}",
            metadata_from_config(config, BaseModel),
        )


def prompt_unit(hit: Dict[str, Any]) -> Dict[str, object]:
    return {
        "unit_id": str(hit.get("unit_id") or ""),
        "doc_id": str(hit.get("doc_id") or ""),
        "title": str(hit.get("title") or ""),
        "heading_path": str(hit.get("heading_path") or ""),
        "page_start": int(hit.get("page_start") or 1),
        "page_end": int(hit.get("page_end") or 1),
        "text": str(hit.get("raw_text") or "")[:1400],
    }


def llm_trace(tool: str, schema: str, result_count: int = 1, failure_type: str = "", fallback_path: str = "", started: float | None = None) -> Dict[str, object]:
    config = load_config()
    args: Dict[str, object] = {
        "provider": config.provider,
        "model": config.model,
        "timeout_ms": config.timeout_ms,
        "retry_attempts": config.retry_attempts,
        "schema": schema,
        "fallback_path": fallback_path,
    }
    if failure_type:
        args["failure_type"] = failure_type
    if started is not None:
        args["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return {"tool": tool, "args": args, "result_count": result_count}

