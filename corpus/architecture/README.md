# Architecture Corpus

This folder contains the M0 architecture corpus manifest and source fixtures.
The governed architecture corpus registers 29 documents across all five
required archetypes:

- `legal`
- `policy_sop`
- `technical_markdown`
- `table_pdf`
- `faq`

Use the validator before running M0 or the aggregate release gate:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus validate corpus/architecture/manifest.json
```

During development, `--relaxed` checks only manifest shape:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus validate corpus/architecture/manifest.json --relaxed
```
