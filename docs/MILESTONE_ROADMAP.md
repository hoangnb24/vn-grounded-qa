# Milestone Roadmap

The implementation docs define a gated program. The right execution order is
not "add model logic first"; it is to build the measurement surfaces that make
each later implementation defensible.

## Working Rule

No milestone is complete until it has:

1. A concrete artifact in the repo.
2. A repeatable command or report.
3. A go / revise / stop decision.
4. Evidence that the milestone gate actually covers the documented requirement.

## Phase 1 — Make M0 Real

Goal: freeze what this system is allowed to be judged against.

Deliverables:

- `docs/M0_SCOPE.md`
- `eval/taxonomy.yaml`
- `corpus/architecture/manifest.json`
- `reports/m0_decision.md`

Exit gate:

- 24-36 architecture documents are registered across legal, SOP, technical
  Markdown, table-heavy PDF, and FAQ archetypes.
- Every document has source URI, expected archetype, owner, license/provenance,
  and status.
- The evaluation taxonomy is stable enough to author concrete questions.

## Phase 2 — M1 Ingestion Quality

Goal: prove documents become trustworthy units before optimizing retrieval.

Deliverables:

- Parser adapter interface with `docling`, `marker`, and local fallback routes.
- Parser bakeoff runner.
- Parser scorecard report by archetype.
- Provenance completeness verifier.

Exit gate:

- Parse success without fatal failure >= 90%.
- Usable heading path recovery >= 85%.
- Provenance completeness = 100%.

## Phase 3 — M2 Retrieval Baseline

Goal: prove sparse retrieval can recover evidence.

Deliverables:

- VnCoreNLP segmentation adapter or documented fallback mode.
- Alias catalog and import command.
- Retrieval eval JSONL.
- Latency and recall report.

Exit gate:

- Single-hop Recall@10 >= 0.90.
- Multi-hop component Recall@20 >= 0.80.
- Mixed Vietnamese-English Recall@10 >= 0.80.
- Search-only p95 <= 400ms.

## Phase 4 — M3/M4 Answering

Goal: prove bounded tool use produces grounded answers.

Deliverables:

- Persistent trace logging.
- E2E eval set with 80 questions across 7 categories.
- Citation exactness verifier.
- No-answer verifier.
- Full-pipeline latency report.

Exit gate:

- Avg tool calls <= 4 and p95 <= 6.
- Argument error rate < 2%.
- Infinite loop rate = 0.
- Answer correctness >= 75%.
- Citation exactness >= 95%.
- Hallucinated citations = 0.
- No-answer precision >= 90%.
- Full-pipeline p95 <= 8s.

## Phase 5 — M5/M6 Decision Work

Goal: decide whether sparse-first remains justified.

Deliverables:

- Thin RAG baseline.
- Larger scale pack.
- Legal regression pack.
- Upgrade decision report.

Exit gate:

- Sparse + bounded tools reaches >= 85% of thin RAG correctness, or the gap is
  explained with evidence.
- Quality drop <= 5 points on larger packs.
- Pipeline p95 <= 10s.
- Provenance/version errors = 0 on curated legal/policy tests.

## Immediate Next Implementation Sequence

1. Replace the two-document seed architecture manifest with 24-36 governed
   documents across legal, SOP, technical Markdown, table-heavy PDF, and FAQ
   archetypes.
2. Add governed legal regression and production shadow documents with the
   required coverage tags.
3. Author or substantively rewrite `eval/mvp80_governed.jsonl` so it contains
   80 scored questions across the taxonomy and no more than 40 percent
   auto-generated rows.
4. Replace role-owner placeholders in `docs/RISK_REGISTER.md` with named
   deployment owners.
5. Run `docs/GOVERNED_INPUTS_RUNBOOK.md` end to end and keep iterating until
   the strict release gate is `go`.
