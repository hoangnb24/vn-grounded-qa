from pathlib import Path

from vn_grounded_qa.cli import main
import json

from vn_grounded_qa.baselines import baseline_comparison_markdown, compare_sparse_to_baseline, run_thin_rag_baseline, write_baseline_comparison_report
from vn_grounded_qa.corpus import document_stub, write_manifest_template, write_synthetic_architecture_corpus
from vn_grounded_qa.eval import EvalResult, run_eval
import vn_grounded_qa.gates as gates_module
from vn_grounded_qa.gates import provenance_version_errors, run_m0_gate, run_m1_gate, run_m2_gate, run_m3_gate, run_m4_gate, run_m5_gate, run_m6_gate, run_release_gate
from vn_grounded_qa.store import GroundedStore


def write_minimal_taxonomy(path: Path) -> None:
    path.write_text(
        """version: 1
categories:
  - id: single_unit_factual
    required_count: 1
rules:
  total_required_questions: 1
  max_auto_generated_fraction: 0.4
""",
        encoding="utf-8",
    )


def test_m0_gate_goes_with_synthetic_manifest_and_taxonomy(tmp_path: Path) -> None:
    manifest = tmp_path / "architecture" / "manifest.json"
    taxonomy = tmp_path / "taxonomy.yaml"
    write_minimal_taxonomy(taxonomy)
    write_synthetic_architecture_corpus(manifest)
    report = run_m0_gate(manifest, taxonomy)
    assert report.decision == "go"
    assert all(check.ok for check in report.checks)


def test_m0_gate_cli_writes_report(tmp_path: Path) -> None:
    manifest = tmp_path / "architecture" / "manifest.json"
    taxonomy = tmp_path / "taxonomy.yaml"
    out = tmp_path / "reports" / "m0.json"
    write_minimal_taxonomy(taxonomy)
    write_synthetic_architecture_corpus(manifest)
    assert main(["gates", "m0", "--manifest", str(manifest), "--taxonomy", str(taxonomy), "--out", str(out)]) == 0
    assert out.exists()


def test_m0_gate_rejects_empty_taxonomy_shape(tmp_path: Path) -> None:
    manifest = tmp_path / "architecture" / "manifest.json"
    taxonomy = tmp_path / "taxonomy.yaml"
    taxonomy.write_text("version: 1\n", encoding="utf-8")
    write_synthetic_architecture_corpus(manifest)

    report = run_m0_gate(manifest, taxonomy)

    assert report.decision == "stop"
    taxonomy_check = next(check for check in report.checks if check.name == "evaluation taxonomy valid")
    assert taxonomy_check.ok is False
    assert any("required_count" in detail for detail in taxonomy_check.details)


def test_m0_gate_revises_when_registered_sources_are_missing(tmp_path: Path) -> None:
    manifest = tmp_path / "architecture" / "manifest.json"
    taxonomy = tmp_path / "taxonomy.yaml"
    write_minimal_taxonomy(taxonomy)
    archetypes = ["faq", "legal", "policy_sop", "table_pdf", "technical_markdown"] * 5
    docs = [document_stub(f"doc_{index:02d}", f"Doc {index:02d}", archetype, f"missing_{index:02d}.md") for index, archetype in enumerate(archetypes, start=1)]
    for doc in docs:
        doc["status"] = "accepted"
    write_manifest_template(manifest, docs)

    report = run_m0_gate(manifest, taxonomy)

    assert report.decision == "revise"
    corpus_check = next(check for check in report.checks if check.name == "architecture corpus registered")
    assert corpus_check.ok is False
    assert any("source_uri does not exist locally" in detail for detail in corpus_check.details)


def test_m1_gate_goes_for_synthetic_fallback_parser(tmp_path: Path) -> None:
    manifest = tmp_path / "architecture" / "manifest.json"
    write_synthetic_architecture_corpus(manifest)
    report = run_m1_gate(manifest, "fallback")
    assert report.decision == "go"
    assert all(check.ok for check in report.checks)


def test_m1_gate_cli_writes_report(tmp_path: Path) -> None:
    manifest = tmp_path / "architecture" / "manifest.json"
    out = tmp_path / "reports" / "m1.json"
    write_synthetic_architecture_corpus(manifest)
    assert main(["gates", "m1", "--manifest", str(manifest), "--parser", "fallback", "--out", str(out)]) == 0
    assert out.exists()


def test_m2_gate_goes_for_synthetic_eval(tmp_path: Path) -> None:
    db, eval_file = synthetic_index_and_eval(tmp_path)
    report = run_m2_gate(db, eval_file)
    assert report.decision == "go"


