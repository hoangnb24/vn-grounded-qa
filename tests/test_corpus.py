import json
from pathlib import Path

from vn_grounded_qa.corpus import validate_architecture_manifest, write_synthetic_architecture_corpus
from vn_grounded_qa.cli import main
from vn_grounded_qa.store import GroundedStore


def test_relaxed_manifest_validation_accepts_schema(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Chính sách\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "architecture_corpus_v1",
                "documents": [
                    {
                        "doc_id": "doc_1",
                        "title": "Chính sách",
                        "doc_type": "policy",
                        "archetype": "policy_sop",
                        "source_uri": "doc.md",
                        "format": "md",
                        "language": "vi",
                        "provenance_owner": "team",
                        "license": "internal",
                        "status": "candidate",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = validate_architecture_manifest(manifest, strict_m0=False)
    assert result.ok is True
    assert result.document_count == 1
    assert result.archetype_counts == {"policy_sop": 1}


def test_strict_m0_manifest_requires_size_and_all_archetypes(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"documents": []}), encoding="utf-8")
    result = validate_architecture_manifest(manifest, strict_m0=True)
    assert result.ok is False
    assert any("24-36" in error for error in result.errors)
    assert any("missing archetypes" in error for error in result.errors)


def test_manifest_validation_rejects_inverted_effective_window(tmp_path: Path) -> None:
    source = tmp_path / "policy.md"
    source.write_text("# Policy\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "doc_id": "policy_v1",
                        "title": "Policy",
                        "doc_type": "policy",
                        "archetype": "policy_sop",
                        "source_uri": "policy.md",
                        "format": "md",
                        "language": "vi",
                        "provenance_owner": "owner",
                        "license": "internal",
                        "status": "accepted",
                        "effective_from": "2026-02-01",
                        "effective_to": "2026-01-01",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = validate_architecture_manifest(manifest, strict_m0=False)

    assert result.ok is False
    assert any("effective_from" in error for error in result.errors)


def test_manifest_validation_accepts_documented_active_status(tmp_path: Path) -> None:
    source = tmp_path / "policy.md"
    source.write_text("# Policy\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "doc_id": "policy_active",
                        "title": "Policy",
                        "doc_type": "policy",
                        "archetype": "policy_sop",
                        "source_uri": "policy.md",
                        "format": "md",
                        "language": "vi",
                        "provenance_owner": "owner",
                        "license": "internal",
                        "status": "active",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = validate_architecture_manifest(manifest, strict_m0=False)

    assert result.ok is True


def test_corpus_template_cli(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    assert main(["corpus", "template", str(manifest)]) == 0
    assert manifest.exists()
    result = validate_architecture_manifest(manifest, strict_m0=False)
    assert result.ok is True


def test_ingest_manifest_preserves_manifest_metadata(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Chính sách HRM\n\n## Điều kiện\n\nNhân viên dùng HRM để gửi yêu cầu.\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "doc_id": "policy_hrm",
                        "doc_family_id": "policy_hrm_family",
                        "title": "Chính sách HRM",
                        "doc_type": "policy",
                        "archetype": "policy_sop",
                        "source_uri": "doc.md",
                        "format": "md",
                        "language": "vi",
                        "provenance_owner": "team",
                        "license": "internal",
                        "status": "accepted",
                        "version_label": "v1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    store = GroundedStore(tmp_path / "qa.db")
    store.init_schema()
    assert store.ingest_manifest(manifest) == 1
    doc = store.get_document("policy_hrm")
    assert doc is not None
    assert doc["doc_family_id"] == "policy_hrm_family"
    assert doc["doc_type"] == "policy"
    assert doc["status"] == "active"
    assert store.search_units("HRM", top_k=1)


def test_ingest_manifest_can_replace_existing_units_and_fts_rows(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Chính sách HRM\n\n## Điều kiện\n\nNhân viên dùng HRM.\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "doc_id": "policy_hrm",
                        "title": "Chính sách HRM",
                        "archetype": "policy_sop",
                        "source_uri": "doc.md",
                        "format": "md",
                        "language": "vi",
                        "provenance_owner": "team",
                        "license": "internal",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    store = GroundedStore(tmp_path / "qa.db")
    store.init_schema()

    assert store.ingest_manifest(manifest) == 1
    source.write_text("# Chính sách HRM\n\n## Điều kiện\n\nNhân viên dùng HRM và endpoint /search_units.\n", encoding="utf-8")
    assert store.ingest_manifest(manifest) == 1

    hits = store.search_units("/search_units", top_k=5)
    assert len(hits) == 1
    assert "/search_units" in hits[0].raw_text


def test_synthetic_architecture_corpus_satisfies_strict_m0_shape(tmp_path: Path) -> None:
    manifest = tmp_path / "architecture" / "manifest.json"
    write_synthetic_architecture_corpus(manifest)
    result = validate_architecture_manifest(manifest, strict_m0=True)
    assert result.ok is True
    assert result.document_count == 25
    assert set(result.archetype_counts) == {"faq", "legal", "policy_sop", "table_pdf", "technical_markdown"}
