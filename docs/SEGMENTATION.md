# Vietnamese Segmentation

The search schema has a first-class `vi_segmented_text` field. The default
runtime uses a conservative dependency-free tokenizer that preserves acronyms,
identifiers, product codes, and paths.

For production-quality Vietnamese segmentation, configure an external command
adapter:

```bash
export VN_GROUNDED_QA_SEGMENTER="/path/to/vncorenlp-wrapper"
```

The command must:

1. Read UTF-8 text from stdin.
2. Write segmented text to stdout.
3. Exit with status 0.

This shape works for a VnCoreNLP wrapper without forcing Java/runtime
dependencies into local development or CI. If the command is missing, exits
non-zero, times out, or returns empty output, ingestion falls back to the local
tokenizer.

The fallback is intentionally not treated as equivalent to VnCoreNLP. Release
gates for governed corpora should record which segmenter was used in the parser
and ingestion reports.