def test_m2_gate_stops_when_eval_has_no_examples(tmp_path: Path) -> None:
    db, _ = synthetic_index_and_eval(tmp_path)
    empty_eval = tmp_path / "empty.jsonl"
    empty_eval.write_text("", encoding="utf-8")

    report = run_m2_gate(db, empty_eval)

    assert report.decision == "stop"


def test_m2_gate_uses_k10_and_k20_thresholds_separately(tmp_path: Path, monkeypatch) -> None:
    db, eval_file = synthetic_index_and_eval(tmp_path)
    seen_k = []

    def fake_run_eval(store, examples, k=10):
        seen_k.append(k)
        recall = {"single_unit_factual": 1.0, "mixed_vi_en": 1.0, "multihop_single_doc": 1.0}
        return EvalResult(
            total=1,
            retrieval_total=1,
            recall_at_k=1.0,
            recall_by_category=recall,
            no_answer_precision=1.0,
            no_answer_recall=1.0,
            p50_search_latency_ms=0.0,
            p95_search_latency_ms=0.0,
            p50_answer_latency_ms=0.0,
            p95_answer_latency_ms=0.0,
            avg_tool_calls=0.0,
            p95_tool_calls=0.0,
            avg_estimated_cost=0.0,
            p95_estimated_cost=0.0,
            answer_total=1,
            answer_correctness=1.0,
            citation_exactness=1.0,
            hallucinated_citation_count=0,
            tool_argument_error_count=0,
            tool_argument_error_rate=0.0,
            tool_limit_error_count=0,
            tool_limit_error_rate=0.0,
            failures=[],
        )

    monkeypatch.setattr(gates_module, "run_eval", fake_run_eval)

    report = gates_module.run_m2_gate(db, eval_file)

    assert report.decision == "go"
    assert seen_k == [10, 20]


def test_m3_gate_goes_for_synthetic_eval(tmp_path: Path) -> None:
    db, eval_file = synthetic_index_and_eval(tmp_path)
    report = run_m3_gate(db, eval_file)
    assert report.decision == "go"


def test_m3_gate_uses_tool_limit_error_rate_for_infinite_loop_check(tmp_path: Path, monkeypatch) -> None:
    db, eval_file = synthetic_index_and_eval(tmp_path)

    def fake_run_eval(store, examples, k=10):
        return EvalResult(
            total=1,
            retrieval_total=1,
            recall_at_k=1.0,
            recall_by_category={},
            no_answer_precision=1.0,
            no_answer_recall=1.0,
            p50_search_latency_ms=0.0,
            p95_search_latency_ms=0.0,
            p50_answer_latency_ms=0.0,
            p95_answer_latency_ms=0.0,
            avg_tool_calls=1.0,
            p95_tool_calls=1.0,
            avg_estimated_cost=0.0,
            p95_estimated_cost=0.0,
            answer_total=1,
            answer_correctness=1.0,
            citation_exactness=1.0,
            hallucinated_citation_count=0,
            tool_argument_error_count=0,
            tool_argument_error_rate=0.0,
            tool_limit_error_count=1,
            tool_limit_error_rate=1.0,
            failures=[{"question": "Q?", "type": "tool_limit_error"}],
        )

    monkeypatch.setattr(gates_module, "run_eval", fake_run_eval)

    report = gates_module.run_m3_gate(db, eval_file)

    assert report.decision == "revise"
    loop_check = next(check for check in report.checks if check.name == "infinite loop rate = 0")
    assert loop_check.ok is False
    assert loop_check.evidence == "1.000"


def test_m4_gate_goes_for_synthetic_eval(tmp_path: Path) -> None:
    db, eval_file = synthetic_index_and_eval(tmp_path)
    report = run_m4_gate(db, eval_file)
    assert report.decision == "go"


def test_m5_gate_goes_for_synthetic_eval(tmp_path: Path) -> None:
    db, eval_file = synthetic_index_and_eval(tmp_path)
    report = run_m5_gate(db, eval_file)
    assert report.decision == "go"


def test_m5_gate_stops_when_baseline_has_no_examples(tmp_path: Path) -> None:
    db, _ = synthetic_index_and_eval(tmp_path)
    empty_eval = tmp_path / "empty.jsonl"
    empty_eval.write_text("", encoding="utf-8")

    report = run_m5_gate(db, empty_eval)

    assert report.decision == "stop"


