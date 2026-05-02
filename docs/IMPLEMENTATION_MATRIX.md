# Implementation Matrix

This matrix maps the approved documentation to concrete repo artifacts. Status
values are intentionally strict:

- `done` means implemented and covered by a local verification command.
- `partial` means a usable slice exists, but the documented gate is not met.
- `missing` means no meaningful implementation exists yet.
- `deferred` means the ADR explicitly treats the item as an upgrade path.

## Current State Summary

| Area | Status | Evidence | Gap |
|---|---:|---|---|
| Runnable package and CLI | done | `pyproject.toml`, `src/vn_grounded_qa/cli.py`, `python3 -m pytest -q` | None for MVP shell |
| Parser-neutral IR | partial | `src/vn_grounded_qa/models.py`, `src/vn_grounded_qa/parsers.py`, parser taxonomy tests | Needs governed parser bakeoff across all archetypes |
| Canonical store | partial | `src/vn_grounded_qa/store.py`, schema versioning, required manifest `doc_type`, active/accepted status handling, populated `parent_unit_id`, structural/heuristic/same-topic relations, effective-window checks | Version graph remains minimal until governed tests demand more |
| Sparse FTS retrieval | partial | `content_units_fts` in `store.py`, identifier-aware `glossary_terms`, repeat-ingest FTS replacement, `docs/SEGMENTATION.md` | Run governed benchmark with configured segmenter |
| Bounded tool layer | partial | `src/vn_grounded_qa/tools.py`, `docs/TOOL_CONTRACTS.md`, bounded `search_units` metadata filters | Governed E2E traces still required for final metrics |
| Grounded answer contract | partial | `src/vn_grounded_qa/answer.py`, `docs/ANSWER_CONTRACT.schema.json`, runtime contract validator | Extractive MVP only; governed correctness/citation benchmark still required |
| Evaluation harness | partial | `src/vn_grounded_qa/eval.py`, `vn-grounded-qa evalset validate --taxonomy ...`, strict human/rewritten source enforcement, all taxonomy gold fields, expected doc checks, version/as-of checks, p50/p95 latency and cost estimate metrics | Replace synthetic 80-question eval with governed/human-authored set |
| Release gates | partial | `vn-grounded-qa gates release`, `vn-grounded-qa readiness governed`, gate-level `go`/`revise`/`stop`, local source availability checks, `--strict-risk-owners`, license checks, `docs/RISK_REGISTER.md` | Governed corpus, legal pack, shadow pack, deployment owners, and project license still required |

## Milestone Matrix

### M0 — Scope Freeze

| Requirement | Status | Artifact | Next action |
|---|---:|---|---|
| Scope statement | done | `docs/M0_SCOPE.md` | Keep updated through milestone changes |
| Non-goals | done | `docs/M0_SCOPE.md` | Keep stable unless ADR changes |
| Answer contract draft | done | `docs/M0_SCOPE.md`, `docs/ANSWER_CONTRACT.schema.json`, `src/vn_grounded_qa/models.py` | Keep schema aligned with API changes |
| Architecture corpus v1: 24-36 docs | partial | `corpus/architecture/manifest.json` has 2 seed docs; `corpus seed-synthetic` can generate 25 fixture docs | Build governed sample corpus |
| Five archetypes: legal, SOP, Markdown, table PDF, FAQ | partial | Synthetic fixture generator covers all five archetypes | Add governed legal, SOP, table PDF, FAQ docs |
| Evaluation taxonomy v1 | done | `eval/taxonomy.yaml`, `vn-grounded-qa evalset validate` loads taxonomy counts/rules, `vn-grounded-qa evalset seed-synthetic` | Replace synthetic examples with governed authored examples |
| Go/revise/stop decision | partial | `reports/m0_decision.md`, `vn-grounded-qa decisions report`, gate-level `stop` for unbenchmarkable inputs | Re-run after governed corpus manifest exists |

### M1 — Ingestion & Parser Bakeoff

