import json
from pathlib import Path

import pytest

from vn_grounded_qa.answer import answer_question, answer_question_llm_assisted
from vn_grounded_qa.cli import main
from vn_grounded_qa.eval import run_eval
from vn_grounded_qa.llm import LLMError
from vn_grounded_qa.semantic import judge_evidence
from vn_grounded_qa.semantic_models import AnswerDraft, EvidenceDecision, QueryPlan
from vn_grounded_qa.store import GroundedStore
from vn_grounded_qa.tools import ToolSession


def make_store(tmp_path: Path) -> GroundedStore:
    store = GroundedStore(tmp_path / "qa.db")
    store.init_schema()
    doc = tmp_path / "policy.md"
    doc.write_text(
        """# Chính sách HRM

## Bằng chứng

Nhân viên phải lưu bằng chứng phê duyệt trên HRM trước khi hoàn tất yêu cầu.

## Ngoại lệ

Trường hợp không có HRM thì phải lưu biên bản xác nhận của quản lý.
""",
        encoding="utf-8",
    )
    store.ingest_path(doc)
    return store


def test_query_planning_schema_validation_rejects_extra_fields() -> None:
    with pytest.raises(Exception):
        QueryPlan.model_validate(
            {
                "rewritten_queries": ["HRM lưu bằng chứng"],
                "intent": "find evidence requirement",
                "entities": ["HRM"],
                "doc_type_filter": None,
                "needs_version_resolution": False,
                "needs_cross_document_reasoning": False,
                "reason": "bounded semantic query planning",
                "extra": "not allowed",
            }
        )


def test_evidence_judge_rejects_unknown_unit_id(monkeypatch) -> None:
    def fake_complete(prompt, schema, model=None):
        return EvidenceDecision(
            answerability="answerable",
            judgments=[],
            required_unit_ids=["missing-unit"],
            reason="bad id",
        )

    monkeypatch.setattr("vn_grounded_qa.semantic.complete_json", fake_complete)

    with pytest.raises(LLMError) as exc:
        judge_evidence("HRM lưu gì?", [{"unit_id": "known-unit", "raw_text": "HRM lưu bằng chứng."}])

    assert exc.value.failure_type == "llm_unknown_unit_id"


