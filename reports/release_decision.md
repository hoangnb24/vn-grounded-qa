# Release Decision Report

**Decision:** `revise`
**Source gate report:** `reports/release_gate.json`

## Passed Checks

- corpus registered and provenance-complete
- parsing benchmarked for all archetypes
- citation hallucinations = 0
- legal regression pack registered
- shadow corpus registered
- open risks documented with owners/mitigations
- project license selected

## Failed Checks and Failure Review

### retrieval thresholds met

- Layer: `retrieval`
- Evidence: `M2=revise`
- Next action: Inspect missed expected units, then tune aliases, segmentation, field weighting, or query handling from observed failures.

### no-answer behavior verified

- Layer: `synthesis`
- Evidence: `0.800`
- Next action: Compare answer text and citations against retrieved units, then adjust support checks or citation selection.

### shadow or scale corpus tested

- Layer: `governance`
- Evidence: `M6=revise`
- Next action: Fill the governed manifest, risk owner, legal pack, shadow-pack, or license evidence required by the release gate.

## Decision Discipline

- Do not label retrieval failures as prompt problems without missed-unit evidence.
- Do not label versioning failures as model reasoning issues without provenance review.
- Re-run the gate after the next action and attach the new JSON report.
