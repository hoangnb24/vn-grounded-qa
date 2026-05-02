# Implementation Plan — Milestones, Schemas, Evaluation, Risk

**Status:** Governed sparse-first MVP complete; strict release gate `go`; LLM-assisted mode experimental  
**Date:** 2026-05-02

The codebase contains the sparse-first MVP implementation, governed input
manifests, milestone gates, release gate, synthetic verification fixtures, and
readiness checks. The governed architecture corpus, MVP eval set, legal
regression pack, production shadow pack, named deployment risk owners, and MIT
license satisfy the strict release gate.

---

## Milestones

Every milestone must reduce one concrete failure risk, produce a reusable artifact, and end in a go / revise / stop decision.

### M0 — Scope Freeze

**Exit question:** Do we agree what "good" means?

Outputs: scope statement, non-goals, answer contract draft, architecture corpus v1 (24–36 docs across 5 archetypes), evaluation taxonomy v1.

### M1 — Ingestion & Parser Bakeoff

**Exit question:** Are documents being transformed into trustworthy units?

Tasks: Run Docling (default) and Marker (fallback) against architecture corpus. Define Parsed IR v1, canonical schema v1. Score parser quality by archetype.

Gates:
- ≥ 90% parse success without fatal failure
- ≥ 85% usable heading path recovery
- 100% provenance completeness

### M2 — Sparse Retrieval Baseline

**Exit question:** Can sparse retrieval recover the right evidence?

Tasks: Build SQLite FTS5 index with Vietnamese segmentation, alias fields, field weighting. Benchmark recall on architecture corpus.

Gates:
- Single-hop Recall@10 ≥ 0.90
- Multi-hop component Recall@20 ≥ 0.80
- Mixed Vietnamese-English Recall@10 ≥ 0.80
- Search-only p95 ≤ 400ms

### M3 — Tool Layer & Bounded Orchestration

**Exit question:** Can the model use tools without unstable loops?

Tasks: Define tool contracts, orchestration ceiling, trace logging.

Gates:
- Avg tool calls ≤ 4, p95 ≤ 6
- Argument error rate < 2%
- Infinite loop rate = 0

### M4 — End-to-End MVP

**Exit question:** Are answers grounded, cited, and operationally acceptable?

Gates:
- Answer correctness ≥ 75%
- Citation exactness ≥ 95%
- Hallucinated citations = 0
- No-answer precision ≥ 90%
- Full-pipeline p95 ≤ 8s

### M5 — Thin RAG Baseline Comparison

**Exit question:** Is sparse-first competitive enough to stay the course?

Gate: Sparse + bounded-tools achieves ≥ 85% of thin RAG baseline answer correctness, or produces a well-supported explanation for the gap.

### M6 — Scale & Upgrade Decision

**Exit question:** What additional complexity, if any, is justified?

Gates:
- Quality drop ≤ 5 points on larger packs
- Pipeline p95 ≤ 10s
- Provenance/version errors = 0 on curated legal/policy tests

---

## Corpus Strategy

| Corpus | Size | Purpose |
|---|---|---|
| Architecture Corpus | 29 docs | Design validation across legal, policy/SOP, technical Markdown, table-heavy PDF, and FAQ archetypes |
| Legal Regression Pack | 12 docs | Stress legal citation, cross-reference, and version/status reasoning |
| Production Shadow | 6 docs | Exercise representative deployment documents and governed provenance |

---

## Schema (Core Entities)

### Parsed IR

Parser-neutral bridge between raw parsing and canonical storage.

```
document_meta:  doc_id, source_uri, source_hash, format, parser_name, parser_version, ingest_time
pages:          page_no, dimensions, blocks[]
blocks:         block_id, block_type, text, order, parent_block_id, bbox, attributes
quality:        ocr_coverage, block_count, heading_confidence, parser_warnings
```

Block types: `title`, `heading`, `paragraph`, `list`, `list_item`, `table`, `table_row`, `table_cell`, `caption`, `figure`, `code_block`, `quote`, `unknown`. Domain overlays: `legal_article`, `legal_clause`, `faq_question`, `faq_answer`, `step`.

### Canonical Store

**`documents`** — identity, provenance, versioning:
`doc_id`, `doc_family_id`, `title`, `doc_type`, `format`, `language`, `source_uri`, `source_hash`, `version_label`, `effective_from/to`, `status`, `parser_name/version`

**`content_units`** — the heart of the system (one row = one retrievable evidence unit):
`unit_id`, `doc_id`, `parent_unit_id`, `unit_type`, `heading_path`, `ordinal_path`, `sequence_no`, `page_start/end`, `raw_text`, `normalized_text`, `vi_segmented_text`, `ascii_folded_text`, `glossary_terms`, `table_text`, `unit_hash`

Unit granularity by archetype:
- Legal → article / clause / point
- SOP → section / subsection / step
- Markdown → heading block / paragraph / code block
- Table-heavy → table + text shadow
- FAQ → question-answer item

**`relations`** — structural and semantic links:
`relation_id`, `from_unit_id`, `relation_type`, `to_unit_id`, `confidence`, `source`

Types: `parent`, `child`, `next`, `previous`, `references`, `defines`, `exception_to`, `supersedes`, `amends`, `same_topic`

**`aliases`** — terminology for mixed-language retrieval:
`alias_id`, `surface_form`, `canonical_form`, `lang`, `domain`, `alias_type`, `source`

### Search Index

Main FTS5 fields: `title`, `heading_path`, `normalized_text`, `vi_segmented_text`, `glossary_terms`, `table_text`

Side index: `ascii_folded_text`, alias `surface_form`/`canonical_form`,
identifiers, source-facing DVC/TVPL codes, short codes, and table shadows.

