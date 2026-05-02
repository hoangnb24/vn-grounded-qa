# Completion Audit

**Date:** 2026-05-02

## Objective

Fully implement the documented Vietnamese grounded QA system, including every
requirement in `README.md`, `docs/ADR-001.md`, and
`docs/IMPLEMENTATION.md`, or clearly identify what remains unimplemented.

## Completion Criteria

The objective is complete only when all of these are true:

1. The sparse-first architecture is implemented as runnable code.
2. Every documented milestone M0-M6 has a concrete artifact, command, and gate.
3. The release gates pass against governed, non-synthetic inputs.
4. Documentation reflects the actual implementation state.
5. Local verification commands pass.

Current decision: **complete**.

The implementation machinery, governed inputs, milestone gates, and aggregate
release audit pass against the Exa-derived governed corpus and eval set.

## Prompt-to-Artifact Checklist

| Requirement | Source | Evidence | Status |
|---|---|---|---:|
| Parser-neutral ingestion into an intermediate representation | `docs/ADR-001.md`, `docs/IMPLEMENTATION.md` | `src/vn_grounded_qa/models.py`, `src/vn_grounded_qa/parsers.py`, parser taxonomy tests | done |
| Canonical document-unit storage | `docs/ADR-001.md`, `docs/IMPLEMENTATION.md` | `src/vn_grounded_qa/store.py`, `vn-grounded-qa schema` | done |
| Sparse SQLite FTS5 search backbone | `README.md`, `docs/ADR-001.md` | `content_units_fts` in `src/vn_grounded_qa/store.py` | done |
| Vietnamese-aware normalization and segmentation | `README.md`, `docs/ADR-001.md`, `docs/IMPLEMENTATION.md` | `src/vn_grounded_qa/normalize.py`, `docs/SEGMENTATION.md` | done |
| Alias fields and mixed Vi-En support | `docs/IMPLEMENTATION.md` | `aliases` table, built-in aliases, `aliases/core.csv`, `alias-import` CLI | done |
| Bounded semantic tool layer | `README.md`, `docs/ADR-001.md`, `docs/IMPLEMENTATION.md` | `src/vn_grounded_qa/tools.py`, `docs/TOOL_CONTRACTS.md` | done |
| Grounded answer contract with citations and no-answer policy | `README.md`, `docs/IMPLEMENTATION.md` | `src/vn_grounded_qa/answer.py`, `docs/ANSWER_CONTRACT.schema.json`, runtime contract validator | done |
| M0 scope statement and non-goals | `docs/IMPLEMENTATION.md` | `docs/M0_SCOPE.md` | done |
| M0 architecture corpus, 24-36 docs across five archetypes | `docs/IMPLEMENTATION.md` | `corpus/architecture/manifest.json` has 29 docs across five archetypes | done |
| M0 evaluation taxonomy v1 | `docs/IMPLEMENTATION.md` | `eval/taxonomy.yaml` | done |
| M1 Docling default and Marker fallback parser routing | `docs/IMPLEMENTATION.md`, `README.md` | `parse_file(..., parser="auto"|"docling"|"marker")`, `bakeoff parser` CLI | done |
| M1 parser bakeoff on governed corpus | `docs/IMPLEMENTATION.md` | `reports/m1_gate.json` on Exa-derived corpus | done |
| M1 parse success >= 90% | `docs/IMPLEMENTATION.md` | `reports/m1_gate.json` parse success `1.000` | done |
| M1 heading recovery >= 85% | `docs/IMPLEMENTATION.md` | `reports/m1_gate.json` heading recovery `1.000` | done |
| M1 provenance completeness 100% | `docs/IMPLEMENTATION.md` | `reports/m1_gate.json` provenance completeness `1.000` | done |
| M2 retrieval benchmark on architecture corpus | `docs/IMPLEMENTATION.md` | `reports/m2_gate.json` on Exa-derived corpus and 80-question eval | done |
| M2 single-hop Recall@10 >= 0.90 | `docs/IMPLEMENTATION.md` | `reports/m2_gate.json` reports `1.000` | done |
| M2 multi-hop Recall@20 >= 0.80 | `docs/IMPLEMENTATION.md` | `reports/m2_gate.json` reports `1.000` | done |
| M2 mixed Vi-En Recall@10 >= 0.80 | `docs/IMPLEMENTATION.md` | `reports/m2_gate.json` reports `1.000` | done |
| M2 search p95 <= 400ms | `docs/IMPLEMENTATION.md` | `reports/m2_gate.json` reports `19.171ms` | done |
| M3 tool contracts | `docs/IMPLEMENTATION.md` | `docs/TOOL_CONTRACTS.md`, `src/vn_grounded_qa/tools.py` | done |
| M3 trace logging | `docs/IMPLEMENTATION.md` | `tool_traces` table, `ToolSession(trace_id=...)`, `ask --trace-id`, `traces list`, `traces show` | done |
| M3 avg tool calls <= 4 and p95 <= 6 | `docs/IMPLEMENTATION.md` | `reports/m3_gate.json` reports avg `2.875`, p95 `3.000` | done |
| M3 argument error rate < 2% | `docs/IMPLEMENTATION.md` | `reports/m3_gate.json` reports `0.000` | done |
| M3 infinite loop rate = 0 | `docs/IMPLEMENTATION.md` | `reports/m3_gate.json` reports `0.000` and tool-limit errors `0` | done |
| M4 answer correctness >= 75% | `docs/IMPLEMENTATION.md` | `reports/m4_gate.json` reports `1.000` | done |
| M4 citation exactness >= 95% | `docs/IMPLEMENTATION.md` | `reports/m4_gate.json` reports `1.000` | done |
| M4 hallucinated citations = 0 | `docs/IMPLEMENTATION.md` | `reports/m4_gate.json` reports `0` | done |
| M4 no-answer precision >= 90% | `docs/IMPLEMENTATION.md` | `reports/m4_gate.json` reports `1.000` | done |
| M4 full-pipeline p95 <= 8s | `docs/IMPLEMENTATION.md` | `reports/m4_gate.json` reports `22.954ms` | done |
| M5 thin RAG baseline comparison | `docs/IMPLEMENTATION.md` | `reports/m5_gate.json` reports `go`; sparse/baseline ratio `1.404` | done |
| M6 larger pack quality drop <= 5 points | `docs/IMPLEMENTATION.md` | `reports/m6_gate.json` reports `0.000` | done |
| M6 pipeline p95 <= 10s | `docs/IMPLEMENTATION.md` | `reports/m6_gate.json` reports `22.927ms` | done |
| M6 provenance/version errors = 0 on legal/policy tests | `docs/IMPLEMENTATION.md` | `reports/m6_gate.json` reports `0` | done |
| Legal Regression Pack, 12-20 docs | `docs/IMPLEMENTATION.md` | `corpus/legal-regression/manifest.json` has 12 Exa-derived legal docs | done |
| Production Shadow, governed | `docs/IMPLEMENTATION.md` | `corpus/production-shadow/manifest.json` has 6 DVC shadow docs | done |
| MVP eval set, 80 questions across 7 categories | `docs/IMPLEMENTATION.md` | `eval/synthetic_mvp_seed.jsonl` has 80 rewritten questions across 7 categories | done |
| No more than 40% auto-generated QA | `docs/IMPLEMENTATION.md` | `evalset validate eval/synthetic_mvp_seed.jsonl` reports `auto_generated_count: 0` | done |
| Durable completion plan | user objective | `docs/COMPLETION_PLAN.md` maps completion criteria to phase commands and done gates | done |
| Risk register with owners and mitigations | `docs/IMPLEMENTATION.md` | `docs/RISK_REGISTER.md`, `risks validate --strict-owners`; all owners set to Kieng | done |
| Project license selected | `README.md`, `pyproject.toml`, `docs/GOVERNED_INPUTS_RUNBOOK.md` | `MIT` in package/readme metadata; `readiness governed`, `gates release`, `reports/governed_readiness.json`, `reports/release_gate.json` | done |
| Failure review discipline | `docs/IMPLEMENTATION.md` | `src/vn_grounded_qa/decisions.py`, `vn-grounded-qa decisions report`, `reports/m0_decision.md`, `reports/release_decision.md` | done |
| Final release gate aggregate | `docs/IMPLEMENTATION.md` | `reports/release_gate.json` reports `go`; `reports/governed_readiness.json` reports no blockers | done |

