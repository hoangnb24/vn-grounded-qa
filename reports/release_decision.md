# Release Decision Report

**Decision:** `go`
**Source gate report:** `reports/release_gate.json`

## Passed Checks

- corpus registered and provenance-complete
- parsing benchmarked for all archetypes
- retrieval thresholds met
- citation hallucinations = 0
- no-answer behavior verified
- legal regression pack registered
- shadow corpus registered
- shadow or scale corpus tested
- open risks documented with deployment owners/mitigations
- project license selected

## Failed Checks and Failure Review

- None
## Decision Discipline

- Do not label retrieval failures as prompt problems without missed-unit evidence.
- Do not label versioning failures as model reasoning issues without provenance review.
- Re-run the gate after the next action and attach the new JSON report.
