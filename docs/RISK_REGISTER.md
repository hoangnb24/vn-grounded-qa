# Risk Register

This file expands the implementation-plan risks with explicit ownership and
status. Deployment ownership is assigned to team Kieng for the current
controlled-release readiness track.

| ID | Risk | Detector | Mitigation | Owner | Status |
|---|---|---|---|---|---|
| CR-1 | Ingestion fidelity too low | M1 parser scorecards | Better parser routing, better mappers | Kieng | open |
| CR-2 | Sparse recall ceiling too low | M2 recall gap | Terminology, rewrite, reranker, hybrid | Kieng | open |
| CR-3 | Mixed Vi-En queries underperform | Mixed-language subset | Alias catalog, folded fields, rewrite | Kieng | open |
| CR-4 | Version/provenance logic weak | Versioned test failures | Version graph, metadata enrichment | Kieng | open |
| CR-5 | Tool orchestration unstable | M3 trace review | Narrower policy, fewer branches | Kieng | open |
| MR-1 | Architecture corpus not representative | Shadow corpus gap | Rebalance corpus | Kieng | open |
| MR-2 | Parser license constrained | Legal review | Fallback parser strategy | Kieng | open |
| MR-3 | Table-heavy docs degrade quality | Table subset score | Table shadow text and specific mapping | Kieng | open |

Allowed statuses: `open`, `mitigating`, `accepted`, `closed`.

Release gate rule: every risk must have a non-empty owner and mitigation, and
status must be one of the allowed statuses.

Strict owner check for controlled release:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli risks validate --strict-owners
```

This mode rejects placeholder role owners such as `Governance owner`; the
current named owner for all entries is `Kieng`.