| Requirement | Status | Artifact | Next action |
|---|---:|---|---|
| Docling default parser | partial | `parse_file(..., parser="auto")` tries Docling first, `parse_file(..., parser="docling")`, `docs/PARSERS.md` | Run installed Docling against governed corpus |
| Marker fallback parser | partial | `parse_file(..., parser="auto")` tries Marker after Docling, `parse_file(..., parser="marker")`, `docs/PARSERS.md` | Run installed Marker against governed corpus and confirm CLI behavior |
| Parsed IR v1 | partial | `src/vn_grounded_qa/models.py`, `src/vn_grounded_qa/parsers.py`, documented block taxonomy tests | Run governed parser bakeoff before marking complete |
| Canonical schema v1 | done | `src/vn_grounded_qa/store.py`, `vn-grounded-qa schema`, schema version 1 | Add future migrations as schema evolves |
| Parser quality by archetype | partial | `vn-grounded-qa bakeoff parser ... --parser ...`, `reports/m1_auto_seed.json`, `reports/m1_fallback_seed.json` | Complete governed corpus and run Docling/Marker |
| Parse success >= 90% | partial | `vn-grounded-qa gates m1` checks threshold | Requires governed architecture corpus and parser choice |
| Heading path recovery >= 85% | partial | `vn-grounded-qa gates m1`, manifest `expected_heading_paths` support | Requires governed full corpus |
| Provenance completeness 100% | partial | `vn-grounded-qa gates m1` checks threshold | Requires full corpus verifier |

### M2 — Sparse Retrieval Baseline

| Requirement | Status | Artifact | Next action |
|---|---:|---|---|
| SQLite FTS5 index | done | `src/vn_grounded_qa/store.py` | Continue tuning |
| Vietnamese segmentation | partial | `src/vn_grounded_qa/normalize.py`, `VN_GROUNDED_QA_SEGMENTER`, `docs/SEGMENTATION.md` | Run governed benchmark with VnCoreNLP wrapper |
| Alias fields | done | `aliases` table, seed aliases, `aliases/core.csv`, `vn-grounded-qa alias-import` | Add deployment-specific alias catalogs as needed |
| Field weighting | done | `bm25(...)` in `search_units` | Benchmark weights |
| Recall benchmark on architecture corpus | partial | `eval/synthetic_mvp_seed.jsonl`, `vn-grounded-qa gates m2` with separate @10/@20 eval passes | Replace synthetic eval with governed architecture eval |
| Single-hop Recall@10 >= 0.90 | partial | `vn-grounded-qa gates m2` computes this from `k=10` results | Requires governed eval set |
| Multi-hop Recall@20 >= 0.80 | partial | `vn-grounded-qa gates m2` computes this from `k=20` results | Requires governed multi-hop eval |
| Mixed Vi-En Recall@10 >= 0.80 | partial | `vn-grounded-qa gates m2` computes this from `k=10` results | Requires governed mixed-language eval |
| Search p95 <= 400ms | partial | `vn-grounded-qa gates m2` | Requires architecture corpus benchmark |

### M3 — Tool Layer & Bounded Orchestration

| Requirement | Status | Artifact | Next action |
|---|---:|---|---|
| Tool contracts | done | `src/vn_grounded_qa/tools.py`, `docs/TOOL_CONTRACTS.md` | Keep docs aligned with API changes |
| Max 6 calls, max 2 searches, depth 1 | done | `ToolSession` limits and edge-case tests | None |
| Trace logging | done | `tool_traces` table, `ToolSession(trace_id=...)`, `ask --trace-id`, `traces list`, `traces show` | None for MVP trace review |
| Avg tool calls <= 4, p95 <= 6 | partial | `vn-grounded-qa gates m3` | Requires governed E2E eval traces |
| Argument error rate < 2% | partial | `vn-grounded-qa gates m3`, explicit `tool_argument_error_rate` metric | Requires governed E2E eval traces |
| Infinite loop rate = 0 | partial | `vn-grounded-qa gates m3`, bounded `ToolSession`, explicit `tool_limit_error_rate` and `tool_limit_error_count` metrics | Requires governed E2E eval traces |

