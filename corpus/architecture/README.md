# Architecture Corpus

This folder is reserved for the M0 architecture corpus manifest and source
fixtures. The production M0 gate requires 24-36 registered documents across all
five archetypes:

- `legal`
- `policy_sop`
- `technical_markdown`
- `table_pdf`
- `faq`

Use the validator before closing M0:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus validate corpus/architecture/manifest.json
```

During development, `--relaxed` checks only manifest shape:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus validate corpus/architecture/manifest.json --relaxed
```