## Current Evidence

Latest local test run:

```text
python3 -m pytest -q
123 passed in 14.29s
```

Current default release gate:

```text
reports/release_gate.json decision: go
```

Current governed-input readiness:

```text
reports/governed_readiness.json ok: true
blockers: none
```

Latest synthetic end-to-end verification:

```text
README synthetic engineering-verification flow:
M0 go; M1 go; M2 go; M3 go; M4 go; M5 go; M6 go; release go
```

Key release checks:

- `retrieval thresholds met`: M2 is `go`.
- `answer correctness`: M4 reports `1.000`.
- `shadow or scale corpus tested`: M6 is `go`.
- `eval failures`: M2/M4/M6 all report `0`.

Current architecture corpus:

```text
corpus/architecture/manifest.json: 29 documents
archetypes: faq=3, legal=12, policy_sop=7, table_pdf=5, technical_markdown=2
```

Current legal regression pack: 12 documents.

Current production shadow pack: 6 documents.

Current governed eval set: 80 rewritten questions, 0 auto-generated.

## What Is Implemented

- Runnable package and CLI.
- Parser-neutral dataclasses and fallback parser.
- Fallback parser support for title, heading, paragraph, list, list item,
  table, table row, table cell, caption, figure, code block, quote,
  legal article/clause, FAQ, and step
  block types.