def test_llm_assisted_answer_cannot_cite_units_not_read(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    hit = store.search_units("HRM bằng chứng", top_k=1)[0]

    def fake_complete(prompt, schema, model=None):
        if schema is QueryPlan:
            return QueryPlan(
                rewritten_queries=["HRM lưu bằng chứng"],
                intent="answer",
                entities=["HRM"],
                doc_type_filter=None,
                needs_version_resolution=False,
                needs_cross_document_reasoning=False,
                reason="test",
            )
        if schema is EvidenceDecision:
            return EvidenceDecision(
                answerability="answerable",
                judgments=[],
                required_unit_ids=[hit.unit_id],
                reason="supported",
            )
        if schema is AnswerDraft:
            return AnswerDraft(answer="HRM lưu bằng chứng.", used_unit_ids=["unknown-unit"], confidence_label="high")
        raise AssertionError(schema)

    monkeypatch.setattr("vn_grounded_qa.semantic.complete_json", fake_complete)

    answer = answer_question_llm_assisted(ToolSession(store), "HRM lưu gì?", top_k=3)

    assert any(call["args"].get("failure_type") == "llm_unknown_unit_id" for call in answer.tool_calls if call["tool"] == "llm.fallback")
    assert set(citation.unit_id for citation in answer.citations).issubset(set(answer.used_unit_ids))


def test_llm_assisted_no_answer_returns_empty_citations(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)

    def fake_complete(prompt, schema, model=None):
        if schema is QueryPlan:
            return QueryPlan(
                rewritten_queries=[],
                intent="unsupported domain",
                entities=[],
                doc_type_filter=None,
                needs_version_resolution=False,
                needs_cross_document_reasoning=False,
                reason="test",
            )
        if schema is EvidenceDecision:
            return EvidenceDecision(answerability="insufficient", judgments=[], required_unit_ids=[], reason="not in corpus")
        raise AssertionError(schema)

    monkeypatch.setattr("vn_grounded_qa.semantic.complete_json", fake_complete)

    answer = answer_question_llm_assisted(ToolSession(store), "Quy định visa Hoa Kỳ là gì?", top_k=3)

    assert answer.insufficient_evidence is True
    assert answer.citations == []
    assert answer.used_unit_ids == []


def test_contradictory_evidence_becomes_insufficient(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)

    def fake_complete(prompt, schema, model=None):
        if schema is QueryPlan:
            return QueryPlan(
                rewritten_queries=["HRM có bắt buộc không"],
                intent="policy contradiction",
                entities=["HRM"],
                doc_type_filter=None,
                needs_version_resolution=False,
                needs_cross_document_reasoning=False,
                reason="test",
            )
        if schema is EvidenceDecision:
            return EvidenceDecision(answerability="contradictory", judgments=[], required_unit_ids=[], reason="mixed policy")
        raise AssertionError(schema)

    monkeypatch.setattr("vn_grounded_qa.semantic.complete_json", fake_complete)

    answer = answer_question_llm_assisted(ToolSession(store), "Nhân viên có phải lưu bằng chứng trên HRM không?", top_k=5)

    assert answer.insufficient_evidence is True
    assert answer.confidence_label == "insufficient"


def test_current_deterministic_mode_still_works(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    answer = answer_question(ToolSession(store), "HRM lưu gì?", top_k=3)
    assert answer.insufficient_evidence is False
    assert answer.citations


def test_cli_mode_switch_works(monkeypatch, tmp_path: Path, capsys) -> None:
    store = make_store(tmp_path)
    hit = store.search_units("HRM bằng chứng", top_k=1)[0]

    def fake_complete(prompt, schema, model=None):
        if schema is QueryPlan:
            return QueryPlan(
                rewritten_queries=[],
                intent="answer",
                entities=["HRM"],
                doc_type_filter=None,
                needs_version_resolution=False,
                needs_cross_document_reasoning=False,
                reason="test",
            )
        if schema is EvidenceDecision:
            return EvidenceDecision(answerability="answerable", judgments=[], required_unit_ids=[hit.unit_id], reason="supported")
        if schema is AnswerDraft:
            return AnswerDraft(answer="HRM lưu bằng chứng phê duyệt.", used_unit_ids=[hit.unit_id], confidence_label="high")
        raise AssertionError(schema)

    monkeypatch.setattr("vn_grounded_qa.semantic.complete_json", fake_complete)

    assert main(["--db", str(store.db_path), "ask", "HRM lưu gì?", "--mode", "llm-assisted"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["insufficient_evidence"] is False
    assert payload["citations"]


def test_eval_can_compare_deterministic_and_llm_assisted(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    hit = store.search_units("HRM bằng chứng", top_k=1)[0]
    rows = [
        {
            "question": "HRM lưu gì?",
            "category": "single_unit_factual",
            "expected_answer_contains": ["bằng chứng"],
            "expected_citation_unit_ids": [hit.unit_id],
        }
    ]

    def fake_complete(prompt, schema, model=None):
        if schema is QueryPlan:
            return QueryPlan(
                rewritten_queries=[],
                intent="answer",
                entities=["HRM"],
                doc_type_filter=None,
                needs_version_resolution=False,
                needs_cross_document_reasoning=False,
                reason="test",
            )
        if schema is EvidenceDecision:
            return EvidenceDecision(answerability="answerable", judgments=[], required_unit_ids=[hit.unit_id], reason="supported")
        if schema is AnswerDraft:
            return AnswerDraft(answer="HRM lưu bằng chứng phê duyệt.", used_unit_ids=[hit.unit_id], confidence_label="high")
        raise AssertionError(schema)

    monkeypatch.setattr("vn_grounded_qa.semantic.complete_json", fake_complete)

    deterministic = run_eval(store, rows, k=3, mode="deterministic")
    llm_assisted = run_eval(store, rows, k=3, mode="llm-assisted")

    assert deterministic.mode == "deterministic"
    assert llm_assisted.mode == "llm-assisted"
    assert llm_assisted.estimated_llm_calls == 3
    assert llm_assisted.citation_exactness == 1.0