### M4 — End-to-End MVP

| Requirement | Status | Artifact | Next action |
|---|---:|---|---|
| Answer correctness >= 75% | partial | `vn-grounded-qa gates m4` with strict synthetic 80-question set, answer-contract validation, version gold checks | Need governed scored 80-question set |
| Citation exactness >= 95% | partial | `vn-grounded-qa gates m4` verifies `expected_citation_unit_ids` when provided | Need governed gold citation spans |
| Hallucinated citations = 0 | partial | `vn-grounded-qa gates m4` | Run final governed pre-release pass |
| No-answer precision >= 90% | partial | `eval/synthetic_mvp_seed.jsonl` passes synthetic no-answer case | Requires 80-question eval |
| Full-pipeline p95 <= 8s | partial | `vn-grounded-qa gates m4` | Requires governed E2E eval |

### M5 — Thin RAG Baseline Comparison

| Requirement | Status | Artifact | Next action |
|---|---:|---|---|
| Thin RAG baseline | partial | `src/vn_grounded_qa/baselines.py`, `vn-grounded-qa gates m5`, `vn-grounded-qa baselines report` | Replace local extractive baseline with model-backed baseline if required |
| Sparse >= 85% of baseline correctness or explain gap | partial | `vn-grounded-qa gates m5`, `reports/m5_baseline_comparison.md` | Re-run on governed 80-question eval |

### M6 — Scale & Upgrade Decision

| Requirement | Status | Artifact | Next action |
|---|---:|---|---|
| Larger packs tested | partial | `vn-grounded-qa gates m6 --scale-eval ...` | Build real larger pack |
| Quality drop <= 5 points | partial | `vn-grounded-qa gates m6` | Run on real larger pack |
| Pipeline p95 <= 10s | partial | `vn-grounded-qa gates m6` | Run on real larger pack |
| Provenance/version errors = 0 | partial | `vn-grounded-qa gates m6` provenance/version verifier, active-version overlap checks, legal regression `coverage_tags` validation, `corpus/legal-regression/manifest.json` | Fill legal/policy regression pack and run governed legal/policy tests |
| Upgrade decision | partial | M6 gate report gives go/revise/stop; `vn-grounded-qa decisions report` can emit narrative reports | Re-run after governed M6 scale/legal pack exists |

## Release Gate Matrix

| Gate | Status | Current evidence | Missing evidence |
|---|---:|---|---|
| Corpus registered and provenance-complete | partial | `vn-grounded-qa gates release` aggregates M0/M1 and blocks missing local manifest sources | Replace seed/synthetic corpus with governed corpus |
| Parsing benchmarked for all archetypes | partial | `vn-grounded-qa gates m1` | Run Docling/Marker on governed corpus |
| Retrieval thresholds met | partial | `vn-grounded-qa gates m2` | Run governed retrieval eval |
| Citation hallucinations = 0 | partial | `vn-grounded-qa gates m4` | Run final governed pre-release pass |
| No-answer behavior verified | partial | `vn-grounded-qa gates m4` | Run governed no-answer eval |
| Shadow corpus tested | partial | `vn-grounded-qa gates m6 --scale-eval ...`, production shadow `coverage_tags` validation, `corpus/production-shadow/manifest.json` | Fill production shadow pack |
| Open risks documented with owners/mitigations | partial | `docs/RISK_REGISTER.md`, `vn-grounded-qa risks validate`, `vn-grounded-qa gates release --strict-risk-owners` | Replace role owners with deployment owners when assigned |
| Project license selected | partial | `vn-grounded-qa readiness governed`, `vn-grounded-qa gates release`, `pyproject.toml`, `README.md` | Select the real project license and replace `TBD` consistently |