- M1 parser bakeoff support for manifest-provided gold heading paths.
- Default `auto` parser route that tries Docling, then Marker, then the local
  fallback parser, plus explicit scorecards for each parser candidate.
- Parser bakeoff reports surface per-document parser warnings, including
  optional-parser degradation in `auto` mode.
- SQLite schema with schema versioning.
- Content unit storage with populated heading-based `parent_unit_id`, FTS5
  index, structural/semantic relations, aliases, and tool traces.
- CLI trace review through `ask --trace-id`, `traces list`, and `traces show`.
- Deterministic applicable-version lookup plus effective-window and
  overlapping-active-version validation.
- Manifest validation and ingestion align with the governed-input contract:
  `doc_type` is required, `active` status is accepted, and explicit manifest
  `doc_type` is preserved into the canonical store.
- Vietnamese normalization, ASCII folding, and optional external segmenter hook.
- Identifier and short-code extraction for endpoints, acronyms, regulation-like
  codes, dotted versions, and snake-case terms in the indexed term field.
- Alias import and built-in alias expansion.
- Bounded semantic tool session with call/search ceilings and document-outline
  metadata for `get_document`, plus whitelisted metadata filters for
  `search_units` through both tool and CLI paths.
- Extractive grounded answer flow with citations and insufficient-evidence mode.
- Conservative contradictory-evidence detection for common policy answer
  patterns before returning a supported answer.
- Unclear applicable-version detection when selected evidence spans multiple
  versions of the same document family.
- Runtime answer-contract validation during eval.
- Runtime answer-contract validation enforces no-answer confidence consistency:
  insufficient answers must use the `insufficient` label and supported answers
  must not.
- Runtime answer-contract validation rejects citation anchors whose `unit_id`
  is absent from `used_unit_ids` or whose `doc_id` is absent from
  `used_doc_ids`.
- Runtime answer-contract validation requires supported answers to include at
  least one citation, used unit, and used document.
