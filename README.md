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

## Quick Orientation

```
docs/
├── ADR-001.md          # Architecture decision record (the "why")
├── IMPLEMENTATION.md   # Milestones, schemas, eval, risk (the "how")
└── COMPLETION_PLAN.md  # Governed completion record and release-gate commands
```

## Status

**Governed sparse-first MVP.** The repository contains a complete local
implementation and a strict governed release record:

- parser-neutral IR for Markdown, text, and optional PDF ingestion,
- `auto`, `fallback`, `docling`, and `marker` parser routes,
- canonical SQLite store with `documents`, `content_units`, `relations`,
  `aliases`, and `tool_traces`,
- SQLite FTS5 sparse retrieval with Vietnamese normalization, ASCII folding,
  governed alias expansion, identifier-aware routing, metadata filters, and
  source-pair routing for DVC/TVPL synthesis questions,
- bounded semantic tool layer with max-call and max-search ceilings,
- grounded extractive answer contract with source-facing citation anchors,
  confidence labels, contradiction checks, version checks, and explicit
  insufficient-evidence behavior,
- authored 80-question MVP eval set across seven taxonomy categories,
- JSONL evaluation harness for retrieval, answer correctness, citation
  exactness, no-answer behavior, latency, tool-call, and cost metrics,
- architecture corpus, legal regression pack, and production shadow pack
  manifests backed by local governed sources,
- M0-M6 gate reports, thin-RAG baseline comparison, governed readiness report,
  and strict aggregate release report,
- risk-register validation, strict deployment-owner checks, and MIT project
  license validation.

Current release evidence lives in `reports/`:

| Artifact | Current result |
|---|---|
| `reports/governed_readiness.json` | `ok: true`, blockers `0` |
| `reports/m2_gate.json` | retrieval `go`, Recall@10/20 checks `1.000` |
| `reports/m3_gate.json` | bounded tool orchestration `go` |
| `reports/m4_gate.json` | answer correctness `1.000`, no-answer precision `1.000` |
| `reports/m5_gate.json` | sparse baseline comparison `go` |
| `reports/m6_gate.json` | scale/provenance gate `go` |
| `reports/release_gate.json` | strict release `go` |

See `reports/completion_audit.md` for the requirement-by-requirement release
audit and `docs/COMPLETION_PLAN.md` for the reproducible completion command
sequence.

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

Validate the architecture corpus manifest:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus validate corpus/architecture/manifest.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus validate corpus/architecture/manifest.json --relaxed
```

Run parser scorecards:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff parser corpus/architecture/manifest.json --parser auto
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff parser corpus/architecture/manifest.json --parser fallback
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff parser corpus/architecture/manifest.json --parser docling
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff parser corpus/architecture/manifest.json --parser marker
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff fallback corpus/architecture/manifest.json --out reports/m1_fallback_seed.json
```

Ingest the governed corpus and run the release gate ladder:

```bash
GOVERNED_DB="governed.db"
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db "$GOVERNED_DB" init
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db "$GOVERNED_DB" ingest-manifest corpus/architecture/manifest.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db "$GOVERNED_DB" eval eval/synthetic_mvp_seed.jsonl --k 10

PYTHONPATH=src python3 -m vn_grounded_qa.cli readiness governed --eval eval/synthetic_mvp_seed.jsonl --strict-risk-owners --out reports/governed_readiness.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m0 --manifest corpus/architecture/manifest.json --out reports/m0_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m1 --manifest corpus/architecture/manifest.json --parser auto --out reports/m1_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m2 --db "$GOVERNED_DB" --eval eval/synthetic_mvp_seed.jsonl --out reports/m2_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m3 --db "$GOVERNED_DB" --eval eval/synthetic_mvp_seed.jsonl --out reports/m3_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m4 --db "$GOVERNED_DB" --eval eval/synthetic_mvp_seed.jsonl --out reports/m4_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m5 --db "$GOVERNED_DB" --eval eval/synthetic_mvp_seed.jsonl --out reports/m5_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m6 --db "$GOVERNED_DB" --base-eval eval/synthetic_mvp_seed.jsonl --scale-eval eval/synthetic_mvp_seed.jsonl --out reports/m6_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates release --manifest corpus/architecture/manifest.json --db "$GOVERNED_DB" --eval eval/synthetic_mvp_seed.jsonl --scale-eval eval/synthetic_mvp_seed.jsonl --legal-pack corpus/legal-regression/manifest.json --shadow-pack corpus/production-shadow/manifest.json --strict-risk-owners --pyproject pyproject.toml --readme README.md --out reports/release_gate.json
```

