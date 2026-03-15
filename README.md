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
└── IMPLEMENTATION.md   # Milestones, schemas, eval, risk (the "how")
```

## Status

**Pre-implementation.** Architecture is frozen. Next step: M0 scope freeze → M1 parser bakeoff on a 24–36 document architecture corpus.

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

TBD
