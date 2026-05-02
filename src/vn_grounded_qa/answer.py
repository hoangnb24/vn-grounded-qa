"""Grounded extractive answer synthesis."""

from __future__ import annotations

from typing import Dict, Iterable, List, Set

from dataclasses import asdict

from .contracts import validate_answer_contract
from .models import Citation, GroundedAnswer
from .normalize import ascii_fold, fts_query_terms, identifier_variants
from .store import source_pair_doc_ids
from .tools import ToolSession

STOP_TERMS: Set[str] = {
    "ai",
    "bang",
    "ban",
    "cach",
    "cai",
    "can",
    "các",
    "cho",
    "cong",
    "corpus",
    "cua",
    "của",
    "dan",
    "dieu",
    "diem",
    "gi",
    "gì",
    "hoa",
    "kien",
    "khi",
    "khong",
    "la",
    "là",
    "nao",
    "nào",
    "nay",
    "neu",
    "nhung",
    "những",
    "nhom",
    "thu",
    "tuc",
    "quy",
    "quy định",
    "the",
    "thế",
    "trong",
    "lien",
    "quan",
    "den",
    "dinh",
    "dung",
    "duoc",
    "hai",
    "hop",
    "kiem",
    "ket",
    "lieu",
    "loai",
    "luat",
    "luu",
    "nhan",
    "nam",
    "noi",
    "phap",
    "phi",
    "tai",
    "tinh",
    "toi",
    "tro",
    "truoc",
    "vien",
    "van",
    "ve",
    "về",
    "viet",
    "voi",
    "xin",
}

NEGATIVE_POLICY_PATTERNS = [
    "khong phai",
    "khong can",
    "khong duoc",
    "khong yeu cau",
    "mien",
]

POSITIVE_POLICY_PATTERNS = [
    "phai",
    "can",
    "duoc",
    "yeu cau",
    "bat buoc",
]

UNSUPPORTED_DOMAIN_PATTERNS = [
    "visa",
    "hoa ky",
    "chung khoan",
    "co phieu",
    "giay phep xay dung",
    "xay dung nha",
]


def answer_question(session: ToolSession, question: str, top_k: int = 5) -> GroundedAnswer:
    terms = session.resolve_terms(question)
    hits = session.search_units(" ".join([question, *terms]), top_k=top_k)
    support_question = " ".join([question, *terms])
    selected = select_supporting_hits(support_question, hits, limit=5)
    selected = include_source_pair_hits(support_question, hits, selected, limit=5)
    if (
        not selected
        or not has_sufficient_support(support_question, selected)
        or has_contradictory_evidence(support_question, selected)
        or has_unclear_applicable_version(selected)
    ):
        return GroundedAnswer(
            answer="Không đủ bằng chứng trong kho tài liệu để trả lời câu hỏi này.",
            citations=[],
            confidence_label="insufficient",
            insufficient_evidence=True,
            used_doc_ids=[],
            used_unit_ids=[],
            tool_calls=session.calls,
        )

    read = session.read_units([hit["unit_id"] for hit in selected])
    citations = [citation_from_hit(hit) for hit in read]
    answer = synthesize_extract(read)
    confidence = "high" if len(read) >= 2 else "medium"
    return GroundedAnswer(
        answer=answer,
        citations=citations,
        confidence_label=confidence,
        insufficient_evidence=False,
        used_doc_ids=sorted({hit["doc_id"] for hit in read}),
        used_unit_ids=[hit["unit_id"] for hit in read],
        tool_calls=session.calls,
    )


def insufficient_answer(session: ToolSession) -> GroundedAnswer:
    return GroundedAnswer(
        answer="Không đủ bằng chứng trong kho tài liệu để trả lời câu hỏi này.",
        citations=[],
        confidence_label="insufficient",
        insufficient_evidence=True,
        used_doc_ids=[],
        used_unit_ids=[],
        tool_calls=session.calls,
    )