Validate release-supporting governance artifacts:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli evalset validate eval/synthetic_mvp_seed.jsonl
PYTHONPATH=src python3 -m vn_grounded_qa.cli risks validate --strict-owners
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-validate corpus/legal-regression/manifest.json --type legal_regression
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-validate corpus/production-shadow/manifest.json --type production_shadow
PYTHONPATH=src python3 -m vn_grounded_qa.cli readiness governed --eval eval/synthetic_mvp_seed.jsonl --strict-risk-owners --out reports/governed_readiness.json
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

Generate synthetic fixtures for local engineering experiments:

```bash
TMPDIR=$(mktemp -d)
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus seed-synthetic "$TMPDIR/architecture/manifest.json" --docs-per-archetype 5
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-seed-synthetic "$TMPDIR/legal/manifest.json" --type legal_regression
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-seed-synthetic "$TMPDIR/shadow/manifest.json" --type production_shadow
PYTHONPATH=src python3 -m vn_grounded_qa.cli evalset seed-synthetic "$TMPDIR/mvp80.jsonl"
```

## CLI Reference

Global option:

- `--db PATH`: SQLite database path, default `grounded.db`

Core commands:

- `init`: create or migrate the SQLite schema.
- `schema`: print schema metadata.
- `ingest PATH... --parser {auto,fallback,docling,marker}`: ingest files or
  directories.
- `ingest-manifest MANIFEST --parser {auto,fallback,docling,marker}`: ingest
  all files registered in a corpus manifest.
- `alias SURFACE CANONICAL --domain DOMAIN --type TYPE`: add a term alias.
- `alias-import CSV`: import aliases from a CSV catalog.
- `search QUERY --top-k N --filter KEY=VALUE`: search evidence units. Filters
  support `doc_id`, `doc_family_id`, `doc_type`, `status`, and
  `version_label`.
- `ask QUESTION --top-k N --trace-id ID`: answer with citations and optionally
  persist tool calls under a trace ID.
- `eval EXAMPLES --k N`: run retrieval and answer evaluation over JSONL rows.

Governance and eval commands:

- `evalset validate EXAMPLES --taxonomy PATH --relaxed`
- `evalset seed-synthetic EXAMPLES`
- `risks validate --path PATH --strict-owners`
- `readiness governed --manifest PATH --eval PATH --taxonomy PATH
  --legal-pack PATH --shadow-pack PATH --risk-register PATH --pyproject PATH
  --readme PATH --strict-risk-owners --out PATH`

Corpus and parser commands:

- `corpus validate MANIFEST --relaxed`
- `corpus template MANIFEST`
- `corpus seed-synthetic MANIFEST --docs-per-archetype N`
- `corpus pack-template MANIFEST --type {legal_regression,production_shadow}`
- `corpus pack-validate MANIFEST --type {legal_regression,production_shadow}`
- `corpus pack-seed-synthetic MANIFEST --type {legal_regression,production_shadow}`
- `bakeoff parser MANIFEST --parser {auto,fallback,docling,marker} --out PATH`
- `bakeoff fallback MANIFEST --out PATH`

Gate, trace, and report commands:

- `gates m0 --manifest PATH --taxonomy PATH --out PATH`
- `gates m1 --manifest PATH --parser {auto,fallback,docling,marker} --out PATH`
- `gates m2|m3|m4|m5 --db PATH --eval PATH --out PATH`
- `gates m6 --db PATH --base-eval PATH --scale-eval PATH --out PATH`
- `gates release --manifest PATH --db PATH --eval PATH --scale-eval PATH
  --parser {auto,fallback,docling,marker} --legal-pack PATH --shadow-pack PATH
  --pyproject PATH --readme PATH --strict-risk-owners --out PATH`
- `decisions report GATE_JSON --out PATH --stop-reason TEXT`
- `traces list`
- `traces show TRACE_ID`
- `baselines report --eval PATH --out PATH`

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
