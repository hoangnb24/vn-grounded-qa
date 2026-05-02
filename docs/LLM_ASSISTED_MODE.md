# LLM-Assisted Mode

LLM-assisted mode is a bounded Google Gemini layer beside the deterministic
answer path. It handles semantic judgment, not autonomous tool use.

## Status

Default mode remains `deterministic`. `llm-assisted` is experimental until it
matches or beats deterministic mode on citation exactness, hallucinated citation
count, no-answer precision, and answer-contract validity over the same eval set.

## Architecture

Flow:

1. `plan_query(question)` returns a `QueryPlan`.
2. Deterministic `resolve_terms` and `search_units` retrieve candidates.
3. `judge_evidence(question, hits)` returns an `EvidenceDecision`.
4. Only `required_unit_ids` are read with `read_units`.
5. `compose_answer(question, units, decision)` returns an `AnswerDraft`.
6. Citations are built locally from read units.
7. The answer contract is validated locally before returning.

The LLM never receives permission to call external tools and automatic Gemini
function calling is not enabled.

## Provider

Live provider calls use optional dependencies:

```bash
pip install -e '.[llm]'
```

Gemini Developer API:

```bash
export VN_GROUNDED_QA_LLM_PROVIDER=google
export VN_GROUNDED_QA_LLM_MODEL=gemini-2.5-flash
export VN_GROUNDED_QA_LLM_TIMEOUT_MS=30000
export VN_GROUNDED_QA_LLM_RETRY_ATTEMPTS=2
export GEMINI_API_KEY=...
```

Vertex AI:

```bash
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT=...
export GOOGLE_CLOUD_LOCATION=...
```

## Safety Model

- LLM output is validated with strict Pydantic models.
- Extra fields are rejected.
- List sizes and enum values are bounded.
- Returned unit IDs must exactly match retrieved/read unit IDs.
- Unknown IDs are rejected; there is no fuzzy matching.
- Citations are generated only from read units.
- If evidence is insufficient, contradictory, or version-unclear, the final
  answer is insufficient.
- If deterministic support checks reject the LLM decision or draft, the system
  falls back to deterministic mode.

Failure metadata uses these types when relevant:

- `llm_dependency_missing`
- `llm_auth_missing`
- `llm_timeout`
- `llm_retry_exhausted`
- `llm_invalid_json`
- `llm_schema_validation_failed`
- `llm_unknown_unit_id`
- `llm_answer_contract_violation`
- `llm_deterministic_validator_rejected`

## Commands

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db grounded.db ask "Câu hỏi?" --mode deterministic
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db grounded.db ask "Câu hỏi?" --mode llm-assisted

PYTHONPATH=src python3 -m vn_grounded_qa.cli --db grounded.db eval eval/synthetic_mvp_seed.jsonl --mode deterministic
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db grounded.db eval eval/synthetic_mvp_seed.jsonl --mode llm-assisted
```

Unit tests cover the LLM path with fake provider responses and do not require a
Gemini key. Eval output reports LLM calls, fallback count, timeout and
retry-exhausted counts, schema/parse failures, invalid unit-ID references, and
deterministic validator rejections separately from deterministic metrics.
