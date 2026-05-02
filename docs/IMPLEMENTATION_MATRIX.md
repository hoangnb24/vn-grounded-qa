# Implementation Matrix

This matrix maps the approved documentation to concrete repo artifacts. Status
values are strict:

- `done` means implemented and covered by a local verification command.
- `deferred` means the ADR explicitly treats the item as an upgrade path.

## Current State Summary

| Area | Status | Evidence | Notes |
|---|---:|---|---|
| Runnable package and CLI | done | `pyproject.toml`, `src/vn_grounded_qa/cli.py`, `python3 -m pytest -q` | CLI covers ingestion, search, QA, eval, corpus governance, gates, traces, and baselines |
| Parser-neutral IR | done | `src/vn_grounded_qa/models.py`, `src/vn_grounded_qa/parsers.py`, parser taxonomy tests, `reports/m1_gate.json` | Local fallback parser is dependency-free; Docling and Marker remain optional parser candidates |
| Canonical store | done | `src/vn_grounded_qa/store.py`, `vn-grounded-qa schema` | Includes schema versioning, document units, relations, aliases, tool traces, and version-window checks |
| Sparse FTS retrieval | done | `content_units_fts`, `reports/m2_gate.json` | Includes alias expansion, identifier routing, source-pair routing, metadata filters, and reranking |
| Bounded tool layer | done | `src/vn_grounded_qa/tools.py`, `docs/TOOL_CONTRACTS.md`, `reports/m3_gate.json` | Max 6 tool calls, max 2 searches, expansion depth 1 |
| Grounded answer contract | done | `src/vn_grounded_qa/answer.py`, `docs/ANSWER_CONTRACT.schema.json`, `reports/m4_gate.json` | Extractive answers include citations, source-facing anchors, confidence labels, no-answer policy, and contradiction/version checks |
| Evaluation harness | done | `src/vn_grounded_qa/eval.py`, `eval/taxonomy.yaml`, `eval/synthetic_mvp_seed.jsonl` | 80 rewritten questions, 0 auto-generated rows, all seven categories |
| Release gates | done | `reports/governed_readiness.json`, `reports/m2_gate.json` through `reports/m6_gate.json`, `reports/release_gate.json` | Strict release gate is `go` with deployment-owner and license checks |

## Milestone Matrix

### M0 — Scope Freeze

| Requirement | Status | Artifact | Evidence |
|---|---:|---|---|
| Scope statement | done | `docs/M0_SCOPE.md` | Scope and non-goals are documented |
| Answer contract draft | done | `docs/ANSWER_CONTRACT.schema.json`, `src/vn_grounded_qa/models.py` | Runtime eval validates answer contracts |
| Architecture corpus v1: 24-36 docs | done | `corpus/architecture/manifest.json` | 29 docs across five archetypes |
| Five archetypes | done | `corpus/architecture/manifest.json` | faq=3, legal=12, policy_sop=7, table_pdf=5, technical_markdown=2 |
| Evaluation taxonomy v1 | done | `eval/taxonomy.yaml` | `evalset validate` enforces category counts and row rules |
| Go/revise/stop decision | done | `reports/release_decision.md`, `src/vn_grounded_qa/decisions.py` | Decision report is `go` |

### M1 — Ingestion & Parser Bakeoff

| Requirement | Status | Artifact | Evidence |
|---|---:|---|---|
| Docling default parser candidate | done | `parse_file(..., parser="auto")`, `parse_file(..., parser="docling")`, `docs/PARSERS.md` | Optional dependency is benchmarked through `bakeoff parser --parser docling` |
| Marker fallback parser candidate | done | `parse_file(..., parser="marker")`, `docs/PARSERS.md` | Optional dependency is benchmarked through `bakeoff parser --parser marker` |
| Local fallback parser | done | `parse_file(..., parser="fallback")` | CI/local parser handles Markdown, text, and optional simple PDF extraction |
| Parsed IR v1 | done | `src/vn_grounded_qa/models.py`, `src/vn_grounded_qa/parsers.py` | Parser taxonomy tests cover supported block types |
| Canonical schema v1 | done | `src/vn_grounded_qa/store.py`, `vn-grounded-qa schema` | Schema version 1 |
| Parse success >= 90% | done | `reports/m1_gate.json` | Included in release gate as M1 `go` |
| Heading path recovery >= 85% | done | `reports/m1_gate.json` | Manifest `expected_heading_paths` supported |
| Provenance completeness 100% | done | `reports/m1_gate.json` | Included in release gate as M1 `go` |

### M2 — Sparse Retrieval Baseline