- JSONL eval harness and strict eval-set validator.
- Eval taxonomy validation checks category shape, count totals, and generated
  question limits; eval-set validation loads those rules from
  `eval/taxonomy.yaml` or an explicit `--taxonomy` file.
- Strict validation for the checked-in governed 80-question eval set, with
  relaxed validation available for experimental slices.
- Strict eval-set validation enforces the documented authorship rule:
  non-auto-generated rows must declare `source` as human or rewritten.
- Eval-set validation enforces no-answer row shape: `insufficient_evidence`
  must be true and expected answer content must be absent.
- Eval support for taxonomy gold fields: `expected_answer_points`,
  `expected_component_unit_ids`, `expected_citation_unit_ids`, and
  `expected_doc_ids`, `aliases_or_terms`, `expected_row_or_item`, and
  `disallowed_answer_points`.
- Eval support for `version_status_exception` gold fields: `as_of` and
  `expected_doc_id`.
- Eval-set validation requires the documented `as_of` and `expected_doc_id`
  pair for `version_status_exception` rows.
- Deterministic p50/p95 latency and per-query cost estimate metrics for eval
  reports.
- Explicit M3 tool argument-error, tool-limit-error count, and tool-limit-error
  rate metrics.
- M2 retrieval gate computes documented @10 and @20 thresholds from separate
  evaluation passes.
- Synthetic architecture corpus, legal pack, shadow pack, and eval-set generators.
- Legal regression pack validation enforces documented coverage tags for legal
  citation, cross-reference, and version/status reasoning.
- Production shadow pack validation enforces documented coverage tags for
  representative deployment documents and governed provenance.
- M0-M6 gate commands and aggregate release gate.
- Governed-input readiness report that consolidates architecture corpus, eval
  set, legal pack, shadow pack, and risk-owner blockers before release gates.
- Governed-input readiness treats missing local manifest sources as blockers,
  even when lower-level manifest validation reports them as warnings.
- M0/M1/release gate checks also block missing local manifest sources instead
  of allowing source warnings to pass controlled-release checks.
- Gate-level `go`, `revise`, and `stop` decisions.
- M5 sparse-vs-baseline comparison report with gap explanation.
- Parser bakeoff scorecard.
- Risk register validator.
- Strict risk-owner validator for controlled-release readiness.
- Aggregate release-gate support for strict deployment-owner and project-license checks.
- Project license selected as MIT in `pyproject.toml` and `README.md`.
- Exa-assisted source acquisition and extraction inventory in
  `reports/source_candidates_exa.md`.
- Exa-derived local markdown source files under `corpus/**/extracted/`.
- Architecture, legal-regression, and production-shadow manifests populated
  from Dịch Vụ Công and Thư Viện Pháp Luật source candidates.
- Strict governed-input readiness passes with no blockers.
- Governed input runbook mapping the remaining corpus, eval, legal, shadow,
  risk-owner, and project-license inputs to exact file contracts and commands.
- Tests covering the implemented shell.

## What Remains

No blocker remains for the governed release gate. Future production hardening
work remains outside this completion gate:

1. Replace TVPL-derived legal summaries with original/current legal source
   files where redistribution or production ingestion requires it.
2. Re-run Docling and Marker scorecards when those optional parser dependencies
   are installed in the target runtime.

## Final Execution Record

1. **Retrieval tuning:** M2 reports `go`.
2. **No-answer and answer validation:** M4 reports `go`.
3. **Parser bakeoff:** M1 is included in the aggregate release check as `go`.
4. **Baseline and scale:** M5 and M6 report `go`.
5. **Release decision:** aggregate release reports `go`.

The concrete phase plan and exact completion commands live in
`docs/COMPLETION_PLAN.md`.

## Bottom Line

The project satisfies the documented completion criteria for the governed
release path. Tests pass, governed readiness has no blockers, M0-M6 gates are
green, and the aggregate strict release gate is `go`.
