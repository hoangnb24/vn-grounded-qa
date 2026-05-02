from pathlib import Path
import json

from vn_grounded_qa.answer import answer_question
from vn_grounded_qa.cli import main
from vn_grounded_qa.eval import estimate_query_cost, run_eval
from vn_grounded_qa.parsers import extract_glossary_terms, parse_file, parse_markdown, units_from_ir
from vn_grounded_qa.store import GroundedStore
from vn_grounded_qa.tools import ToolSession


def make_store(tmp_path: Path) -> GroundedStore:
    store = GroundedStore(tmp_path / "qa.db")
    store.init_schema()
    doc = tmp_path / "policy.md"
    doc.write_text(
        """# Chính sách nghỉ phép

## Điều kiện

Nhân viên chính thức được nghỉ phép năm 12 ngày sau khi hoàn tất thử việc.

## Phê duyệt

Quản lý trực tiếp phải phê duyệt yêu cầu nghỉ phép trên HRM trước ngày nghỉ.

| Loại | Số ngày |
| Nghỉ phép năm | 12 |
""",
        encoding="utf-8",
    )
    store.ingest_path(doc)
    return store


def test_schema_version_is_recorded(tmp_path: Path) -> None:
    store = GroundedStore(tmp_path / "qa.db")
    store.init_schema()
    assert store.schema_version() == 1