| Requirement | Status | Artifact | Evidence |
|---|---:|---|---|
| SQLite FTS5 index | done | `src/vn_grounded_qa/store.py` | `content_units_fts` indexes title, heading, normalized, segmented, glossary, table, and folded text |
| Vietnamese normalization and segmentation | done | `src/vn_grounded_qa/normalize.py`, `docs/SEGMENTATION.md` | ASCII folding and fallback segmentation are built in; external segmenter hook is supported |
| Alias fields and catalog | done | `aliases` table, `aliases/core.csv`, `alias-import` CLI | Governed mixed-language aliases are seeded and importable |
| Identifier-aware retrieval | done | `identifier_variants`, `identifier_candidate_rows` | DVC codes and legal document numbers route to matching documents |
| Source-pair retrieval | done | `source_pair_doc_ids`, `source_pair_candidate_rows` | Multi-document DVC/TVPL source questions route to paired evidence |
| Recall benchmark on architecture corpus | done | `reports/m2_gate.json` | Eval failures `0` |
| Single-hop Recall@10 >= 0.90 | done | `reports/m2_gate.json` | `1.000` |
| Multi-hop component Recall@20 >= 0.80 | done | `reports/m2_gate.json` | `1.000` |
| Mixed Vi-En Recall@10 >= 0.80 | done | `reports/m2_gate.json` | `1.000` |
| Search p95 <= 400ms | done | `reports/m2_gate.json` | `19.171ms` |

### M3 — Tool Layer & Bounded Orchestration

| Requirement | Status | Artifact | Evidence |
|---|---:|---|---|
| Tool contracts | done | `src/vn_grounded_qa/tools.py`, `docs/TOOL_CONTRACTS.md` | Search/read/context/document/term/version tools documented |
| Max 6 calls, max 2 searches, depth 1 | done | `ToolSession` | Gate reports no tool-limit errors |
| Trace logging | done | `tool_traces`, `ask --trace-id`, `traces list`, `traces show` | Persisted traces include args, result counts, and timestamps |
| Avg tool calls <= 4, p95 <= 6 | done | `reports/m3_gate.json` | avg `2.875`, p95 `3.000` |
| Argument error rate < 2% | done | `reports/m3_gate.json` | `0.000` |
| Infinite loop rate = 0 | done | `reports/m3_gate.json` | `0.000` |

### M4 — End-to-End MVP

| Requirement | Status | Artifact | Evidence |
|---|---:|---|---|
| Answer correctness >= 75% | done | `reports/m4_gate.json` | `1.000` |
| Citation exactness >= 95% | done | `reports/m4_gate.json` | `1.000` |
| Hallucinated citations = 0 | done | `reports/m4_gate.json` | `0` |
| No-answer precision >= 90% | done | `reports/m4_gate.json` | `1.000` |
| Full-pipeline p95 <= 8s | done | `reports/m4_gate.json` | `22.954ms` |
| Eval failures = 0 | done | `reports/m4_gate.json` | `0` |

### M5 — Thin RAG Baseline Comparison

| Requirement | Status | Artifact | Evidence |
|---|---:|---|---|
| Thin RAG baseline | done | `src/vn_grounded_qa/baselines.py`, `reports/m5_gate.json`, `reports/m5_baseline_comparison.md` | Baseline executed over 80 eval rows |
| Sparse >= 85% of baseline correctness or explain gap | done | `reports/m5_gate.json` | sparse/baseline ratio `1.404` |

### M6 — Scale & Upgrade Decision

| Requirement | Status | Artifact | Evidence |
|---|---:|---|---|
| Larger packs tested | done | `reports/m6_gate.json`, `corpus/legal-regression/manifest.json`, `corpus/production-shadow/manifest.json` | Legal and shadow packs validate |
| Quality drop <= 5 points | done | `reports/m6_gate.json` | `0.000` |
| Pipeline p95 <= 10s | done | `reports/m6_gate.json` | `22.927ms` |
| Provenance/version errors = 0 | done | `reports/m6_gate.json` | `0` |
| Upgrade decision | done | `reports/release_decision.md` | Sparse-first remains justified for the governed MVP |

## Release Gate Matrix

| Gate | Status | Evidence |
|---|---:|---|
| Corpus registered and provenance-complete | done | `reports/release_gate.json`, M0/M1 `go` |
| Parsing benchmarked for all archetypes | done | `reports/release_gate.json`, M1 `go` |
| Retrieval thresholds met | done | `reports/release_gate.json`, M2 `go` |
| Citation hallucinations = 0 | done | `reports/release_gate.json`, hallucinated citations `0` |
| No-answer behavior verified | done | `reports/release_gate.json`, no-answer precision `1.000` |
| Legal regression pack registered | done | `corpus/legal-regression/manifest.json`, 12 docs |
| Shadow corpus registered | done | `corpus/production-shadow/manifest.json`, 6 docs |
| Shadow or scale corpus tested | done | `reports/release_gate.json`, M6 `go` |
| Open risks documented with deployment owners/mitigations | done | `docs/RISK_REGISTER.md`, `reports/release_gate.json` |
| Project license selected | done | `pyproject.toml`, `README.md`, `reports/release_gate.json` |

## Deferred Upgrade Paths

The ADR leaves these upgrades available when future evidence justifies them:

- local reranker or hybrid neural retrieval,
- fuller evidence/version graph,
- model-backed thin RAG baseline,
- production VnCoreNLP segmentation wrapper,
- original-source legal ingestion for redistribution-sensitive deployments.
