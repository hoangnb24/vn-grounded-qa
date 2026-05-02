# Vietnamese Grounded QA System

Evidence-first document retrieval and question answering for Vietnamese enterprise documentation.

## What this is

A grounded QA system for controlled corpora — PDFs, Markdown, SOPs, legal texts, policies, and knowledge-base materials — that answers questions in Vietnamese with verifiable citations and explicit uncertainty.

The target experience is **not** "helpful chat." It is:

- answers supported by the corpus,
- clear source citations with document/section/page references,
- explicit "insufficient evidence" when the corpus can't justify confidence,
- robust handling of Vietnamese text with light English mixing (acronyms, product terms, module names).

## Architecture

```
Raw Assets → Parsed IR → Canonical Store → Sparse Index → Semantic Tools → Grounded Answer
```

The system is **evidence-first** — not vector-DB-first, not graph-first, not agent-first.

| Layer | What it does |
|---|---|
| Raw Asset Registry | Stores source files with provenance (hash, URI, parser, timestamp) |
| Parsed IR | Parser-neutral intermediate representation (pages, blocks, hierarchy) |
| Canonical Store | Stable retrieval units: `documents`, `content_units`, `relations`, `aliases` |
| Search Index | Sparse FTS with Vietnamese segmentation, alias expansion, field weighting |
| Tool Layer | Bounded semantic tools (`search_units`, `read_units`, `expand_context`, etc.) |
| Answer Contract | Grounded synthesis with citations, confidence labels, no-answer policy |

Key design decisions:

- **Sparse retrieval (SQLite FTS5) as default backbone** — operationally simple, explainable, no vector-DB dependency. Hybrid retrieval is an upgrade path, not a starting assumption.
- **Bounded tool orchestration** — max 6 tool calls per answer, max 2 searches. No open-ended agent loops.
- **Parser-neutral IR** — parsers (Docling, Marker, etc.) can be swapped without rebuilding downstream layers.
- **Vietnamese-aware normalization** — word segmentation (VnCoreNLP), ASCII folding, alias dictionaries as first-class search fields.

See [`docs/ADR-001.md`](docs/ADR-001.md) for the full architecture decision record.
See [`docs/IMPLEMENTATION.md`](docs/IMPLEMENTATION.md) for milestones, schemas, evaluation, and risk.

## Quick orientation

```
docs/
├── ADR-001.md          # Architecture decision record (the "why")
├── IMPLEMENTATION.md   # Milestones, schemas, eval, risk (the "how")
└── COMPLETION_PLAN.md  # Current finish plan and release-gate closure path
```

## Status

**Runnable sparse-first MVP.** The repository now contains the first implementation slice:

- parser-neutral IR for Markdown, text, and optional PDF ingestion,
- canonical SQLite store with `documents`, `content_units`, `relations`, and `aliases`,
- SQLite FTS5 sparse retrieval with Vietnamese normalization, ASCII folding, alias expansion, and table text shadows,
- bounded semantic tool layer with max-call and max-search ceilings,
- grounded extractive answer contract with citations and explicit insufficient-evidence behavior,
- JSONL evaluation harness for retrieval, latency, tool-call, and no-answer checks,
- M0/M1 execution scaffolds: corpus manifest validation and parser bakeoff reports.
- synthetic architecture corpus generation for local gate development.
- default `auto` parser routing through Docling, Marker, then local fallback.
- milestone gate reports for M0 through M6.
- strict MVP eval-set validation and synthetic 80-question eval generation.
- risk-register validation and legal/shadow pack manifest validation.
- governed-input readiness report for release-blocking corpus, eval, pack, risk-owner, and license gaps.

The full milestone program in `docs/IMPLEMENTATION.md` is not complete yet. See
`docs/IMPLEMENTATION_MATRIX.md`, `docs/MILESTONE_ROADMAP.md`, and
`docs/GOVERNED_INPUTS_RUNBOOK.md`, `docs/COMPLETION_PLAN.md`, plus
`reports/completion_audit.md`, for the live gap list, governed-input handoff,
completion audit, and execution order.
The checked-in `eval/synthetic_mvp_seed.jsonl` is a seven-question smoke slice;
use `evalset seed-synthetic` to generate the synthetic 80-question fixture.

## Quick start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'

vn-grounded-qa --db grounded.db init
vn-grounded-qa --db grounded.db ingest docs
vn-grounded-qa --db grounded.db search "sparse retrieval tiếng Việt"
vn-grounded-qa --db grounded.db search "sparse retrieval tiếng Việt" --filter doc_type=technical_markdown
vn-grounded-qa --db grounded.db ask "Hệ thống dùng loại truy xuất nào?"
```

For source-tree smoke tests without installing:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db grounded.db init
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db grounded.db ingest docs
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db grounded.db ask "Hệ thống dùng loại truy xuất nào?"
```

Run tests:

```bash
python3 -m pytest -q
```

Validate the current seed corpus manifest:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus validate corpus/architecture/manifest.json --relaxed
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus validate corpus/architecture/manifest.json
```

The strict command is expected to fail until the M0 architecture corpus contains
24-36 governed documents across all required archetypes.

Run the current fallback parser scorecard:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff fallback corpus/architecture/manifest.json --out reports/m1_fallback_seed.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff parser corpus/architecture/manifest.json --parser auto
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff parser corpus/architecture/manifest.json --parser docling
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff parser corpus/architecture/manifest.json --parser marker
```