def test_ingest_and_search_vietnamese_query(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    hits = store.search_units("nghỉ phép năm bao nhiêu ngày", top_k=5)
    assert hits
    assert "Số ngày: 12" in hits[0].raw_text
    assert hits[0].heading_path == "Chính sách nghỉ phép > Phê duyệt"


def test_ascii_folded_search_matches_diacritics(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    hits = store.search_units("nghi phep nam", top_k=5)
    assert hits
    assert any("nghỉ phép năm" in hit.raw_text for hit in hits)


def test_alias_expansion(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add_alias("HRM", "hệ thống quản lý nhân sự")
    hits = store.search_units("duyet tren he thong quan ly nhan su", top_k=5)
    assert hits
    assert any("HRM" in hit.raw_text for hit in hits)


def test_search_units_supports_document_metadata_filters(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    doc_id = store.search_units("nghỉ phép", top_k=1)[0].doc_id

    hits = store.search_units("nghỉ phép", top_k=5, filters={"doc_id": doc_id, "status": "active"})

    assert hits
    assert {hit.doc_id for hit in hits} == {doc_id}


def test_tool_search_units_records_filters_and_rejects_unknown_filters(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    doc_id = store.search_units("nghỉ phép", top_k=1)[0].doc_id
    session = ToolSession(store)

    hits = session.search_units("nghỉ phép", top_k=2, filters={"doc_id": doc_id})

    assert hits
    assert session.calls[-1]["args"]["filters"] == {"doc_id": doc_id}
    try:
        session.search_units("nghỉ phép", top_k=2, filters={"unsupported": "x"})
    except ValueError as exc:
        assert "Unsupported search filters" in str(exc)
    else:
        raise AssertionError("unsupported search filter should fail")


def test_cli_search_accepts_metadata_filters(tmp_path: Path, capsys) -> None:
    store = make_store(tmp_path)
    doc_id = store.search_units("nghỉ phép", top_k=1)[0].doc_id

    assert main(["--db", str(store.db_path), "search", "nghỉ phép", "--filter", f"doc_id={doc_id}", "--top-k", "5"]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output
    assert {hit["doc_id"] for hit in output} == {doc_id}


def test_alias_csv_import(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    csv_path = tmp_path / "aliases.csv"
    csv_path.write_text("surface_form,canonical_form,lang,domain,alias_type,source\nnhân sự,HRM,vi,hr,synonym,test\n", encoding="utf-8")
    assert store.import_alias_csv(csv_path) == 1
    assert "HRM" in store.resolve_terms("nhân sự")


def test_grounded_answer_contract_and_tool_limits(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    answer = answer_question(ToolSession(store), "Ai phê duyệt yêu cầu nghỉ phép?", top_k=3)
    assert answer.insufficient_evidence is False
    assert answer.citations
    assert answer.used_unit_ids
    assert len(answer.tool_calls) <= 6


def test_applicable_version_tool(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    doc_id = store.search_units("nghỉ phép", top_k=1)[0].doc_id
    session = ToolSession(store)
    version = session.get_applicable_version(doc_id)
    assert version is not None
    assert version["doc_id"] == doc_id
    assert session.calls[-1]["tool"] == "get_applicable_version"


def test_get_document_tool_returns_metadata_and_outline(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    doc_id = store.search_units("nghỉ phép", top_k=1)[0].doc_id

    document = ToolSession(store).get_document(doc_id)

    assert document is not None
    assert document["doc_id"] == doc_id
    assert "outline" in document
    assert any("Chính sách nghỉ phép" in item for item in document["outline"])


def test_applicable_version_prefers_latest_effective_active_version(tmp_path: Path) -> None:
    store = GroundedStore(tmp_path / "qa.db")
    store.init_schema()
    old_doc = tmp_path / "policy_v1.md"
    new_doc = tmp_path / "policy_v2.md"
    old_doc.write_text("# Policy\n\n## Rule\n\nPhiên bản cũ.\n", encoding="utf-8")
    new_doc.write_text("# Policy\n\n## Rule\n\nPhiên bản mới.\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        """{
  "documents": [
    {
      "doc_id": "policy_v1",
      "doc_family_id": "policy_family",
      "title": "Policy v1",
      "archetype": "policy_sop",
      "source_uri": "policy_v1.md",
      "format": "md",
      "language": "vi",
      "provenance_owner": "owner",
      "license": "internal",
      "status": "accepted",
      "version_label": "v1",
      "effective_from": "2026-01-01",
      "effective_to": "2026-01-31"
    },
    {
      "doc_id": "policy_v2",
      "doc_family_id": "policy_family",
      "title": "Policy v2",
      "archetype": "policy_sop",
      "source_uri": "policy_v2.md",
      "format": "md",
      "language": "vi",
      "provenance_owner": "owner",
      "license": "internal",
      "status": "accepted",
      "version_label": "v2",
      "effective_from": "2026-02-01"
    }
  ]
}
""",
        encoding="utf-8",
    )
    store.ingest_manifest(manifest)

    latest = store.get_applicable_version("policy_family")
    old = store.get_applicable_version("policy_family", as_of="2026-01-15")
    new = store.get_applicable_version("policy_family", as_of="2026-02-15")

    assert latest is not None and latest["doc_id"] == "policy_v2"
    assert old is not None and old["doc_id"] == "policy_v1"
    assert new is not None and new["doc_id"] == "policy_v2"


def test_structural_relations_power_context_expansion(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    hit = store.search_units("Quản lý trực tiếp", top_k=1)[0]
    context = ToolSession(store).expand_context(hit.unit_id)
    context_ids = {item["unit_id"] for item in context}
    assert hit.unit_id in context_ids
    assert len(context) >= 2


def test_heuristic_relations_are_populated(tmp_path: Path) -> None:
    store = GroundedStore(tmp_path / "qa.db")
    store.init_schema()
    doc = tmp_path / "legal.md"
    doc.write_text(
        "# Quy định\n\n## Điều 1\n\nNhân viên phải lưu bằng chứng.\n\n## Điều 2\n\nTrường hợp khẩn cấp là ngoại lệ và tham chiếu Điều 1.\n",
        encoding="utf-8",
    )
    store.ingest_path(doc)
    rows = store.conn.execute("SELECT relation_type FROM relations").fetchall()
    relation_types = {row["relation_type"] for row in rows}
    assert "references" in relation_types
    assert "exception_to" in relation_types


def test_same_topic_relations_are_populated(tmp_path: Path) -> None:
    store = GroundedStore(tmp_path / "qa.db")
    store.init_schema()
    doc = tmp_path / "topic.md"
    doc.write_text(
        "# Sổ tay\n\n## HRM\n\nHRM lưu bằng chứng phê duyệt.\n\nHRM gửi thông báo cho nhân sự.\n",
        encoding="utf-8",
    )
    store.ingest_path(doc)

    rows = store.conn.execute("SELECT relation_type, source FROM relations").fetchall()

    assert any(row["relation_type"] == "same_topic" and row["source"] == "topic_key" for row in rows)


def test_tool_session_persists_trace_when_trace_id_is_set(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    session = ToolSession(store, trace_id="trace-1")
    session.search_units("nghỉ phép", top_k=2)
    rows = store.get_tool_trace("trace-1")
    assert len(rows) == 1
    assert rows[0]["tool"] == "search_units"
    assert rows[0]["result_count"] >= 1


def test_cli_ask_can_persist_and_show_trace(tmp_path: Path, capsys) -> None:
    store = make_store(tmp_path)
    db_path = store.db_path
    store.close()

    assert main(["--db", str(db_path), "ask", "Ai phê duyệt yêu cầu nghỉ phép?", "--trace-id", "cli-trace"]) == 0
    capsys.readouterr()
    assert main(["--db", str(db_path), "traces", "list"]) == 0
    list_output = json.loads(capsys.readouterr().out)
    assert list_output[0]["trace_id"] == "cli-trace"
    assert list_output[0]["call_count"] >= 1

    assert main(["--db", str(db_path), "traces", "show", "cli-trace"]) == 0
    show_output = json.loads(capsys.readouterr().out)
    search_calls = [call for call in show_output if call["tool"] == "search_units"]
    assert search_calls
    assert search_calls[0]["args"]["query"] == "Ai phê duyệt yêu cầu nghỉ phép?"


def test_tool_session_enforces_search_ceiling(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    session = ToolSession(store, max_searches=1)
    session.search_units("nghỉ phép", top_k=1)
    try:
        session.search_units("HRM", top_k=1)
    except RuntimeError as exc:
        assert "Search call ceiling" in str(exc)
    else:
        raise AssertionError("expected search ceiling error")


def test_expand_context_depth_is_capped(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    hit = store.search_units("Quản lý trực tiếp", top_k=1)[0]
    shallow = ToolSession(store).expand_context(hit.unit_id, depth=1)
    deep = ToolSession(store).expand_context(hit.unit_id, depth=99)
    assert len(deep) == len(shallow)


def test_no_answer_when_corpus_has_no_evidence(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    answer = answer_question(ToolSession(store), "Quy định về mua cổ phiếu là gì?", top_k=3)
    assert answer.insufficient_evidence is True
    assert answer.confidence_label == "insufficient"


def test_no_answer_when_retrieved_evidence_is_contradictory(tmp_path: Path) -> None:
    store = GroundedStore(tmp_path / "qa.db")
    store.init_schema()
    doc = tmp_path / "contradiction.md"
    doc.write_text(
        """# Chính sách HRM

## Quy định A

Nhân viên phải lưu bằng chứng phê duyệt trên HRM.

## Quy định B

Nhân viên không cần lưu bằng chứng phê duyệt trên HRM.
""",
        encoding="utf-8",
    )
    store.ingest_path(doc)

    answer = answer_question(ToolSession(store), "Nhân viên có phải lưu bằng chứng trên HRM không?", top_k=5)

    assert answer.insufficient_evidence is True
    assert answer.confidence_label == "insufficient"


def test_eval_reports_latency_categories_and_tool_counts(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    expected_unit = store.search_units("nghỉ phép năm", top_k=1)[0].unit_id
    result = run_eval(
        store,
        [
            {
                "question": "Nghỉ phép năm bao nhiêu ngày?",
                "category": "single_unit_factual",
                "expected_unit_ids": [expected_unit],
                "expected_text_contains": ["Số ngày: 12"],
            },
            {
                "question": "Quy định mua cổ phiếu là gì?",
                "category": "no_answer",
                "insufficient_evidence": True,
            },
        ],
        k=5,
    )
    assert result.total == 2
    assert result.recall_at_k == 1.0
    assert result.recall_by_category["single_unit_factual"] == 1.0
    assert result.no_answer_precision == 1.0
    assert result.p50_search_latency_ms >= 0.0
    assert result.p95_search_latency_ms >= 0.0
    assert result.p50_answer_latency_ms >= 0.0
    assert result.p95_answer_latency_ms >= result.p50_answer_latency_ms
    assert result.avg_tool_calls > 0
    assert result.avg_estimated_cost > 0
    assert result.p95_estimated_cost >= result.avg_estimated_cost
    assert result.tool_argument_error_rate == 0.0
    assert result.tool_limit_error_count == 0
    assert result.tool_limit_error_rate == 0.0


def test_eval_can_match_expected_text_without_unit_ids(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    result = run_eval(
        store,
        [
            {
                "question": "Ai phê duyệt nghỉ phép?",
                "category": "single_unit_factual",
                "expected_text_contains": ["quản lý trực tiếp"],
            }
        ],
        k=5,
    )
    assert result.recall_at_k == 1.0


def test_eval_supports_taxonomy_gold_fields_for_answers_and_citations(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    expected = store.search_units("quản lý trực tiếp phê duyệt", top_k=1)[0].unit_id

    result = run_eval(
        store,
        [
            {
                "question": "Ai phê duyệt yêu cầu nghỉ phép?",
                "category": "single_unit_factual",
                "expected_component_unit_ids": [expected],
                "expected_answer_points": ["quản lý trực tiếp"],
                "expected_citation_unit_ids": [expected],
            }
        ],
        k=5,
    )

    assert result.recall_at_k == 1.0
    assert result.answer_correctness == 1.0
    assert result.citation_exactness == 1.0
    assert not result.failures


def test_eval_checks_version_status_exception_gold_fields(tmp_path: Path) -> None:
    store = GroundedStore(tmp_path / "qa.db")
    store.init_schema()
    (tmp_path / "policy_v1.md").write_text("# Policy\n\n## Rule\n\nCũ.\n", encoding="utf-8")
    (tmp_path / "policy_v2.md").write_text("# Policy\n\n## Rule\n\nMới.\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        """{
  "documents": [
    {
      "doc_id": "policy_v1",
      "doc_family_id": "policy_family",
      "title": "Policy v1",
      "archetype": "policy_sop",
      "source_uri": "policy_v1.md",
      "format": "md",
      "language": "vi",
      "provenance_owner": "owner",
      "license": "internal",
      "status": "accepted",
      "version_label": "v1",
      "effective_from": "2026-01-01",
      "effective_to": "2026-01-31"
    },
    {
      "doc_id": "policy_v2",
      "doc_family_id": "policy_family",
      "title": "Policy v2",
      "archetype": "policy_sop",
      "source_uri": "policy_v2.md",
      "format": "md",
      "language": "vi",
      "provenance_owner": "owner",
      "license": "internal",
      "status": "accepted",
      "version_label": "v2",
      "effective_from": "2026-02-01"
    }
  ]
}
""",
        encoding="utf-8",
    )
    store.ingest_manifest(manifest)

    result = run_eval(
        store,
        [
            {
                "question": "Phiên bản nào áp dụng ngày 2026-02-15?",
                "category": "version_status_exception",
                "as_of": "2026-02-15",
                "expected_doc_id": "policy_v2",
            }
        ],
        k=5,
    )

    assert not result.failures


def test_answer_refuses_when_selected_evidence_spans_versions(tmp_path: Path) -> None:
    store = GroundedStore(tmp_path / "qa.db")
    store.init_schema()
    (tmp_path / "policy_v1.md").write_text("# Policy\n\n## Rule\n\nNhân viên phải lưu bằng chứng HRM.\n", encoding="utf-8")
    (tmp_path / "policy_v2.md").write_text("# Policy\n\n## Rule\n\nNhân viên phải lưu bằng chứng HRM và mã phê duyệt.\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        """{
  "documents": [
    {
      "doc_id": "policy_v1",
      "doc_family_id": "policy_family",
      "title": "Policy v1",
      "archetype": "policy_sop",
      "source_uri": "policy_v1.md",
      "format": "md",
      "language": "vi",
      "provenance_owner": "owner",
      "license": "internal",
      "status": "accepted",
      "version_label": "v1",
      "effective_from": "2026-01-01"
    },
    {
      "doc_id": "policy_v2",
      "doc_family_id": "policy_family",
      "title": "Policy v2",
      "archetype": "policy_sop",
      "source_uri": "policy_v2.md",
      "format": "md",
      "language": "vi",
      "provenance_owner": "owner",
      "license": "internal",
      "status": "accepted",
      "version_label": "v2",
      "effective_from": "2026-01-15"
    }
  ]
}
""",
        encoding="utf-8",
    )
    store.ingest_manifest(manifest)

    answer = answer_question(ToolSession(store), "Nhân viên phải lưu bằng chứng HRM không?", top_k=5)

    assert answer.insufficient_evidence is True
    assert answer.confidence_label == "insufficient"


def test_eval_checks_expected_doc_ids_for_multidoc_answers(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    hit = store.search_units("quản lý trực tiếp phê duyệt", top_k=1)[0]

    result = run_eval(
        store,
        [
            {
                "question": "Ai phê duyệt yêu cầu nghỉ phép?",
                "category": "multidoc_synthesis",
                "expected_component_unit_ids": [hit.unit_id],
                "expected_answer_points": ["quản lý trực tiếp"],
                "expected_doc_ids": [hit.doc_id],
            }
        ],
        k=5,
    )

    assert result.answer_correctness == 1.0
    assert not result.failures


def test_eval_checks_alias_terms_and_expected_row_or_item(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add_alias("HRM", "hệ thống quản lý nhân sự")

    result = run_eval(
        store,
        [
            {
                "question": "HRM phê duyệt gì?",
                "category": "mixed_vi_en",
                "aliases_or_terms": ["HRM", "hệ thống quản lý nhân sự"],
                "expected_text_contains": ["HRM"],
            },
            {
                "question": "Nghỉ phép năm bao nhiêu ngày?",
                "category": "table_list_structure",
                "expected_row_or_item": "Số ngày: 12",
            },
        ],
        k=5,
    )

    assert result.recall_at_k == 1.0
    assert not result.failures


def test_identifier_extraction_covers_paths_codes_and_versions() -> None:
    terms = extract_glossary_terms("Endpoint /search_units dùng HRM cho QD-12 và bản 1.2.3 trong approval_flow")

    assert "/search_units" in terms
    assert "HRM" in terms
    assert "QD-12" in terms
    assert "1.2.3" in terms
    assert "approval_flow" in terms


def test_estimate_query_cost_is_deterministic() -> None:
    assert estimate_query_cost([{"tool": "search_units"}, {"tool": "read_units"}]) == 0.0002


def test_faq_question_and_answer_are_one_unit(tmp_path: Path) -> None:
    store = GroundedStore(tmp_path / "qa.db")
    store.init_schema()
    doc = tmp_path / "faq.md"
    doc.write_text(
        "# FAQ\n\n## Câu hỏi thường gặp\n\nHỏi: HRM dùng để làm gì?\n\nĐáp: HRM dùng để lưu bằng chứng phê duyệt.\n",
        encoding="utf-8",
    )
    store.ingest_path(doc)
    hit = store.search_units("HRM dùng để làm gì", top_k=1)[0]
    assert "Đáp: HRM dùng để lưu bằng chứng" in hit.raw_text


def test_markdown_parser_emits_documented_block_taxonomy(tmp_path: Path) -> None:
    doc = tmp_path / "taxonomy.md"
    doc.write_text(
        """# Sổ tay vận hành

## Điều 1. Phạm vi

Khoản 1 áp dụng cho nhóm vận hành.

## Quy trình

- Bước 1: Tạo yêu cầu trên HRM.
- Kiểm tra bằng chứng.

| Trường | Giá trị |
|---|---|
| SLA | 2 ngày |

> Lưu ý nội bộ.

```sql
select * from approvals;
```

![Sơ đồ phê duyệt](approval.png)

Hỏi: HRM lưu gì?

Đáp: HRM lưu bằng chứng.
""",
        encoding="utf-8",
    )

    ir = parse_markdown(doc)
    block_types = [block.block_type for block in ir.blocks]

    assert "title" in block_types
    assert "legal_article" in block_types
    assert "legal_clause" in block_types
    assert "list" in block_types
    assert "step" in block_types
    assert "list_item" in block_types
    assert "table" in block_types
    assert "table_row" in block_types
    assert "table_cell" in block_types
    assert "quote" in block_types
    assert "code_block" in block_types
    assert "figure" in block_types
    assert "caption" in block_types
    assert "faq_question" in block_types
    assert "faq_answer" in block_types

    table = next(block for block in ir.blocks if block.block_type == "table")
    table_rows = [block for block in ir.blocks if block.block_type == "table_row"]
    table_cells = [block for block in ir.blocks if block.block_type == "table_cell"]
    assert table_rows
    assert table_cells
    assert all(row.parent_block_id == table.block_id for row in table_rows)
    assert all(cell.parent_block_id in {row.block_id for row in table_rows} for cell in table_cells)


def test_auto_parser_uses_optional_parser_order_then_local_fallback(tmp_path: Path) -> None:
    doc = tmp_path / "auto.md"
    doc.write_text("# Title\n\nBody", encoding="utf-8")

    ir = parse_file(doc, parser="auto")

    assert ir.document_meta.parser_name == "markdown-lite"
    assert any("auto parser fell back" in warning for warning in ir.quality["parser_warnings"])


def test_container_blocks_do_not_duplicate_canonical_units(tmp_path: Path) -> None:
    doc = tmp_path / "structured.md"
    doc.write_text(
        """# Handbook

## Checklist

- Bước 1: Tạo yêu cầu.
- Lưu mã yêu cầu.

| Trường | Giá trị |
|---|---|
| SLA | 2 ngày |
""",
        encoding="utf-8",
    )

    units = units_from_ir(parse_markdown(doc))
    unit_types = [unit.unit_type for unit in units]

    assert unit_types.count("table") == 1
    assert "table_cell" not in unit_types
    assert "list" not in unit_types
    assert "step" in unit_types
    assert "list_item" in unit_types


def test_units_from_ir_uses_title_and_legal_headings_as_context(tmp_path: Path) -> None:
    doc = tmp_path / "legal.md"
    doc.write_text(
        """# Quy chế

## Điều 2. Nghĩa vụ

Nhân viên phải lưu bằng chứng.
""",
        encoding="utf-8",
    )

    units = units_from_ir(parse_markdown(doc))

    assert units
    assert units[0].heading_path == "Quy chế > Điều 2. Nghĩa vụ"


def test_units_from_ir_sets_parent_unit_ids_from_heading_hierarchy(tmp_path: Path) -> None:
    doc = tmp_path / "nested.md"
    doc.write_text(
        """# Handbook

## Parent

Parent unit.

### Child

Child unit.
""",
        encoding="utf-8",
    )

    units = units_from_ir(parse_markdown(doc))
    parent = next(unit for unit in units if unit.raw_text == "Parent unit.")
    child = next(unit for unit in units if unit.raw_text == "Child unit.")

    assert child.parent_unit_id == parent.unit_id