def answer_question_llm_assisted(session: ToolSession, question: str, top_k: int = 5) -> GroundedAnswer:
    """Answer through a bounded LLM layer, with deterministic fallback.

    The LLM may plan, judge, and draft text, but citations are always assembled
    from units read through the local tool session and the answer contract is
    validated before returning.
    """

    try:
        from .llm import LLMError
        from .semantic import compose_answer, judge_evidence, llm_trace, plan_query
    except ImportError:
        fallback = deterministic_fallback(session, question, top_k)
        fallback.tool_calls.append(
            {
                "tool": "llm.dependency",
                "args": {
                    "failure_type": "llm_dependency_missing",
                    "fallback_path": "deterministic",
                    "install": "pip install -e '.[llm]'",
                },
                "result_count": 0,
            }
        )
        return fallback

    try:
        plan = plan_query(question)
        session.calls.append(llm_trace("llm.plan_query", "QueryPlan"))
        terms = session.resolve_terms(question)
        search_queries = [question, *plan.rewritten_queries]
        hits: List[Dict[str, object]] = []
        for query in compact_search_queries(search_queries):
            hits.extend(session.search_units(" ".join([query, *terms]), top_k=top_k, doc_type=plan.doc_type_filter))
        hits = dedupe_hits(hits)[: max(top_k, 5)]
        decision = judge_evidence(question, hits)
        session.calls.append(llm_trace("llm.judge_evidence", "EvidenceDecision"))
        if decision.answerability != "answerable":
            answer = insufficient_answer(session)
            answer.tool_calls.append(llm_trace("llm.fallback", "EvidenceDecision", result_count=0, failure_type=f"llm_{decision.answerability}", fallback_path="insufficient"))
            return answer
        required_ids = [unit_id for unit_id in decision.required_unit_ids if unit_id]
        read = session.read_units(required_ids)
        read_ids = {str(hit["unit_id"]) for hit in read}
        if set(required_ids) != read_ids:
            raise LLMError("llm_unknown_unit_id", "Required LLM unit IDs were not readable from the store.")
        support_question = " ".join([question, *terms])
        if (
            not read
            or not has_sufficient_support(support_question, read)
            or has_contradictory_evidence(support_question, read)
            or has_unclear_applicable_version(read)
        ):
            raise LLMError("llm_deterministic_validator_rejected", "Deterministic support checks rejected the LLM evidence decision.")
        draft = compose_answer(question, read, decision)
        session.calls.append(llm_trace("llm.compose_answer", "AnswerDraft"))
        used_ids = [unit_id for unit_id in draft.used_unit_ids if unit_id in read_ids]
        if set(required_ids) - set(used_ids):
            raise LLMError("llm_deterministic_validator_rejected", "LLM draft omitted a required supporting unit.")
        used_hits = [hit for hit in read if str(hit["unit_id"]) in set(used_ids)]
        if not used_hits:
            raise LLMError("llm_deterministic_validator_rejected", "LLM draft did not use any readable evidence units.")
        answer = GroundedAnswer(
            answer=draft.answer,
            citations=[citation_from_hit(hit) for hit in used_hits],
            confidence_label=draft.confidence_label,
            insufficient_evidence=False,
            used_doc_ids=sorted({str(hit["doc_id"]) for hit in used_hits}),
            used_unit_ids=[str(hit["unit_id"]) for hit in used_hits],
            tool_calls=session.calls,
        )
        contract_errors = validate_answer_contract(asdict(answer))
        if contract_errors:
            raise LLMError("llm_answer_contract_violation", "; ".join(contract_errors))
        return answer
    except LLMError as exc:
        fallback = deterministic_fallback(session, question, top_k)
        fallback.tool_calls.append(
            {
                "tool": "llm.fallback",
                "args": {
                    **exc.metadata,
                    "failure_type": exc.failure_type,
                    "fallback_path": "deterministic",
                },
                "result_count": 0,
            }
        )
        return fallback


def deterministic_fallback(session: ToolSession, question: str, top_k: int) -> GroundedAnswer:
    fallback_session = ToolSession(session.store)
    answer = answer_question(fallback_session, question, top_k=top_k)
    answer.tool_calls[:] = [*session.calls, *answer.tool_calls]
    return answer


def compact_search_queries(queries: List[str]) -> List[str]:
    cleaned: List[str] = []
    seen: Set[str] = set()
    for query in queries:
        value = " ".join(str(query).split())
        if value and value not in seen:
            cleaned.append(value)
            seen.add(value)
    if len(cleaned) <= 2:
        return cleaned
    return [cleaned[0], " ".join(cleaned[1:])]


def dedupe_hits(hits: List[Dict[str, object]]) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    seen: Set[str] = set()
    for hit in hits:
        unit_id = str(hit.get("unit_id") or "")
        if unit_id and unit_id not in seen:
            out.append(hit)
            seen.add(unit_id)
    return out


def include_source_pair_hits(
    question: str,
    hits: List[Dict[str, object]],
    selected: List[Dict[str, object]],
    limit: int = 5,
) -> List[Dict[str, object]]:
    preferred_doc_ids = source_pair_doc_ids(question)
    if not preferred_doc_ids:
        return selected
    by_doc: Dict[str, Dict[str, object]] = {}
    for hit in hits:
        doc_id = str(hit.get("doc_id") or "")
        if doc_id in preferred_doc_ids and doc_id not in by_doc:
            by_doc[doc_id] = hit
    if not by_doc:
        return selected
    out: List[Dict[str, object]] = []
    seen_units: Set[str] = set()
    for doc_id in preferred_doc_ids:
        hit = by_doc.get(doc_id)
        if hit and str(hit["unit_id"]) not in seen_units:
            out.append(hit)
            seen_units.add(str(hit["unit_id"]))
    for hit in selected:
        if str(hit["unit_id"]) not in seen_units:
            out.append(hit)
            seen_units.add(str(hit["unit_id"]))
        if len(out) >= limit:
            break
    return out[:limit]