Generate and exercise a full synthetic 25-document architecture corpus in a
temporary directory:

```bash
TMPDIR=$(mktemp -d)
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus seed-synthetic "$TMPDIR/architecture/manifest.json"
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-seed-synthetic "$TMPDIR/legal/manifest.json" --type legal_regression
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-seed-synthetic "$TMPDIR/shadow/manifest.json" --type production_shadow
PYTHONPATH=src python3 -m vn_grounded_qa.cli evalset seed-synthetic "$TMPDIR/mvp80.jsonl"
printf 'license = {text = "MIT"}\n' > "$TMPDIR/pyproject.toml"
printf '# Synthetic verification\n\n## License\n\nMIT\n' > "$TMPDIR/README.md"
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db "$TMPDIR/grounded.db" ingest-manifest "$TMPDIR/architecture/manifest.json"
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db "$TMPDIR/grounded.db" eval "$TMPDIR/mvp80.jsonl" --k 10
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m0 --manifest "$TMPDIR/architecture/manifest.json" --out "$TMPDIR/m0_gate.json"
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m1 --manifest "$TMPDIR/architecture/manifest.json" --parser fallback --out "$TMPDIR/m1_gate.json"
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m2 --db "$TMPDIR/grounded.db" --eval "$TMPDIR/mvp80.jsonl" --out "$TMPDIR/m2_gate.json"
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m3 --db "$TMPDIR/grounded.db" --eval "$TMPDIR/mvp80.jsonl" --out "$TMPDIR/m3_gate.json"
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m4 --db "$TMPDIR/grounded.db" --eval "$TMPDIR/mvp80.jsonl" --out "$TMPDIR/m4_gate.json"
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m5 --db "$TMPDIR/grounded.db" --eval "$TMPDIR/mvp80.jsonl" --out "$TMPDIR/m5_gate.json"
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db "$TMPDIR/grounded.db" baselines report --eval "$TMPDIR/mvp80.jsonl" --out "$TMPDIR/m5_baseline_comparison.md"
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m6 --db "$TMPDIR/grounded.db" --base-eval "$TMPDIR/mvp80.jsonl" --scale-eval "$TMPDIR/mvp80.jsonl" --out "$TMPDIR/m6_gate.json"
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates release --manifest "$TMPDIR/architecture/manifest.json" --db "$TMPDIR/grounded.db" --eval "$TMPDIR/mvp80.jsonl" --scale-eval "$TMPDIR/mvp80.jsonl" --legal-pack "$TMPDIR/legal/manifest.json" --shadow-pack "$TMPDIR/shadow/manifest.json" --pyproject "$TMPDIR/pyproject.toml" --readme "$TMPDIR/README.md" --out "$TMPDIR/release_gate.json"
```

For controlled release, add `--strict-risk-owners` after deployment owners have
replaced role placeholders in `docs/RISK_REGISTER.md`, and keep the selected
project license aligned between `pyproject.toml` and this README.

Validate release-supporting governance artifacts:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli evalset validate eval/synthetic_mvp_seed.jsonl --relaxed
PYTHONPATH=src python3 -m vn_grounded_qa.cli risks validate
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-validate corpus/legal-regression/manifest.json --type legal_regression
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-validate corpus/production-shadow/manifest.json --type production_shadow
PYTHONPATH=src python3 -m vn_grounded_qa.cli readiness governed --eval eval/mvp80_governed.jsonl --strict-risk-owners --out reports/governed_readiness.json
```

Write narrative go/revise/stop decision reports from gate JSON:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli decisions report reports/m0_gate.json --out reports/m0_decision.md
PYTHONPATH=src python3 -m vn_grounded_qa.cli decisions report reports/release_gate.json --out reports/release_decision.md
```

Import a domain alias catalog:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db grounded.db alias-import aliases/core.csv
```

This synthetic corpus is for engineering verification only. It does not replace
the governed architecture corpus required for release gates.

## References

- [SQLite FTS5](https://sqlite.org/fts5.html) — sparse retrieval backbone
- [VnCoreNLP](https://aclanthology.org/N18-5012/) — Vietnamese segmentation
- [Docling](https://github.com/docling-project/docling) (MIT) — default document parser
- [Marker](https://github.com/datalab-to/marker) (GPL-3.0) — fallback parser
- [Keyword Search Is All You Need](https://arxiv.org/abs/2602.23368) — sparse retrieval justification
- [LaRA benchmark](https://researchportal.hkust.edu.hk/en/publications/lara-benchmarking-retrieval-augmented-generation-and-long-context/) — RAG vs long-context comparison
- [Vietnamese Legal QA dataset](https://huggingface.co/datasets/thangvip/vietnamese-legal-qa) — public benchmark slice
- [Vietnamese-English Cross-Lingual Retrieval (NAACL 2025)](https://aclanthology.org/2025.naacl-short.12/)
- [DRiLL Vietnamese Legal Retrieval (VLSP 2025)](https://aclanthology.org/2025.vlsp-1.20/)

## License

MIT
