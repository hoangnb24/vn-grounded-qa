# Parser Adapters

The ingestion layer supports four parser routes:

| Parser | Role | Dependency | Notes |
|---|---|---|---|
| `auto` | Default ingestion route | optional Docling/Marker | Tries Docling, then Marker, then local fallback; records a parser warning when it degrades |
| `fallback` | Local development and CI parser | none, plus optional `pypdf` for PDFs | Handles Markdown, text, and optional simple PDF extraction |
| `docling` | M1 default parser candidate | `pip install 'vn-grounded-qa[docling]'` | Uses `docling.document_converter.DocumentConverter` and exports Markdown |
| `marker` | M1 fallback parser candidate | `pip install 'vn-grounded-qa[marker]'` | Uses the Marker CLI and imports generated Markdown |

Run a parser scorecard:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff parser corpus/architecture/manifest.json --parser auto
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff parser corpus/architecture/manifest.json --parser fallback
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff parser corpus/architecture/manifest.json --parser docling
PYTHONPATH=src python3 -m vn_grounded_qa.cli bakeoff parser corpus/architecture/manifest.json --parser marker
```

Unavailable optional parsers are reported as per-document parse failures. This
keeps bakeoff runs auditable: a missing dependency is a failed candidate, not a
silent fallback.

For `auto`, optional-parser degradation is reported in each document's
`parser_warnings` list. A successful `auto` bakeoff can show that Docling or
Marker were unavailable and the local parser was used.

Use parser selection during ingestion:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli --db grounded.db ingest-manifest corpus/architecture/manifest.json --parser auto
```

The M1 gate is evaluated through `gates m1`, which runs a parser bakeoff on the
governed architecture corpus and applies the parse-success, heading-recovery,
and provenance-completeness thresholds. Optional Docling and Marker scorecards
can be generated independently when those dependencies are installed in the
target runtime.

## Heading Gold

Governed corpus manifests may include `expected_heading_paths` per document.
When present, M1 bakeoff treats heading recovery as successful only if all
listed paths appear in canonical units.

Example:

```json
{
  "doc_id": "policy_001",
  "expected_heading_paths": [
    "Chính sách nhân sự > Phê duyệt",
    "Chính sách nhân sự > Ngoại lệ"
  ]
}
```
