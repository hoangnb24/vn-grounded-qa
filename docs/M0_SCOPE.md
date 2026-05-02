# M0 Scope Freeze

## Product Scope

Vietnamese Grounded QA is an evidence-first question answering system for
controlled enterprise corpora. It answers in Vietnamese from registered source
documents and returns citations to retrievable evidence units.

The system is judged on whether answers are supported by the corpus, whether
citations are exact, whether missing evidence is handled honestly, and whether
retrieval remains explainable.

## Supported Document Archetypes

M0 requires the architecture corpus to include all five archetypes below:

| Archetype | Expected unit shape | Example evidence boundary |
|---|---|---|
| Legal | article / clause / point | Article 5, Clause 2, Point a |
| Policy or SOP | section / subsection / step | Approval step or policy rule |
| Technical Markdown | heading block / paragraph / code block | Section under a stable heading |
| Table-heavy PDF | table plus searchable text shadow | Row or table with header mapping |
| FAQ | question-answer item | One FAQ pair |

## In Scope

- Parser-neutral ingestion into Parsed IR.
- Canonical document and content-unit storage with provenance.
- Sparse SQLite FTS5 retrieval as the default backbone.
- Vietnamese normalization, segmentation, ASCII folding, aliases, identifiers,
  and short-code matching.
- Bounded semantic tools for search, reading, context expansion, term
  resolution, document lookup, and applicable version lookup.
- Grounded answer synthesis with citations, confidence labels, and no-answer
  behavior.
- Evaluation reports for ingestion, retrieval, tool use, answering, latency,
  and release gates.

## Non-Goals

- No vector database as a required dependency.
- No open-ended agent loop.
- No GraphRAG or full knowledge graph as a starting requirement.
- No whole-corpus stuffing as the primary answering method.
- No production release before the documented release gates are met.
- No claim that fallback tokenization is equivalent to VnCoreNLP segmentation.

## Answer Contract Draft

Every answer object must include:

```json
{
  "answer": "string",
  "citations": [
    {
      "unit_id": "string",
      "doc_id": "string",
      "title": "string",
      "heading_path": "string",
      "page_start": 1,
      "page_end": 1
    }
  ],
  "confidence_label": "high|medium|low|insufficient",
  "insufficient_evidence": false,
  "used_doc_ids": ["string"],
  "used_unit_ids": ["string"],
  "tool_calls": []
}
```

## No-Answer Policy

The system must return insufficient evidence when:

- retrieved units do not support the conclusion,
- evidence is contradictory,
- applicable document version is unclear,
- the question is outside the registered corpus,
- citations cannot be tied to stored units.

When `insufficient_evidence` is `true`, `confidence_label` must be
`insufficient`; supported answers must not use the `insufficient` confidence
label.

Every citation `unit_id` must be present in `used_unit_ids`; every citation
`doc_id` must be present in `used_doc_ids`.

Supported answers must include at least one citation, one used unit, and one
used document.

## M0 Exit Decision Template

M0 can only close when:

- `corpus/architecture/manifest.json` contains 24-36 registered documents,
- all five archetypes are represented,
- every registered document has provenance fields,
- `eval/taxonomy.yaml` is present and reviewed,
- the M0 decision report says `go`, `revise`, or `stop`.
