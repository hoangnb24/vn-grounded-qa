# Production Shadow Pack

The production shadow pack contains governed representative deployment
documents that help prevent overfitting to public benchmark style. The
checked-in pack registers 6 documents.

Create a template for a replacement or experimental pack:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-template corpus/production-shadow/manifest.json --type production_shadow
```

Validate:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-validate corpus/production-shadow/manifest.json --type production_shadow
```
