import json
from pathlib import Path

from vn_grounded_qa.cli import main
from vn_grounded_qa.corpus import validate_pack_manifest, write_pack_template, write_synthetic_pack


def test_pack_template_cli(tmp_path: Path) -> None:
    manifest = tmp_path / "legal" / "manifest.json"
    assert main(["corpus", "pack-template", str(manifest), "--type", "legal_regression"]) == 0
    assert manifest.exists()


def test_legal_regression_pack_requires_12_to_20_legal_docs(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    write_pack_template(manifest, "legal_regression")
    result = validate_pack_manifest(manifest, "legal_regression")
    assert result.ok is False
    assert any("12-20" in error for error in result.errors)


def test_legal_regression_pack_requires_documented_coverage_tags(tmp_path: Path) -> None:
    legal_docs = []
    for index in range(1, 13):
        source = tmp_path / f"legal_{index:02d}.md"
        source.write_text(f"# Legal {index}\n", encoding="utf-8")
        legal_docs.append(
            {
                "doc_id": f"legal_{index:02d}",
                "title": f"Legal {index}",
                "doc_type": "legal",
                "archetype": "legal",
                "source_uri": source.name,
                "format": "md",
                "language": "vi",
                "provenance_owner": "team",
                "license": "internal",
                "status": "accepted",
                "coverage_tags": ["legal_citation"],
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"documents": legal_docs}), encoding="utf-8")

    result = validate_pack_manifest(manifest, "legal_regression")

    assert result.ok is False
    assert any("cross_reference" in error and "version_status" in error for error in result.errors)


def test_production_shadow_pack_requires_shadow_status(tmp_path: Path) -> None:
    source = tmp_path / "shadow.md"
    source.write_text("# Shadow\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "doc_id": "shadow_1",
                        "title": "Shadow",
                        "doc_type": "faq",
                        "archetype": "faq",
                        "source_uri": "shadow.md",
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
    result = validate_pack_manifest(manifest, "production_shadow")
    assert result.ok is False
    assert any("status=shadow" in error for error in result.errors)


def test_production_shadow_pack_requires_documented_coverage_tags(tmp_path: Path) -> None:
    source = tmp_path / "shadow.md"
    source.write_text("# Shadow\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "doc_id": "shadow_1",
                        "title": "Shadow",
                        "doc_type": "faq",
                        "archetype": "faq",
                        "source_uri": "shadow.md",
                        "format": "md",
                        "language": "vi",
                        "provenance_owner": "team",
                        "license": "internal",
                        "status": "shadow",
                        "coverage_tags": ["representative_deployment"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = validate_pack_manifest(manifest, "production_shadow")

    assert result.ok is False
    assert any("governed_provenance" in error for error in result.errors)


def test_synthetic_legal_regression_pack_validates(tmp_path: Path) -> None:
    manifest = tmp_path / "legal" / "manifest.json"
    write_synthetic_pack(manifest, "legal_regression")
    result = validate_pack_manifest(manifest, "legal_regression")
    assert result.ok is True
    assert result.document_count == 12


def test_synthetic_shadow_pack_validates_via_cli(tmp_path: Path) -> None:
    manifest = tmp_path / "shadow" / "manifest.json"
    assert main(["corpus", "pack-seed-synthetic", str(manifest), "--type", "production_shadow"]) == 0
    result = validate_pack_manifest(manifest, "production_shadow")
    assert result.ok is True
