# Legal Regression Pack

The legal regression pack contains governed legal documents that stress
citation, cross-reference, and version/status reasoning. The checked-in pack
registers 12 documents.

Create a template for a replacement or experimental pack:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-template corpus/legal-regression/manifest.json --type legal_regression
```

Validate:

```bash
PYTHONPATH=src python3 -m vn_grounded_qa.cli corpus pack-validate corpus/legal-regression/manifest.json --type legal_regression
```
