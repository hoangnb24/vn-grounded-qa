import os

from vn_grounded_qa.normalize import segment_vi


def test_segment_vi_fallback_preserves_identifiers(monkeypatch) -> None:
    monkeypatch.delenv("VN_GROUNDED_QA_SEGMENTER", raising=False)
    assert "/search_units" in segment_vi("Endpoint /search_units dùng cho HRM")


def test_segment_vi_external_command(monkeypatch, tmp_path) -> None:
    script = tmp_path / "segmenter.py"
    script.write_text(
        "import sys\ntext=sys.stdin.read()\nprint(text.replace('nhân sự', 'nhân_sự'))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VN_GROUNDED_QA_SEGMENTER", f"python3 {script}")
    assert "nhân_sự" in segment_vi("Quản lý nhân sự")


def test_segment_vi_external_command_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("VN_GROUNDED_QA_SEGMENTER", "/missing/segmenter")
    assert "nhân" in segment_vi("Quản lý nhân sự")