def has_sufficient_support(question: str, hits: List[Dict[str, object]]) -> bool:
    terms = salient_terms(question)
    if not terms:
        return bool(hits)
    evidence = ascii_fold("\n".join(hit_evidence_text(hit) for hit in hits[:5]))
    question_folded = ascii_fold(question)
    for pattern in UNSUPPORTED_DOMAIN_PATTERNS:
        if pattern in question_folded and pattern not in evidence:
            return False
    matched = {term for term in terms if term in evidence}
    return len(matched) / len(terms) >= 0.40


def has_contradictory_evidence(question: str, hits: List[Dict[str, object]]) -> bool:
    terms = salient_terms(question)
    if not terms:
        return False
    positive_terms: Set[str] = set()
    negative_terms: Set[str] = set()
    for hit in hits[:5]:
        evidence = ascii_fold(hit_evidence_text(hit))
        matched_terms = {term for term in terms if term in evidence}
        if not matched_terms:
            continue
        has_negative = any(pattern in evidence for pattern in NEGATIVE_POLICY_PATTERNS)
        has_positive = any(pattern in evidence for pattern in POSITIVE_POLICY_PATTERNS)
        if has_negative:
            negative_terms.update(matched_terms)
        if has_positive and not has_negative:
            positive_terms.update(matched_terms)
    return bool(positive_terms.intersection(negative_terms))


def has_unclear_applicable_version(hits: List[Dict[str, object]]) -> bool:
    docs_by_family: Dict[str, Set[str]] = {}
    for hit in hits[:5]:
        family = str(hit.get("doc_family_id") or hit.get("doc_id") or "")
        doc_id = str(hit.get("doc_id") or "")
        if not family or not doc_id:
            continue
        docs_by_family.setdefault(family, set()).add(doc_id)
    return any(len(doc_ids) > 1 for doc_ids in docs_by_family.values())


def select_supporting_hits(question: str, hits: List[Dict[str, object]], limit: int = 5) -> List[Dict[str, object]]:
    terms = salient_terms(question)
    if not terms:
        return hits[:limit]
    selected: List[Dict[str, object]] = []
    covered = set()
    for hit in hits:
        evidence = ascii_fold(hit_evidence_text(hit))
        hit_terms = {term for term in terms if term in evidence}
        if hit_terms - covered or not selected:
            selected.append(hit)
            covered.update(hit_terms)
        if len(selected) >= limit or len(covered) == len(terms):
            break
    if len(selected) < min(limit, len(hits)):
        selected_ids = {hit["unit_id"] for hit in selected}
        for hit in hits:
            if hit["unit_id"] not in selected_ids:
                selected.append(hit)
            if len(selected) >= limit:
                break
    return selected


def salient_terms(question: str) -> List[str]:
    terms = []
    seen = set()
    for term in fts_query_terms(ascii_fold(question)):
        if len(term) < 3 or term in STOP_TERMS or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def hit_evidence_text(hit: Dict[str, object]) -> str:
    return " ".join(
        [
            str(hit.get("title") or ""),
            str(hit.get("heading_path") or ""),
            str(hit.get("raw_text") or ""),
            " ".join(identifier_variants(str(hit.get("doc_id") or ""))),
        ]
    ).lower()


def citation_from_hit(hit: Dict[str, object]) -> Citation:
    return Citation(
        unit_id=str(hit["unit_id"]),
        doc_id=str(hit["doc_id"]),
        title=str(hit["title"]),
        heading_path=str(hit.get("heading_path") or ""),
        page_start=int(hit["page_start"]),
        page_end=int(hit["page_end"]),
    )


def synthesize_extract(hits: Iterable[Dict[str, object]]) -> str:
    lines: List[str] = []
    for index, hit in enumerate(hits, start=1):
        text = compact(str(hit["raw_text"]))
        anchor = format_anchor(hit)
        lines.append(f"{index}. {text} ({anchor})")
    if not lines:
        return "Không đủ bằng chứng trong kho tài liệu để trả lời câu hỏi này."
    return "Dựa trên các đoạn được tìm thấy:\n" + "\n".join(lines)


def compact(text: str, limit: int = 520) -> str:
    value = " ".join(text.split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def format_anchor(hit: Dict[str, object]) -> str:
    doc_id = str(hit["doc_id"])
    identifiers = ", ".join(identifier_variants(doc_id))
    title = str(hit["title"])
    heading = str(hit.get("heading_path") or "").strip()
    page_start = int(hit["page_start"])
    page_end = int(hit["page_end"])
    page = f"tr. {page_start}" if page_start == page_end else f"tr. {page_start}-{page_end}"
    if heading:
        return f"{identifiers}, {title}, {heading}, {page}"
    return f"{identifiers}, {title}, {page}"
