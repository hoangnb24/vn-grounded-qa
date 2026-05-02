# M1 Decision Report

**Decision:** `revise`
**Source gate report:** `reports/m1_gate.json`

## Passed Checks

- auto parser bakeoff
- parse success >= 90%
- heading path recovery >= 85%
- provenance completeness = 100%

## Failed Checks and Failure Review

### architecture corpus ready

- Layer: `ingestion`
- Evidence: `corpus/architecture/manifest.json`
- Next action: Fix corpus registration, parser output, heading recovery, or provenance before retesting downstream layers.
- Details:
  - M0 architecture corpus must contain 24-36 documents; found 2
  - M0 architecture corpus missing archetypes: faq, legal, policy_sop, table_pdf

## Decision Discipline

- Do not label retrieval failures as prompt problems without missed-unit evidence.
- Do not label versioning failures as model reasoning issues without provenance review.
- Re-run the gate after the next action and attach the new JSON report.
