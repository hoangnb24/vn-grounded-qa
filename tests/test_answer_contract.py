import json
from dataclasses import asdict
from pathlib import Path

from vn_grounded_qa.answer import answer_question
from vn_grounded_qa.contracts import validate_answer_contract
from vn_grounded_qa.store import GroundedStore
from vn_grounded_qa.tools import ToolSession


def test_answer_contract_schema_has_required_fields() -> None:
    schema = json.loads(Path("docs/ANSWER_CONTRACT.schema.json").read_text(encoding="utf-8"))
    required = set(schema["required"])
    assert {"answer", "citations", "confidence_label", "insufficient_evidence", "used_doc_ids", "used_unit_ids", "tool_calls"} <= required


def test_answer_object_matches_contract_shape(tmp_path: Path) -> None:
    store = GroundedStore(tmp_path / "qa.db")
    store.init_schema()
    doc = tmp_path / "doc.md"
    doc.write_text("# Chính sách\n\n## HRM\n\nHRM lưu bằng chứng phê duyệt.\n", encoding="utf-8")
    store.ingest_path(doc)
    answer = asdict(answer_question(ToolSession(store), "HRM lưu gì?"))
    schema = json.loads(Path("docs/ANSWER_CONTRACT.schema.json").read_text(encoding="utf-8"))
    assert set(answer) == set(schema["properties"])
    assert answer["confidence_label"] in schema["properties"]["confidence_label"]["enum"]
    assert validate_answer_contract(answer, schema) == []


def test_answer_contract_validator_rejects_missing_extra_and_wrong_type() -> None:
    schema = json.loads(Path("docs/ANSWER_CONTRACT.schema.json").read_text(encoding="utf-8"))
    bad_answer = {
        "answer": "x",
        "citations": [{"unit_id": "u", "doc_id": "d", "title": "t", "heading_path": "h", "page_start": 0, "page_end": 1}],
        "confidence_label": "certain",
        "insufficient_evidence": "no",
        "used_doc_ids": [],
        "tool_calls": [],
        "extra": True,
    }

    errors = validate_answer_contract(bad_answer, schema)

    assert any("missing required field used_unit_ids" in error for error in errors)
    assert any("unexpected field extra" in error for error in errors)
    assert any("confidence_label" in error and "enum" in error for error in errors)
    assert any("insufficient_evidence" in error and "boolean" in error for error in errors)
    assert any("page_start" in error and ">= 1" in error for error in errors)


def test_answer_contract_validator_enforces_insufficient_confidence_consistency() -> None:
    schema = json.loads(Path("docs/ANSWER_CONTRACT.schema.json").read_text(encoding="utf-8"))
    payload = {
        "answer": "Không đủ bằng chứng.",
        "citations": [],
        "confidence_label": "low",
        "insufficient_evidence": True,
        "used_doc_ids": [],
        "used_unit_ids": [],
        "tool_calls": [],
    }

    errors = validate_answer_contract(payload, schema)

    assert any("must be insufficient" in error for error in errors)


def test_answer_contract_validator_rejects_citations_outside_used_units() -> None:
    schema = json.loads(Path("docs/ANSWER_CONTRACT.schema.json").read_text(encoding="utf-8"))
    payload = {
        "answer": "Có bằng chứng.",
        "citations": [{"unit_id": "u2", "doc_id": "d", "title": "t", "heading_path": "h", "page_start": 1, "page_end": 1}],
        "confidence_label": "medium",
        "insufficient_evidence": False,
        "used_doc_ids": ["d"],
        "used_unit_ids": ["u1"],
        "tool_calls": [],
    }

    errors = validate_answer_contract(payload, schema)

    assert any("cited unit is not present" in error for error in errors)


def test_answer_contract_validator_rejects_citations_outside_used_docs() -> None:
    schema = json.loads(Path("docs/ANSWER_CONTRACT.schema.json").read_text(encoding="utf-8"))
    payload = {
        "answer": "Có bằng chứng.",
        "citations": [{"unit_id": "u1", "doc_id": "d2", "title": "t", "heading_path": "h", "page_start": 1, "page_end": 1}],
        "confidence_label": "medium",
        "insufficient_evidence": False,
        "used_doc_ids": ["d1"],
        "used_unit_ids": ["u1"],
        "tool_calls": [],
    }

    errors = validate_answer_contract(payload, schema)

    assert any("cited document is not present" in error for error in errors)


def test_answer_contract_validator_requires_citations_for_supported_answers() -> None:
    schema = json.loads(Path("docs/ANSWER_CONTRACT.schema.json").read_text(encoding="utf-8"))
    payload = {
        "answer": "Có bằng chứng.",
        "citations": [],
        "confidence_label": "medium",
        "insufficient_evidence": False,
        "used_doc_ids": [],
        "used_unit_ids": [],
        "tool_calls": [],
    }

    errors = validate_answer_contract(payload, schema)

    assert any("supported answers must include at least one citation" in error for error in errors)
    assert any("supported answers must include at least one used unit" in error for error in errors)
    assert any("supported answers must include at least one used document" in error for error in errors)
