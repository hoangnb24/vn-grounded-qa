# Legal Regression Pack

The implementation plan requires 12-20 legal documents to stress citation,
cross-reference, and version reasoning.

Create a template:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-template corpus/legal-regression/manifest.json --type legal_regression
```

Validate:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-validate corpus/legal-regression/manifest.json --type legal_regression
```