def test_baseline_comparison_report_can_explain_gap(tmp_path: Path) -> None:
    db, eval_file = synthetic_index_and_eval(tmp_path)
    store = GroundedStore(db)
    try:
        examples = json.loads('{"question":"Quy định không tồn tại?","category":"single_unit_factual","expected_text_contains":["không có"]}'),
        sparse = run_eval(store, list(examples), k=10)
        baseline = run_thin_rag_baseline(store, list(examples), top_k=10)
    finally:
        store.close()
    comparison = compare_sparse_to_baseline(sparse, baseline)
    out = tmp_path / "m5.md"

    write_baseline_comparison_report(comparison, out)
    text = out.read_text(encoding="utf-8")

    assert "# M5 Baseline Comparison" in text
    assert "Sparse/baseline ratio" in text
    assert baseline_comparison_markdown(comparison) == text


def test_baseline_report_cli_writes_markdown(tmp_path: Path) -> None:
    db, eval_file = synthetic_index_and_eval(tmp_path)
    out = tmp_path / "m5_baseline.md"

    assert main(["--db", str(db), "baselines", "report", "--eval", str(eval_file), "--out", str(out)]) == 0
    assert out.exists()
    assert "M5 Baseline Comparison" in out.read_text(encoding="utf-8")


def test_m6_gate_goes_for_synthetic_eval(tmp_path: Path) -> None:
    db, eval_file = synthetic_index_and_eval(tmp_path)
    report = run_m6_gate(db, eval_file, eval_file)
    assert report.decision == "go"


def test_release_gate_goes_for_synthetic_full_path(tmp_path: Path) -> None:
    manifest, db, eval_file = synthetic_manifest_index_and_eval(tmp_path)
    legal_pack, shadow_pack = synthetic_release_packs(tmp_path)
    pyproject, readme = synthetic_license_files(tmp_path)
    report = run_release_gate(
        manifest,
        db,
        eval_file,
        eval_file,
        legal_pack_path=legal_pack,
        shadow_pack_path=shadow_pack,
        pyproject_path=pyproject,
        readme_path=readme,
    )
    assert report.decision == "go"


def test_release_gate_accepts_named_deployment_risk_owners(tmp_path: Path) -> None:
    manifest, db, eval_file = synthetic_manifest_index_and_eval(tmp_path)
    legal_pack, shadow_pack = synthetic_release_packs(tmp_path)
    pyproject, readme = synthetic_license_files(tmp_path)
    report = run_release_gate(
        manifest,
        db,
        eval_file,
        eval_file,
        legal_pack_path=legal_pack,
        shadow_pack_path=shadow_pack,
        pyproject_path=pyproject,
        readme_path=readme,
        strict_risk_owners=True,
    )

    assert report.decision == "go"
    owner_check = next(check for check in report.checks if "deployment owners" in check.name)
    assert owner_check.ok is True


def test_release_gate_revises_when_registered_pack_sources_are_missing(tmp_path: Path) -> None:
    manifest, db, eval_file = synthetic_manifest_index_and_eval(tmp_path)
    legal_pack, shadow_pack = synthetic_release_packs(tmp_path)
    pyproject, readme = synthetic_license_files(tmp_path)
    (legal_pack.parent / "legal_01.md").unlink()

    report = run_release_gate(
        manifest,
        db,
        eval_file,
        eval_file,
        legal_pack_path=legal_pack,
        shadow_pack_path=shadow_pack,
        pyproject_path=pyproject,
        readme_path=readme,
    )

    assert report.decision == "revise"
    legal_check = next(check for check in report.checks if check.name == "legal regression pack registered")
    assert legal_check.ok is False
    assert any("source_uri does not exist locally" in detail for detail in legal_check.details)


def test_release_gate_revises_when_license_is_not_selected(tmp_path: Path) -> None:
    manifest, db, eval_file = synthetic_manifest_index_and_eval(tmp_path)
    legal_pack, shadow_pack = synthetic_release_packs(tmp_path)
    pyproject = tmp_path / "pyproject_tbd.toml"
    readme = tmp_path / "README_TBD.md"
    pyproject.write_text('license = {text = "TBD"}\n', encoding="utf-8")
    readme.write_text("# Demo\n\n## License\n\nTBD\n", encoding="utf-8")

    report = run_release_gate(
        manifest,
        db,
        eval_file,
        eval_file,
        legal_pack_path=legal_pack,
        shadow_pack_path=shadow_pack,
        pyproject_path=pyproject,
        readme_path=readme,
    )

    assert report.decision == "revise"
    license_gate = next(check for check in report.checks if check.name == "project license selected")
    assert license_gate.ok is False
    assert any("license is not selected" in detail for detail in license_gate.details)


