# Milestone Roadmap

The implementation docs define a gated sparse-first program. Each milestone has
a concrete repo artifact, a repeatable command, a gate report, and a
go/revise/stop decision surface.

## Working Rule

No milestone is complete until it has:

1. A concrete artifact in the repo.
2. A repeatable command or report.
3. A go / revise / stop decision.
4. Evidence that the milestone gate covers the documented requirement.

The governed MVP satisfies this rule through `reports/m2_gate.json` through
`reports/m6_gate.json`, `reports/governed_readiness.json`, and
`reports/release_gate.json`.

## Phase 1 — M0 Scope Freeze

Goal: freeze what the system is judged against.

Deliverables:

- `docs/M0_SCOPE.md`
- `eval/taxonomy.yaml`
- `corpus/architecture/manifest.json`
- `reports/m0_decision.md`

Gate evidence:

- 29 architecture documents are registered across legal, SOP, technical
  Markdown, table-heavy PDF, and FAQ archetypes.
- Every architecture document includes source URI, archetype, owner,
  license/provenance, and status metadata.
- The evaluation taxonomy defines seven scored categories for the MVP eval set.

## Phase 2 — M1 Ingestion Quality

Goal: prove documents become trustworthy units before optimizing retrieval.

Deliverables:

- Parser adapter routes for `auto`, `fallback`, `docling`, and `marker`.
- Parser bakeoff runner.
- Parser scorecard report by archetype.
- Provenance completeness verifier.

Gate evidence:

- `reports/m1_gate.json`
- Aggregate release report records M1 as `go`.
- Parser scorecards run through `vn-grounded-qa bakeoff parser`.

## Phase 3 — M2 Retrieval Baseline

Goal: prove sparse retrieval recovers evidence.

Deliverables:

- Vietnamese normalization and optional external segmentation hook.
- Governed alias catalog in `aliases/core.csv`.
- Identifier-aware DVC/TVPL retrieval.
- Source-pair routing for multi-document DVC/TVPL questions.
- Retrieval eval JSONL with latency and recall metrics.

Gate evidence:

- `reports/m2_gate.json`
- Single-hop Recall@10: `1.000`
- Multi-hop component Recall@20: `1.000`
- Mixed Vietnamese-English Recall@10: `1.000`
- Search-only p95: `19.171ms`

## Phase 4 — M3/M4 Answering

Goal: prove bounded tool use produces grounded answers.

Deliverables:

- Persistent trace logging.
- E2E eval set with 80 questions across seven categories.
- Citation exactness verifier.
- No-answer verifier.
- Full-pipeline latency report.

Gate evidence:

- `reports/m3_gate.json`
- `reports/m4_gate.json`
- Avg tool calls: `2.875`; p95 tool calls: `3.000`
- Argument error rate: `0.000`
- Infinite loop rate: `0.000`
- Answer correctness: `1.000`
- Citation exactness: `1.000`
- Hallucinated citations: `0`
- No-answer precision: `1.000`
- Full-pipeline p95: `22.954ms`

## Phase 5 — M5/M6 Decision Work

Goal: decide whether sparse-first remains justified.

Deliverables:

- Thin RAG baseline comparison.
- Legal regression pack.
- Production shadow pack.
- Scale and upgrade-decision gate.

Gate evidence:

- `reports/m5_gate.json`
- `reports/m6_gate.json`
- Sparse/baseline correctness ratio: `1.404`
- Scale quality drop: `0.000`
- M6 pipeline p95: `22.927ms`
- Provenance/version errors: `0`

## Release Path

The strict release path uses the governed corpus, governed eval set, legal
regression pack, production shadow pack, deployment-owned risk register, and
MIT license metadata.

```bash
GOVERNED_DB="governed.db"
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db "$GOVERNED_DB" init
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db "$GOVERNED_DB" ingest-manifest corpus/architecture/manifest.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli readiness governed --eval eval/synthetic_mvp_seed.jsonl --strict-risk-owners --out reports/governed_readiness.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates release --manifest corpus/architecture/manifest.json --db "$GOVERNED_DB" --eval eval/synthetic_mvp_seed.jsonl --scale-eval eval/synthetic_mvp_seed.jsonl --legal-pack corpus/legal-regression/manifest.json --shadow-pack corpus/production-shadow/manifest.json --strict-risk-owners --pyproject pyproject.toml --readme README.md --out reports/release_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli decisions report reports/release_gate.json --out reports/release_decision.md
```

The current release decision is `go`.

## Upgrade Sequence

Future work follows the ADR upgrade order when gate evidence justifies extra
complexity:

1. Terminology and alias enrichment.
2. Query rewrite.
3. Local reranker.
4. Evidence graph.
5. Version graph.
6. Hybrid neural retrieval.
