# Governed Inputs Runbook

This runbook is the execution checklist for validating the governed release
inputs. The checked-in corpus, eval set, legal regression pack, production
shadow pack, risk register, and license metadata satisfy the strict release
gate.

For Exa-assisted source discovery, see
`docs/GOVERNED_SOURCE_ACQUISITION.md`.

## Required Inputs

| Input | Target file | Required size | Required coverage |
|---|---|---:|---|
| Architecture corpus | `corpus/architecture/manifest.json` | 24-36 docs | legal, policy/SOP, technical Markdown, table-heavy PDF, FAQ |
| MVP eval set | `eval/synthetic_mvp_seed.jsonl` | 80 questions | all 7 taxonomy categories in `eval/taxonomy.yaml` |
| Legal regression pack | `corpus/legal-regression/manifest.json` | 12 docs | legal citation, cross-reference, version/status reasoning |
| Production shadow pack | `corpus/production-shadow/manifest.json` | 6 docs | representative deployment documents, governed provenance |
| Risk owners | `docs/RISK_REGISTER.md` | all open risks | named deployment owners and mitigations |
| Project license | `pyproject.toml`, `README.md` | selected license | non-`TBD` and matching package/readme values |

The 80-question eval set may contain at most 40 percent auto-generated
questions. The checked-in eval set contains zero auto-generated rows.

`vn-grounded-qa readiness governed` and the milestone/release gates are
intentionally stricter than the individual schema validators: local
`source_uri` warnings block readiness because parser, ingestion, and gate runs
cannot proceed without the files.

Project license placeholders block readiness. The package metadata and README
license section use MIT.

## Manifest Rules

Each document entry must include enough metadata for provenance and version
checks:

```json
{
  "doc_id": "stable_id",
  "source_uri": "relative/or/absolute/path",
  "title": "Human title",
  "doc_type": "policy",
  "archetype": "policy_sop",
  "language": "vi",
  "provenance_owner": "Named source owner",
  "license": "internal-approved",
  "version_label": "v1",
  "effective_from": "2026-01-01",
  "effective_to": "",
  "status": "active"
}
```

For parser bakeoff, add `expected_heading_paths` where a human can define the
correct outline:

```json
"expected_heading_paths": [
  "Quy trình phê duyệt > Phạm vi",
  "Quy trình phê duyệt > Các bước thực hiện"
]
```

For the legal regression pack, each manifest may distribute these
`coverage_tags` across documents, but the pack as a whole must include all
three:

```json
"coverage_tags": ["legal_citation", "cross_reference", "version_status"]
```

For the production shadow pack, the pack as a whole must include both shadow
coverage tags:

```json
"coverage_tags": ["representative_deployment", "governed_provenance"]
```

## Eval JSONL Rules

Each eval row should include the category, the question, and gold evidence. Use
the most specific gold fields available.

```json
{
  "id": "single_001",
  "category": "single_unit_factual",
  "question": "Nhân viên phải lưu bằng chứng ở đâu?",
  "expected_doc_ids": ["policy_expense_v1"],
  "expected_unit_ids": ["unit_policy_expense_v1_004"],
  "expected_citation_unit_ids": ["unit_policy_expense_v1_004"],
  "expected_answer_points": ["lưu bằng chứng trong HRM"],
  "source": "human"
}
```

For version/status questions, include both `as_of` and `expected_doc_id`.

For strict governed eval validation, every non-auto-generated row must include
`"source": "human"` or `"source": "rewritten"`.

For no-answer cases, set `insufficient_evidence` to `true` and do not provide
`expected_answer_contains` or `expected_answer_points`.

## Execution Order

1. Fill and validate the architecture corpus.

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus validate corpus/architecture/manifest.json
```

2. Run parser bakeoff for all available parsers.

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff parser corpus/architecture/manifest.json --parser auto --out reports/m1_auto_governed.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff parser corpus/architecture/manifest.json --parser fallback --out reports/m1_fallback_governed.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff parser corpus/architecture/manifest.json --parser docling --out reports/m1_docling_governed.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff parser corpus/architecture/manifest.json --parser marker --out reports/m1_marker_governed.json
```

3. Ingest the governed corpus into a fresh database.

```bash
GOVERNED_DB="governed.$(date +%Y%m%d%H%M%S).db"
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db "$GOVERNED_DB" init
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db "$GOVERNED_DB" ingest-manifest corpus/architecture/manifest.json
```

4. Validate the governed eval set.

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli evalset validate eval/synthetic_mvp_seed.jsonl
```

5. Validate legal and shadow packs.

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-validate corpus/legal-regression/manifest.json --type legal_regression
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-validate corpus/production-shadow/manifest.json --type production_shadow
```

6. Run M0-M6 gates on governed inputs.

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli readiness governed --manifest corpus/architecture/manifest.json --eval eval/synthetic_mvp_seed.jsonl --legal-pack corpus/legal-regression/manifest.json --shadow-pack corpus/production-shadow/manifest.json --strict-risk-owners --out reports/governed_readiness.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m0 --manifest corpus/architecture/manifest.json --out reports/m0_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m1 --manifest corpus/architecture/manifest.json --parser auto --out reports/m1_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m2 --db "$GOVERNED_DB" --eval eval/synthetic_mvp_seed.jsonl --out reports/m2_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m3 --db "$GOVERNED_DB" --eval eval/synthetic_mvp_seed.jsonl --out reports/m3_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m4 --db "$GOVERNED_DB" --eval eval/synthetic_mvp_seed.jsonl --out reports/m4_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m5 --db "$GOVERNED_DB" --eval eval/synthetic_mvp_seed.jsonl --out reports/m5_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m6 --db "$GOVERNED_DB" --base-eval eval/synthetic_mvp_seed.jsonl --scale-eval eval/synthetic_mvp_seed.jsonl --out reports/m6_gate.json
```

7. Run the controlled-release gate.

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates release --manifest corpus/architecture/manifest.json --db "$GOVERNED_DB" --eval eval/synthetic_mvp_seed.jsonl --scale-eval eval/synthetic_mvp_seed.jsonl --legal-pack corpus/legal-regression/manifest.json --shadow-pack corpus/production-shadow/manifest.json --strict-risk-owners --pyproject pyproject.toml --readme README.md --out reports/release_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli decisions report reports/release_gate.json --out reports/release_decision.md
```

## Stop Conditions

Use `stop` rather than `revise` when the input is not benchmarkable:

- architecture manifest has zero documents,
- taxonomy or eval file is missing,
- eval set has zero questions,
- legal or shadow pack cannot be provenance-validated,
- risk owners are unknown for a controlled release,
- the project license is unknown or inconsistent between package metadata and
  README.

## Completion Rule

The implementation objective is complete when the strict release gate is `go`
against governed inputs and `reports/completion_audit.md` maps every documented
requirement to current passing evidence.
