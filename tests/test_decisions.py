import json
from pathlib import Path

from vn_grounded_qa.cli import main
from vn_grounded_qa.decisions import build_decision_report, classify_failure_layer, write_decision_report


def test_build_decision_report_classifies_failed_gate_checks(tmp_path: Path) -> None:
    gate = tmp_path / "m0_gate.json"
    gate.write_text(
        json.dumps(
            {
                "milestone": "M0",
                "decision": "revise",
                "checks": [
                    {"name": "evaluation taxonomy present", "ok": True, "evidence": "eval/taxonomy.yaml"},
                    {
                        "name": "architecture corpus registered",
                        "ok": False,
                        "evidence": "corpus/architecture/manifest.json",
                        "details": ["M0 architecture corpus must contain 24-36 documents; found 2"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    report = build_decision_report(gate)

    assert report.decision == "revise"
    assert report.passed_checks == ["evaluation taxonomy present"]
    assert report.failed_reviews[0].layer == "ingestion"
    assert "corpus registration" in report.failed_reviews[0].next_action


def test_write_decision_report_outputs_markdown(tmp_path: Path) -> None:
    gate = tmp_path / "release_gate.json"
    out = tmp_path / "release_decision.md"
    gate.write_text(
        json.dumps(
            {
                "milestone": "Release",
                "decision": "revise",
                "checks": [
                    {"name": "citation hallucinations = 0", "ok": True, "evidence": "0"},
                    {
                        "name": "retrieval thresholds met",
                        "ok": False,
                        "evidence": "M2=revise",
                        "details": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    report = write_decision_report(gate, out)
    text = out.read_text(encoding="utf-8")

    assert report.decision == "revise"
    assert "# Release Decision Report" in text
    assert "- Layer: `retrieval`" in text
    assert "Do not label retrieval failures as prompt problems" in text


def test_decision_report_can_record_stop_reason(tmp_path: Path) -> None:
    gate = tmp_path / "m5_gate.json"
    gate.write_text(
        json.dumps({"milestone": "M5", "decision": "revise", "checks": []}),
        encoding="utf-8",
    )

    report = build_decision_report(gate, stop_reason="Baseline is not representative.")

    assert report.decision == "stop"
    assert report.stop_reason == "Baseline is not representative."


def test_decisions_report_cli_writes_file(tmp_path: Path) -> None:
    gate = tmp_path / "m1_gate.json"
    out = tmp_path / "m1_decision.md"
    gate.write_text(
        json.dumps({"milestone": "M1", "decision": "go", "checks": [{"name": "parse success >= 90%", "ok": True, "evidence": "1.000"}]}),
        encoding="utf-8",
    )

    assert main(["decisions", "report", str(gate), "--out", str(out)]) == 0
    assert out.exists()


def test_classify_failure_layer_prefers_governance_for_risks() -> None:
    assert classify_failure_layer("open risks documented with owners/mitigations") == "governance"
    assert classify_failure_layer("legal regression pack registered") == "governance"
    assert classify_failure_layer("shadow corpus registered") == "governance"
    assert classify_failure_layer("project license selected") == "governance"
    assert classify_failure_layer("parsing benchmarked for all archetypes") == "ingestion"
    assert classify_failure_layer("architecture corpus registered", ["M0 architecture corpus missing archetypes: faq, legal"]) == "ingestion"
