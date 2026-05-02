from pathlib import Path

from vn_grounded_qa.cli import main
from vn_grounded_qa.eval import load_eval_taxonomy, validate_eval_set, validate_eval_taxonomy, write_synthetic_mvp_eval


def test_synthetic_mvp_eval_validates_strictly(tmp_path: Path) -> None:
    path = tmp_path / "mvp.jsonl"
    write_synthetic_mvp_eval(path)
    result = validate_eval_set(path, strict=True)
    assert result.ok is True
    assert result.total == 80
    assert result.category_counts["single_unit_factual"] == 20
    assert result.category_counts["no_answer"] == 10


def test_evalset_seed_cli(tmp_path: Path) -> None:
    path = tmp_path / "mvp.jsonl"
    assert main(["evalset", "seed-synthetic", str(path)]) == 0
    assert path.exists()


def test_evalset_strict_rejects_wrong_counts(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"question":"Q?","category":"single_unit_factual","expected_text_contains":["x"],"source":"human"}\n', encoding="utf-8")
    result = validate_eval_set(path, strict=True)
    assert result.ok is False
    assert any("80 questions" in error for error in result.errors)


def test_evalset_strict_requires_non_auto_rows_to_be_human_or_rewritten(tmp_path: Path) -> None:
    taxonomy = tmp_path / "taxonomy.yaml"
    taxonomy.write_text(
        """version: 1
categories:
  - id: custom_category
    required_count: 1
rules:
  total_required_questions: 1
  max_auto_generated_fraction: 0.4
""",
        encoding="utf-8",
    )
    path = tmp_path / "custom.jsonl"
    path.write_text('{"question":"Q?","category":"custom_category","expected_text_contains":["A"],"auto_generated":false}\n', encoding="utf-8")

    result = validate_eval_set(path, strict=True, taxonomy_path=taxonomy)

    assert result.ok is False
    assert any("source to human or rewritten" in error for error in result.errors)


def test_evalset_validation_accepts_taxonomy_gold_fields(tmp_path: Path) -> None:
    path = tmp_path / "taxonomy_fields.jsonl"
    path.write_text(
        '{"question":"Q?","category":"multidoc_synthesis","expected_component_unit_ids":["u1"],"expected_answer_points":["A"],"expected_citation_unit_ids":["u1"]}\n',
        encoding="utf-8",
    )

    result = validate_eval_set(path, strict=False)

    assert result.ok is True


def test_evalset_validation_accepts_version_gold_fields(tmp_path: Path) -> None:
    path = tmp_path / "version_fields.jsonl"
    path.write_text(
        '{"question":"Q?","category":"version_status_exception","as_of":"2026-02-01","expected_doc_id":"policy_v2"}\n',
        encoding="utf-8",
    )

    result = validate_eval_set(path, strict=False)

    assert result.ok is True


def test_evalset_validation_requires_version_status_gold_pair(tmp_path: Path) -> None:
    path = tmp_path / "bad_version_fields.jsonl"
    path.write_text(
        '{"question":"Q?","category":"version_status_exception","expected_text_contains":["A"]}\n',
        encoding="utf-8",
    )

    result = validate_eval_set(path, strict=False)

    assert result.ok is False
    assert any("as_of and expected_doc_id" in error for error in result.errors)


def test_evalset_validation_accepts_expected_doc_ids(tmp_path: Path) -> None:
    path = tmp_path / "doc_ids.jsonl"
    path.write_text(
        '{"question":"Q?","category":"multidoc_synthesis","expected_doc_ids":["doc_a","doc_b"]}\n',
        encoding="utf-8",
    )

    result = validate_eval_set(path, strict=False)

    assert result.ok is True


def test_evalset_validation_accepts_remaining_taxonomy_gold_fields(tmp_path: Path) -> None:
    path = tmp_path / "remaining_fields.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"question":"Q1?","category":"mixed_vi_en","aliases_or_terms":["HRM"]}',
                '{"question":"Q2?","category":"table_list_structure","expected_row_or_item":"Hạn mức: 5000000 VND"}',
                '{"question":"Q3?","category":"no_answer","insufficient_evidence":true,"disallowed_answer_points":["bịa"]}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = validate_eval_set(path, strict=False)

    assert result.ok is True


def test_evalset_validation_enforces_no_answer_shape(tmp_path: Path) -> None:
    path = tmp_path / "bad_no_answer.jsonl"
    path.write_text(
        '{"question":"Q?","category":"no_answer","expected_answer_points":["A"]}\n',
        encoding="utf-8",
    )

    result = validate_eval_set(path, strict=False)

    assert result.ok is False
    assert any("insufficient_evidence=true" in error for error in result.errors)
    assert any("must not provide expected answer content" in error for error in result.errors)


def test_evalset_validation_uses_taxonomy_file_counts(tmp_path: Path) -> None:
    taxonomy = tmp_path / "taxonomy.yaml"
    taxonomy.write_text(
        """version: 1
categories:
  - id: custom_category
    required_count: 2
rules:
  total_required_questions: 2
  max_auto_generated_fraction: 0.5
""",
        encoding="utf-8",
    )
    path = tmp_path / "custom.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"question":"Q1?","category":"custom_category","expected_text_contains":["A"],"auto_generated":true}',
                '{"question":"Q2?","category":"custom_category","expected_text_contains":["B"],"auto_generated":false,"source":"human"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = validate_eval_set(path, strict=True, taxonomy_path=taxonomy)

    assert result.ok is True
    assert load_eval_taxonomy(taxonomy).category_counts == {"custom_category": 2}


def test_evalset_cli_accepts_explicit_taxonomy(tmp_path: Path) -> None:
    taxonomy = tmp_path / "taxonomy.yaml"
    taxonomy.write_text(
        """version: 1
categories:
  - id: custom_category
    required_count: 1
rules:
  total_required_questions: 1
  max_auto_generated_fraction: 1.0
""",
        encoding="utf-8",
    )
    path = tmp_path / "custom.jsonl"
    path.write_text('{"question":"Q?","category":"custom_category","expected_text_contains":["A"],"auto_generated":true}\n', encoding="utf-8")

    assert main(["evalset", "validate", str(path), "--taxonomy", str(taxonomy)]) == 0


def test_taxonomy_validation_rejects_total_mismatch(tmp_path: Path) -> None:
    taxonomy = tmp_path / "taxonomy.yaml"
    taxonomy.write_text(
        """version: 1
categories:
  - id: custom_category
    required_count: 2
rules:
  total_required_questions: 3
  max_auto_generated_fraction: 0.4
""",
        encoding="utf-8",
    )

    errors = validate_eval_taxonomy(taxonomy)

    assert any("total_required_questions" in error for error in errors)
