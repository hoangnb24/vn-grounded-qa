import json
from pathlib import Path

from vn_grounded_qa.cli import main
from vn_grounded_qa.corpus import document_stub, write_manifest_template, write_synthetic_architecture_corpus, write_synthetic_pack
from vn_grounded_qa.eval import write_synthetic_mvp_eval
from vn_grounded_qa.readiness import run_governed_readiness


def test_governed_readiness_reports_current_state() -> None:
    report = run_governed_readiness(
        Path("corpus/architecture/manifest.json"),
        Path("eval/synthetic_mvp_seed.jsonl"),
        strict_risk_owners=True,
    )

    assert report.ok is True
    assert report.blockers == []


def test_governed_readiness_passes_for_complete_synthetic_inputs(tmp_path: Path) -> None:
    architecture = tmp_path / "architecture" / "manifest.json"
    eval_path = tmp_path / "eval" / "mvp80.jsonl"
    legal_pack = tmp_path / "legal" / "manifest.json"
    shadow_pack = tmp_path / "shadow" / "manifest.json"
    pyproject = tmp_path / "pyproject.toml"
    readme = tmp_path / "README.md"
    out = tmp_path / "reports" / "readiness.json"

    write_synthetic_architecture_corpus(architecture)
    write_synthetic_mvp_eval(eval_path)
    write_synthetic_pack(legal_pack, "legal_regression")
    write_synthetic_pack(shadow_pack, "production_shadow")
    write_license_files(pyproject, readme)

    rc = main(
        [
            "readiness",
            "governed",
            "--manifest",
            str(architecture),
            "--eval",
            str(eval_path),
            "--legal-pack",
            str(legal_pack),
            "--shadow-pack",
            str(shadow_pack),
            "--pyproject",
            str(pyproject),
            "--readme",
            str(readme),
            "--out",
            str(out),
        ]
    )

    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["blockers"] == []


def test_governed_readiness_blocks_missing_local_sources(tmp_path: Path) -> None:
    architecture = tmp_path / "architecture" / "manifest.json"
    eval_path = tmp_path / "eval" / "mvp80.jsonl"
    legal_pack = tmp_path / "legal" / "manifest.json"
    shadow_pack = tmp_path / "shadow" / "manifest.json"

    write_synthetic_architecture_corpus(architecture)
    write_synthetic_mvp_eval(eval_path)
    write_synthetic_pack(legal_pack, "legal_regression")
    write_synthetic_pack(shadow_pack, "production_shadow")

    docs = [document_stub(f"doc_{index:02d}", f"Doc {index:02d}", archetype, f"missing_{index:02d}.md") for index, archetype in enumerate(["faq", "legal", "policy_sop", "table_pdf", "technical_markdown"] * 5, start=1)]
    for doc in docs:
        doc["status"] = "accepted"
    write_manifest_template(architecture, docs)

    report = run_governed_readiness(architecture, eval_path, legal_pack_path=legal_pack, shadow_pack_path=shadow_pack)

    assert report.ok is False
    item = next(item for item in report.items if item.name == "architecture corpus ready")
    assert item.ok is False
    assert any("source_uri does not exist locally" in detail for detail in item.details)


def test_governed_readiness_blocks_unselected_license(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    readme = tmp_path / "README.md"
    pyproject.write_text('license = {text = "TBD"}\n', encoding="utf-8")
    readme.write_text("# Demo\n\n## License\n\nTBD\n", encoding="utf-8")

    report = run_governed_readiness(
        Path("corpus/architecture/manifest.json"),
        Path("eval/synthetic_mvp_seed.jsonl"),
        pyproject_path=pyproject,
        readme_path=readme,
    )

    item = next(item for item in report.items if item.name == "project license selected")
    assert item.ok is False
    assert any("license is not selected" in detail for detail in item.details)


def write_license_files(pyproject: Path, readme: Path) -> None:
    pyproject.write_text('license = {text = "MIT"}\n', encoding="utf-8")
    readme.write_text("# Demo\n\n## License\n\nMIT\n", encoding="utf-8")