Retrieval behavior includes:

- governed Vietnamese/English alias expansion from `aliases/core.csv` and
  built-in seed aliases,
- exact identifier candidate routing for DVC procedure codes and legal
  document numbers,
- source-pair routing for multi-document DVC/TVPL questions,
- metadata penalties for acquisition and coverage-tag units,
- intent boosts for time-limit, form, submission-channel, and result questions,
- metadata filters for `doc_id`, `doc_family_id`, `doc_type`, `status`, and
  `version_label`.

### Tool Contracts

| Tool | Purpose |
|---|---|
| `search_units` | Find candidate evidence units (query, filters, top_k) |
| `read_units` | Read selected units in full |
| `expand_context` | Follow structural/explicit relations |
| `get_document` | Retrieve doc metadata or outline |
| `resolve_terms` | Normalize terms, acronyms, aliases |
| `get_applicable_version` | Resolve valid doc version for time-sensitive domains |

Orchestration ceiling: max 6 total tool calls, max 2 searches, max expansion depth 1.

### LLM-Assisted Semantic Layer

The repository includes an optional, bounded LLM-assisted path:

- `src/vn_grounded_qa/llm.py`: Google Gemini adapter using structured JSON
  output, env-based Developer API / Vertex AI configuration, bounded timeout,
  and finite retry attempts.
- `src/vn_grounded_qa/semantic_models.py`: strict Pydantic contracts for
  `QueryPlan`, `EvidenceDecision`, `EvidenceJudgment`, and `AnswerDraft`.
- `src/vn_grounded_qa/semantic.py`: prompt wrappers and exact unit-ID
  validation for planning, evidence judgment, and answer drafting.
- `answer_question_llm_assisted(...)`: parallel answer path that keeps
  deterministic retrieval, unit reads, citation construction, support checks,
  and answer-contract validation authoritative.

The LLM layer cannot create citations, invent unit IDs, enable external tools,
or run an open-ended agent loop. Failures fall back to deterministic mode with
failure metadata in `tool_calls`.

### Answer Contract

Every answer must include: `answer`, `citations[]`, `confidence_label` (high/medium/low/insufficient), `insufficient_evidence` flag, `used_doc_ids[]`, `used_unit_ids[]`.

Supported answers (`insufficient_evidence=false`) must include at least one
citation, one used unit, and one used document.

No-answer rules: prefer "insufficient evidence" when retrieved units don't support the conclusion, evidence is contradictory, applicable version is unclear, or question is outside corpus. `insufficient_evidence=true` must pair with `confidence_label=insufficient`; supported answers must not use the `insufficient` confidence label.

Anti-hallucination: never fabricate source anchors, never invent documents, never imply certainty when provenance is unresolved. Every citation `unit_id` must also appear in `used_unit_ids`, and every citation `doc_id` must also appear in `used_doc_ids`.

---

## Evaluation

**MVP eval set:** 80 questions across 7 categories:

| Category | Count |
|---|---|
| Single-unit factual / paraphrase | 20 |
| Vietnamese + light English mixing | 10 |
| Table / list / structure-heavy | 10 |
| Multi-hop within one document | 10 |
| Multi-document synthesis | 10 |
| Version / status / exception | 10 |
| No-answer / insufficient evidence | 10 |

Rule: no more than 40% from auto-generated QA. Rest must be rewritten or human-authored and marked with `source: rewritten` or `source: human`.

**Metrics:** Recall@k, answer correctness, citation exactness, hallucinated citation count, no-answer precision/recall, p50/p95 latency, tool call count, per-query cost estimate.

`run_eval(..., mode="llm-assisted")` reports LLM-specific metrics: estimated
LLM calls/cost, fallback count, timeout count, retry-exhausted count,
schema/parse failure count, invalid unit-ID count, and deterministic validator
rejection count. Deterministic mode remains the release gate owner.

The checked-in governed eval file is `eval/synthetic_mvp_seed.jsonl`. It
contains 80 rewritten questions with zero auto-generated rows and covers all
seven taxonomy categories.

---

## Risk Register

| ID | Risk | Detector | Mitigation |
|---|---|---|---|
| CR-1 | Ingestion fidelity too low | M1 scorecards | Better parser routing, better mappers |
| CR-2 | Sparse recall ceiling too low | M2 recall gap | Terminology → rewrite → reranker → hybrid |
| CR-3 | Mixed Vi-En queries underperform | Mixed-language subset | Alias catalog, folded fields, rewrite |
| CR-4 | Version/provenance logic weak | Versioned test failures | Version graph, metadata enrichment |
| CR-5 | Tool orchestration unstable | M3 trace review | Narrower policy, fewer branches |
| MR-1 | Architecture corpus not representative | Shadow corpus gap | Rebalance corpus |
| MR-2 | Parser license constrained | Legal review | Fallback parser strategy |
| MR-3 | Table-heavy docs degrade quality | Table subset score | Table shadow text + specific mapping |

---

## Failure Review Discipline

For every benchmark failure:
1. Identify the layer: ingestion → retrieval → orchestration → synthesis → evaluation
2. Do not label retrieval failures as "prompt problems" without evidence
3. Do not label versioning failures as "model reasoning issues" without provenance review

## Release Gates

The system may only move to controlled release when:
1. Corpus is registered and provenance-complete
2. Parsing quality is benchmarked for all archetypes
3. Retrieval thresholds are met
4. Citation hallucinations = 0 in final pre-release pass
5. No-answer behavior is verified
6. Shadow corpus is tested
7. Open risks are documented with owners and mitigations
8. Project license is selected and consistent between package metadata and README

The current strict release report is `reports/release_gate.json`, with decision
`go`. The narrative decision report is `reports/release_decision.md`.
