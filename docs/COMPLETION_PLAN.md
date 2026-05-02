# Completion Plan

**Status:** complete; controlled release gate is `go`  
**Last refreshed:** 2026-05-02

This is the completion record for the Vietnamese grounded QA application from
the current codebase state. The strict release gate is now `go` on governed
inputs.

## Success Criteria

The project is complete when all of these are true:

1. `python3 -m pytest -q` passes.
2. Governed input readiness has no blockers.
3. M0-M6 gate reports are `go` against the governed architecture corpus and
   governed 80-question eval set.
4. The aggregate release gate is `go` with strict risk owners and license
   checks enabled.
5. `reports/completion_audit.md` shows no missing, partial, or unverified
   release requirements.

## Current State

Implemented:

- Parser-neutral Markdown/text/PDF ingestion with Docling, Marker, and local
  fallback parser routes.
- Canonical SQLite store with documents, content units, relations, aliases,
  tool traces, and FTS5 sparse retrieval.
- Vietnamese normalization, ASCII folding, identifier extraction, and optional
  external segmentation hook.
- Bounded semantic tools and extractive grounded answer contract.
- Eval-set validation, risk validation, readiness checks, M0-M6 gates, release
  gate, and decision reports.
- Governed architecture, legal regression, and production shadow manifests.

Fresh evidence from the current checkout:

```text
python3 -m pytest -q:
123 passed in 14.29s

corpus/architecture/manifest.json:
29 docs; faq=3, legal=12, policy_sop=7, table_pdf=5, technical_markdown=2

eval/synthetic_mvp_seed.jsonl:
80 questions; auto_generated=0
```

Final gate evidence:

```text
governed readiness: ok; blockers=0
M2 decision: go
single-hop Recall@10: 1.000, target 0.900
multi-hop component Recall@20: 1.000, target 0.800
mixed Vietnamese-English Recall@10: 1.000, target 0.800
search p95: 19.171ms, target <= 400ms

M3 decision: go
avg tool calls: 2.875; p95 tool calls: 3.000

M4 decision: go
answer correctness: 1.000, target 0.750
no-answer precision: 1.000, target 0.900
eval failures: 0

M5 decision: go
M6 decision: go
Release decision: go
```

## Finish Sequence

### Phase 1 — Retrieval Closure

Status: done. M2 is `go` without weakening the documented thresholds.

Work:

- Add failure-focused query expansion for procedure codes, legal identifiers,
  form identifiers, time-limit questions, channel/submission questions, and
  multi-document "nguồn nào" questions.
- Add document-family and source-title boosts so a query containing a procedure
  code such as `DVC 1.010101` cannot be crowded out by nearby generic DVC
  sources.
- Keep metadata/acquisition/provenance units searchable but below answer-bearing
  body facts.
- Add regression tests for every retrieval class that currently fails.

Done when:

```bash
rm -f /tmp/vn_grounded_qa_release.db
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db /tmp/vn_grounded_qa_release.db init
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db /tmp/vn_grounded_qa_release.db ingest-manifest corpus/architecture/manifest.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m2 --db /tmp/vn_grounded_qa_release.db --eval eval/synthetic_mvp_seed.jsonl --out reports/m2_gate.json
```

returns M2 `go`.

### Phase 2 — Answer Contract Closure

Status: done. M4 is `go` after retrieval closure.

Work:

- Use heading/title context in support checks without letting generic document
  titles answer unsupported questions.
- Improve no-answer filtering so out-of-corpus questions remain insufficient
  after retrieval recall improves.
- Improve extractive synthesis for multi-hop and multi-document rows so answer
  text includes the expected grounded points from selected evidence.
- Add citation-exactness tests for selected units and answer-contract tests for
  no-answer boundaries.

Done when:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m4 --db /tmp/vn_grounded_qa_release.db --eval eval/synthetic_mvp_seed.jsonl --out reports/m4_gate.json
```

returns M4 `go`.

### Phase 3 — Scale And Baseline Closure

Status: done. M5 and M6 are `go`.

Work:

- Re-run the thin RAG baseline after M4 is passing and refresh
  `reports/m5_baseline_comparison.md`.
- Run M6 with the production shadow pack or a distinct scale eval, not just the
  base eval reused as a proxy.
- Fix provenance/version errors surfaced by M6, especially effective-window and
  historical/current legal-source questions.

Done when:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m5 --db /tmp/vn_grounded_qa_release.db --eval eval/synthetic_mvp_seed.jsonl --out reports/m5_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates m6 --db /tmp/vn_grounded_qa_release.db --base-eval eval/synthetic_mvp_seed.jsonl --scale-eval eval/synthetic_mvp_seed.jsonl --out reports/m6_gate.json
```

return `go`, or M5 contains an evidence-backed sparse-vs-baseline gap decision.

### Phase 4 — Release Audit Closure

Status: done. The project has a strict, reproducible release `go` decision.

Work:

- Run governed readiness, M0-M6, and aggregate release gate.
- Refresh `reports/completion_audit.md` from the final gate outputs.
- Generate final decision reports from gate JSON.

Done when:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli readiness governed --eval eval/synthetic_mvp_seed.jsonl --strict-risk-owners --out reports/governed_readiness.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli gates release --manifest corpus/architecture/manifest.json --db /tmp/vn_grounded_qa_release.db --eval eval/synthetic_mvp_seed.jsonl --scale-eval eval/synthetic_mvp_seed.jsonl --legal-pack corpus/legal-regression/manifest.json --shadow-pack corpus/production-shadow/manifest.json --strict-risk-owners --pyproject pyproject.toml --readme README.md --out reports/release_gate.json
PYTHONPATH=src python3 -m vn_grounded_qa.cli decisions report reports/release_gate.json --out reports/release_decision.md
python3 -m pytest -q
```

returns a release `go` and all tests pass.

## Final State

No completion blocker remains in the governed release path. Remaining future
work is production hardening only, especially replacing TVPL-derived summaries
with original/current legal source files where redistribution requires it.
