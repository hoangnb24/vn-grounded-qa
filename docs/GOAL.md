# Improve Vietnamese Grounded QA With Google Gemini LLM Assistance

  ## Objective

  Improve the `vn-grounded-qa` system by adding a bounded, contract-first LLM-
  assisted layer using Google Gemini. The goal is to reduce brittle hardcoded
  regex / keyword / heuristic logic while preserving the system’s strongest
  guarantees: evidence-grounded answers, exact citations, reproducible eval
  gates, and deterministic no-answer behavior.

  Success means the system can use an LLM for semantic judgment without
  allowing the LLM to invent documents, citations, unsupported claims, or
  uncontrolled tool loops.

  ## Context

  Repository: `/Users/themrb/Documents/personal/vn-grounded-qa`

  This repo is an evidence-first Vietnamese documentation QA system. It
  currently uses:

  - SQLite FTS5 sparse retrieval
  - parser-neutral document ingestion
  - canonical `documents`, `content_units`, `relations`, and `aliases`
  - bounded semantic tools in `src/vn_grounded_qa/tools.py`
  - answer synthesis in `src/vn_grounded_qa/answer.py`
  - eval and gate harnesses in `src/vn_grounded_qa/eval.py` and `src/
  vn_grounded_qa/gates.py`

  Important design constraints:

  - Do not replace sparse retrieval wholesale.
  - Do not add an open-ended agent loop.
  - Do not allow LLM-generated citations.
  - LLM output must be structured JSON and validated.
  - The deterministic answer contract remains authoritative.
  - Google provider is preferred.

  Known weak spots from brainstorming:

  - `src/vn_grounded_qa/answer.py`
    - `STOP_TERMS`
    - `NEGATIVE_POLICY_PATTERNS`
    - `POSITIVE_POLICY_PATTERNS`
    - `UNSUPPORTED_DOMAIN_PATTERNS`
    - `has_sufficient_support`
    - `has_contradictory_evidence`
    - `select_supporting_hits`
    - `synthesize_extract`

  - `src/vn_grounded_qa/store.py`
    - `heuristic_relation_types`
    - `referenced_units`
    - `query_identifiers`
    - `identifier_search_patterns`
    - `source_pair_doc_ids`
    - `rerank_hits`

  These are semantic reasoning problems currently handled by rigid rules.

  Preferred libraries:

  - `google-genai`
  - `pydantic`

  Use Google Gemini structured output mode through JSON Schema / Pydantic
  models.

  ## Work Style

  Start with repo inspection before coding. Keep changes incremental and
  reversible.

  Think in layers:

  1. Retrieval remains deterministic.
  2. LLM helps understand the query.
  3. LLM helps judge evidence.
  4. LLM helps compose Vietnamese answers.
  5. Deterministic validation decides whether the answer is allowed.

  Do not make LLM-assisted mode the default immediately. Add it as a parallel
  mode first, compare against current behavior, then recommend whether it
  should become default.

  ## Tool Rules

  Before implementation:

  1. Inspect:
     - `pyproject.toml`
     - `src/vn_grounded_qa/answer.py`
     - `src/vn_grounded_qa/store.py`
     - `src/vn_grounded_qa/tools.py`
     - `src/vn_grounded_qa/models.py`
     - `src/vn_grounded_qa/eval.py`
     - `src/vn_grounded_qa/gates.py`
     - `docs/ANSWER_CONTRACT.schema.json`
     - `eval/taxonomy.yaml`

  2. Check existing tests around:
     - answer contract
     - no-answer behavior
     - citation exactness
     - retrieval
     - source-pair routing
     - relation heuristics

  3. Use current repo patterns. Avoid adding LangChain, LlamaIndex, or broad
  orchestration frameworks unless a concrete repo-specific need appears.

  ## Proposed Architecture

  Add a bounded LLM layer with these modules:

  ```text
  src/vn_grounded_qa/llm.py
  src/vn_grounded_qa/semantic.py
  src/vn_grounded_qa/semantic_models.py
  ```

  ### llm.py

  Create a small Google provider adapter.

  Requirements:

  - use google-genai
  - support Gemini Developer API via GEMINI_API_KEY
  - leave room for Vertex AI via:
      - GOOGLE_GENAI_USE_VERTEXAI
      - GOOGLE_CLOUD_PROJECT
      - GOOGLE_CLOUD_LOCATION
  - configure bounded network behavior with Google GenAI HTTP options:
      - request timeout in milliseconds
      - retry attempts for transient 408 / 429 / 5xx failures
      - no unbounded retry loops
  - use `response_mime_type="application/json"` plus either:
      - `response_schema=<PydanticModel>` when relying on SDK parsing, or
      - `response_json_schema=<model.model_json_schema()>` followed by explicit
        `model_validate_json(response.text)`
  - keep prompts free of duplicated JSON examples when the schema is already
    supplied through the SDK config
  - do not enable Gemini automatic function calling or external tools for this
    feature; repository retrieval tools remain deterministic Python calls
  - expose a minimal function like:

  ```python
  def complete_json(prompt: str, schema: type[BaseModel], model: str | None =
  None) -> BaseModel:
      ...
  ```

  Config env vars:

  ```text
  VN_GROUNDED_QA_LLM_PROVIDER=google
  VN_GROUNDED_QA_LLM_MODEL=gemini-2.5-flash
  VN_GROUNDED_QA_LLM_TIMEOUT_MS=30000
  VN_GROUNDED_QA_LLM_RETRY_ATTEMPTS=2
  GEMINI_API_KEY=...
  ```

  ### semantic_models.py

  Define Pydantic contracts for LLM output.

  At minimum:

  ```python
  class QueryPlan(BaseModel):
      rewritten_queries: list[str]
      intent: str
      entities: list[str]
      doc_type_filter: str | None
      needs_version_resolution: bool
      needs_cross_document_reasoning: bool
      reason: str

  class EvidenceJudgment(BaseModel):
      unit_id: str
      role: Literal["supports", "contradicts", "background", "irrelevant"]
      supported_claim: str
      reason: str
      confidence: Literal["high", "medium", "low"]

  class EvidenceDecision(BaseModel):
      answerability: Literal["answerable", "insufficient", "contradictory",
  "unclear_version"]
      judgments: list[EvidenceJudgment]
      required_unit_ids: list[str]
      reason: str

  class AnswerDraft(BaseModel):
      answer: str
      used_unit_ids: list[str]
      confidence_label: Literal["high", "medium", "low", "insufficient"]
  ```

  Contract details:

  - Use strict Pydantic model config where possible:
      - reject extra fields
      - keep enums narrow
      - cap list lengths for rewritten queries, entities, judgments, and used
        unit IDs
  - Prefer nullable fields only where the Google structured-output schema
    subset supports them cleanly.
  - If SDK-parsed output and explicit Pydantic validation disagree, explicit
    local validation wins.
  - Normalize and compare returned IDs as exact strings; never fuzzy-match an
    LLM-returned unit ID to a local unit.

  ### semantic.py

  Implement:

  ```python
  plan_query(question: str) -> QueryPlan
  judge_evidence(question: str, hits: list[dict]) -> EvidenceDecision
  compose_answer(question: str, units: list[dict], decision: EvidenceDecision)
  -> AnswerDraft
  ```

  Rules:

  - LLM can only reference unit IDs provided in the prompt.
  - LLM cannot create citation fields.
  - LLM cannot claim evidence exists outside supplied units.
  - If LLM returns unknown unit IDs, reject the output.
  - If LLM says insufficient, final answer must be insufficient.
  - If deterministic version checks fail, final answer must be insufficient or
    unclear version.
  - If the LLM decision is answerable but deterministic support checks fail,
    return insufficient evidence or fall back to deterministic mode.
  - If the LLM draft omits a required supporting unit, do not silently add a
    citation; reject the draft and use the fallback policy.

  ## Answer Flow

  Add a new function beside the current deterministic path:

  answer_question_llm_assisted(session: ToolSession, question: str, top_k: int
  = 5) -> GroundedAnswer

  Suggested flow:

  1. Call plan_query(question).
  2. Run resolve_terms.
  3. Search using original question plus rewritten queries.
  4. Deduplicate hits by unit_id.
  5. Call judge_evidence(question, hits).
  6. If decision is not answerable, return deterministic insufficient evidence
     answer.
  7. Read only required_unit_ids.
  8. Call compose_answer.
  9. Validate used_unit_ids against read units.
  10. Build citations deterministically with existing citation logic.
  11. Validate answer contract.
  12. Return GroundedAnswer.

  Add CLI support:

  vn-grounded-qa ask "..." --mode deterministic
  vn-grounded-qa ask "..." --mode llm-assisted

  Default should remain deterministic until eval proves the new path is better.

  ## Evaluation Requirements

  Extend eval so both modes can be compared.

  Add support for:

  vn-grounded-qa eval eval/synthetic_mvp_seed.jsonl --mode deterministic
  vn-grounded-qa eval eval/synthetic_mvp_seed.jsonl --mode llm-assisted

  Track:

  - recall@k
  - answer correctness
  - citation exactness
  - hallucinated citation count
  - no-answer precision
  - no-answer recall
  - p50/p95 latency
  - estimated LLM calls
  - estimated cost
  - schema validation failures
  - invalid unit ID references from LLM
  - LLM fallback count
  - LLM timeout count
  - LLM retry-exhausted count
  - LLM schema-parse failure count
  - unsupported answer rejected by deterministic validator count

  Do not count an LLM answer as successful if it passes text correctness but
  fails citation exactness.

  Promotion gate:

  - deterministic mode remains the release gate owner until LLM-assisted mode
    is at least as good on citation exactness, hallucinated citation count,
    no-answer precision, and answer contract validity
  - LLM-assisted mode may improve answer readability or semantic selection, but
    it must not regress strict release checks
  - if live Gemini verification is unavailable, report LLM-assisted mode as
    stub-verified only and keep it experimental

  ## Testing Requirements

  Add focused tests for:

  1. Query planning schema validation.
  2. Evidence judge rejects unknown unit_id.
  3. LLM-assisted answer cannot cite units not retrieved/read.
  4. LLM-assisted no-answer path returns empty citations.
  5. Contradictory evidence becomes insufficient/contradictory.
  6. Current deterministic mode still works.
  7. CLI mode switch works.
  8. Eval can compare deterministic vs LLM-assisted mode.

  Use fake/stub LLM responses in unit tests. Do not require a real Gemini API
  key for normal test runs.

  ## Dependency Changes

  Update pyproject.toml with optional dependencies:

  [project.optional-dependencies]
  llm = [
    "google-genai>=1.74.0",
    "pydantic>=2.7"
  ]

  Do not make LLM dependencies required for the base package.

  If the optional dependency is missing and user requests --mode llm-assisted,
  return a clear error explaining how to install:

  pip install -e '.[llm]'

  ## Safety And Fallback Behavior

  If Gemini call fails, times out, returns invalid JSON, or returns invalid
  unit IDs:

  - record the failure in trace/tool metadata where appropriate
  - fall back to deterministic answer mode, or return insufficient evidence if
    fallback would be misleading
  - never silently produce an unsupported answer

  Add clear failure types to eval/reporting.

  Suggested failure types:

  - `llm_dependency_missing`
  - `llm_auth_missing`
  - `llm_timeout`
  - `llm_retry_exhausted`
  - `llm_invalid_json`
  - `llm_schema_validation_failed`
  - `llm_unknown_unit_id`
  - `llm_answer_contract_violation`
  - `llm_deterministic_validator_rejected`

  Trace metadata should include provider, model, timeout, retry attempts,
  schema name, elapsed time, fallback path, and failure type. Do not persist API
  keys or full prompts containing sensitive corpus text unless an explicit debug
  flag is added later.

  ## Documentation Updates

  Update docs only after implementation is working.

  Likely docs:

  - README.md
  - docs/IMPLEMENTATION.md
  - docs/TOOL_CONTRACTS.md
  - maybe a new docs/LLM_ASSISTED_MODE.md

  Document:

  - how to enable Google Gemini
  - env vars
  - deterministic vs LLM-assisted mode
  - citation safety model
  - why LLM is bounded and not an open-ended agent
  - how to run eval comparison

  ## Verification

  Run:

  python3 -m pytest -q

  Then run a small deterministic and LLM-assisted eval comparison. If no Gemini
  key is available, run stubbed tests and clearly report that live provider
  verification was skipped.

  Before finishing, inspect whether any existing release gate assumptions need
  updating. Do not weaken existing gates just to make LLM mode pass.

  Provider verification matrix:

  - Unit tests: fake provider, no network, no API key required.
  - Integration smoke: fake provider through CLI `--mode llm-assisted`.
  - Live smoke: Gemini Developer API with `GEMINI_API_KEY`, one answerable
    question and one no-answer question.
  - Optional Vertex smoke: `GOOGLE_GENAI_USE_VERTEXAI`,
    `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_LOCATION` configured.
  - Eval comparison: deterministic vs LLM-assisted over the same indexed DB and
    eval file, with latency/cost/fallback metrics reported separately.

  ## Output Contract

  Return:

  1. Summary of implemented architecture.
  2. Files changed.
  3. New CLI/API behavior.
  4. Test results.
  5. Eval comparison results if available.
  6. Known limitations.
  7. Recommendation: keep experimental, make default later, or reject until
     further work.

  ## Done Criteria

  The task is done only when:

  - LLM-assisted mode exists as a separate path.
  - Google provider integration is optional and configured by env vars.
  - Structured outputs are validated with Pydantic.
  - LLM cannot fabricate citations or unit IDs.
  - Existing deterministic mode still passes tests.
  - New tests cover core safety boundaries.
  - The answer contract remains authoritative.

  ## Research Notes To Preserve

  - Local repo evidence shows the current deterministic path already enforces
    citations from read units, empty citations for insufficient evidence, tool
    call ceilings, version ambiguity checks, and answer-contract validation.
    The LLM layer should wrap these constraints, not duplicate or bypass them.
  - Google GenAI structured output supports Pydantic models and JSON Schema,
    but the implementation should still run local Pydantic validation because
    this repository's citation and unit-ID rules are stricter than generic JSON
    shape validity.
  - The Google GenAI SDK supports both Gemini Developer API and Vertex AI
    configuration through the same client surface, so the provider adapter can
    stay small if environment detection is kept explicit.
  - The SDK and official docs expose HTTP timeout and retry configuration.
    These should be first-class config values because this project has bounded
    tool-call and deterministic fallback requirements.
  - Upstream SDK docs mention automatic function calling, but this feature
    should avoid it. Letting Gemini call tools would reintroduce the open-ended
    agent loop the project explicitly avoids.

  Useful references checked:

  - https://ai.google.dev/gemini-api/docs/structured-output
  - https://googleapis.github.io/python-genai/
  - https://github.com/googleapis/python-genai
  - https://docs.cloud.google.com/vertex-ai/generative-ai/docs/retry-strategy
