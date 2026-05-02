# Production Shadow Pack

The implementation plan requires a small governed production shadow corpus to
prevent overfitting to public benchmark style.

Create a template:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-template corpus/production-shadow/manifest.json --type production_shadow
```

Validate:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-validate corpus/production-shadow/manifest.json --type production_shadow
```