def test_provenance_version_errors_flags_overlapping_active_versions(tmp_path: Path) -> None:
    store = GroundedStore(tmp_path / "grounded.db")
    store.init_schema()
    for doc_id, effective_from, effective_to in [
        ("policy_v1", "2026-01-01", "2026-02-15"),
        ("policy_v2", "2026-02-01", ""),
    ]:
        source = tmp_path / f"{doc_id}.md"
        source.write_text("# Policy\n\n## Rule\n\nText.\n", encoding="utf-8")
        manifest = tmp_path / f"{doc_id}.json"
        manifest.write_text(
            json.dumps(
                {
                    "documents": [
                        {
                            "doc_id": doc_id,
                            "doc_family_id": "policy_family",
                            "title": doc_id,
                            "archetype": "policy_sop",
                            "source_uri": source.name,
                            "format": "md",
                            "language": "vi",
                            "provenance_owner": "owner",
                            "license": "internal",
                            "status": "accepted",
                            "version_label": doc_id,
                            "effective_from": effective_from,
                            "effective_to": effective_to,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        store.ingest_manifest(manifest)

    errors = provenance_version_errors(store)

    assert any("overlapping active versions" in error for error in errors)


def synthetic_index_and_eval(tmp_path: Path):
    _, db, eval_file = synthetic_manifest_index_and_eval(tmp_path)
    return db, eval_file


def synthetic_manifest_index_and_eval(tmp_path: Path):
    manifest = tmp_path / "architecture" / "manifest.json"
    db = tmp_path / "grounded.db"
    eval_file = tmp_path / "eval.jsonl"
    write_synthetic_architecture_corpus(manifest)
    store = GroundedStore(db)
    store.init_schema()
    store.ingest_manifest(manifest)
    store.close()
    eval_file.write_text(
        '\n'.join(
            [
                '{"question":"HRM dùng để làm gì?","category":"mixed_vi_en","expected_text_contains":["hrm dùng để tạo yêu cầu"]}',
                '{"question":"Ai phê duyệt cuối cùng?","category":"single_unit_factual","expected_text_contains":["bộ phận nhân sự phê duyệt cuối cùng"],"expected_answer_contains":["bộ phận nhân sự phê duyệt cuối cùng"]}',
                '{"question":"Ai kiểm tra thông tin và ai phê duyệt cuối cùng?","category":"multihop_single_doc","expected_text_contains":["quản lý trực tiếp kiểm tra","bộ phận nhân sự phê duyệt"],"expected_answer_contains":["quản lý trực tiếp kiểm tra","bộ phận nhân sự phê duyệt"]}',
                '{"question":"Quy định mua cổ phiếu cá nhân là gì?","category":"no_answer","insufficient_evidence":true}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest, db, eval_file


def synthetic_license_files(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    readme = tmp_path / "README.md"
    pyproject.write_text('license = {text = "MIT"}\n', encoding="utf-8")
    readme.write_text("# Demo\n\n## License\n\nMIT\n", encoding="utf-8")
    return pyproject, readme


def synthetic_release_packs(tmp_path: Path):
    legal_dir = tmp_path / "legal"
    shadow_dir = tmp_path / "shadow"
    legal_docs = []
    for index in range(1, 13):
        source = legal_dir / f"legal_{index:02d}.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"# Legal {index}\n\n## Điều 1\n\nQuy định pháp lý {index}.\n", encoding="utf-8")
        stub = document_stub(f"legal_{index:02d}", f"Legal {index}", "legal", source.name)
        stub["status"] = "accepted"
        stub["coverage_tags"] = ["legal_citation", "cross_reference", "version_status"]
        legal_docs.append(stub)
    legal_manifest = legal_dir / "manifest.json"
    write_manifest_template(legal_manifest, legal_docs)

    shadow_source = shadow_dir / "shadow.md"
    shadow_source.parent.mkdir(parents=True, exist_ok=True)
    shadow_source.write_text("# Shadow\n\n## FAQ\n\nHỏi: Shadow?\n\nĐáp: Có.\n", encoding="utf-8")
    shadow_stub = document_stub("shadow_01", "Shadow", "faq", "shadow.md")
    shadow_stub["status"] = "shadow"
    shadow_stub["coverage_tags"] = ["representative_deployment", "governed_provenance"]
    shadow_manifest = shadow_dir / "manifest.json"
    shadow_manifest.write_text(
        json.dumps({"version": 1, "name": "production_shadow", "documents": [shadow_stub]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return legal_manifest, shadow_manifest
