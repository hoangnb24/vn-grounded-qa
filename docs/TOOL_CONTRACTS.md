# Tool Contracts

The tool layer is deliberately bounded. It is not an open-ended agent loop.

## Limits

- Max total calls per answer: 6
- Max search calls per answer: 2
- Max context expansion depth: 1

## Trace Review

Persist tool traces by passing a trace ID to `ask`:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db grounded.db ask "Câu hỏi?" --trace-id review-001
```

Inspect persisted traces:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db grounded.db traces list
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db grounded.db traces show review-001
```

Trace rows include the tool name, call index, parsed arguments, result count,
and timestamp. Use them for M3 argument-error, repeated-search, and call-ceiling
review.

## Tools

### `search_units`

Find candidate evidence units.

Arguments:

- `query`: user query or rewritten query string
- `top_k`: requested result count, capped by the implementation
- `doc_type`: optional document/archetype filter
- `filters`: optional object supporting `doc_id`, `doc_family_id`, `doc_type`,
  `status`, and `version_label`

Returns: ranked evidence-unit summaries with document title, heading path, page
range, raw text, and score.

CLI:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db grounded.db search "Câu hỏi?" --filter doc_type=policy --filter status=active
```

### `read_units`

Read selected evidence units in full.

Arguments:

- `unit_ids`: list of unit IDs

Returns: full evidence units with citation anchors.

### `expand_context`

Follow structural relations around a unit.

Arguments:

- `unit_id`: starting unit
- `depth`: capped to 1

Returns: related units through `previous`, `next`, `parent`, `child`, and
`references` relations.

### `get_document`

Retrieve document metadata.

Arguments:

- `doc_id`: document ID

Returns: document metadata plus an `outline` list of stored heading paths, or
`null`.

### `resolve_terms`

Resolve aliases, acronyms, and mixed Vietnamese-English terms.

Arguments:

- `query`: query text

Returns: matched alias/canonical terms.

### `get_applicable_version`

Resolve the active version for a document family.

Arguments:

- `doc_family_id`: document family ID
- `as_of`: optional ISO date

Returns: active document metadata or `null`.

## LLM-Assisted Pseudo-Tools

`--mode llm-assisted` records LLM metadata entries in
`GroundedAnswer.tool_calls` so eval reports can count provider behavior without
letting Gemini call repository tools.

Possible entries:

- `llm.plan_query`
- `llm.judge_evidence`
- `llm.compose_answer`
- `llm.fallback`
- `llm.dependency`

Arguments include provider, model, timeout, retry attempts, schema name,
fallback path, and failure type when present. API keys and full prompts are not
persisted.

The real retrieval/read tools remain deterministic Python calls. LLM-assisted
mode does not enable automatic function calling or external provider tools.
