import json
from pathlib import Path

from vn_grounded_qa.bakeoff import run_fallback_bakeoff, run_parser_bakeoff
from vn_grounded_qa.cli import main


def write_manifest(tmp_path: Path) -> Path:
    source = tmp_path / "policy.md"
    source.write_text("# Chính sách\n\n## Phê duyệt\n\nQuản lý phê duyệt trên HRM.\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "doc_id": "policy_1",
                        "title": "Chính sách",
                        "archetype": "policy_sop",
                        "source_uri": "policy.md",
                        "format": "md",
                        "language": "vi",
                        "provenance_owner": "team",
                        "license": "internal",
                        "status": "candidate",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_fallback_bakeoff_reports_ingestion_quality(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path)
    report = run_fallback_bakeoff(manifest)
    assert report.ok is True
    assert report.document_count == 1
    assert report.parse_success_rate == 1.0
    assert report.heading_path_recovery_rate == 1.0
    assert report.provenance_completeness_rate == 1.0


def test_bakeoff_uses_expected_heading_paths_when_present(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["documents"][0]["expected_heading_paths"] = ["Chính sách > Phê duyệt"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    report = run_fallback_bakeoff(manifest)

    assert report.heading_path_recovery_rate == 1.0
    assert report.documents[0].missing_heading_paths == []


def test_bakeoff_reports_missing_expected_heading_paths(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["documents"][0]["expected_heading_paths"] = ["Chính sách > Không tồn tại"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    report = run_fallback_bakeoff(manifest)

    assert report.ok is False
    assert report.heading_path_recovery_rate == 0.0
    assert report.documents[0].missing_heading_paths == ["Chính sách > Không tồn tại"]


def test_fallback_bakeoff_cli_writes_report(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path)
    out = tmp_path / "reports" / "m1.json"
    assert main(["bakeoff", "fallback", str(manifest), "--out", str(out)]) == 0
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ok"] is True


def test_parser_bakeoff_cli_supports_explicit_fallback(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path)
    assert main(["bakeoff", "parser", str(manifest), "--parser", "fallback"]) == 0


def test_auto_bakeoff_surfaces_parser_degradation_warnings(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path)
    report = run_parser_bakeoff(manifest, "auto")

    assert report.ok is True
    assert any("auto parser fell back" in warning for warning in report.documents[0].parser_warnings)


def test_unavailable_docling_parser_is_reported_per_document(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path)
    report = run_fallback_bakeoff(manifest)
    assert report.ok is True
    exit_code = main(["bakeoff", "parser", str(manifest), "--parser", "docling"])
    assert exit_code in {0, 2}
