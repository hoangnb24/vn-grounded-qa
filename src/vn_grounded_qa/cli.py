"""Command line interface for the grounded QA MVP."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .answer import answer_question, answer_question_llm_assisted
from .baselines import compare_sparse_to_baseline, run_thin_rag_baseline, write_baseline_comparison_report
from .bakeoff import run_parser_bakeoff, write_report
from .corpus import validate_architecture_manifest, validate_pack_manifest, write_manifest_template, write_pack_template, write_synthetic_architecture_corpus, write_synthetic_pack
from .decisions import write_decision_report
from .eval import load_jsonl, run_eval, validate_eval_set, write_synthetic_mvp_eval
from .gates import run_m0_gate, run_m1_gate, run_m2_gate, run_m3_gate, run_m4_gate, run_m5_gate, run_m6_gate, run_release_gate, write_gate_report
from .readiness import run_governed_readiness
from .risks import validate_risk_register
from .store import GroundedStore
from .tools import ToolSession

PARSER_CHOICES = ["auto", "fallback", "docling", "marker"]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="vn-grounded-qa")
    parser.add_argument("--db", default="grounded.db", help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create or migrate the SQLite schema")

    sub.add_parser("schema", help="Print canonical store schema metadata")

    ingest = sub.add_parser("ingest", help="Ingest Markdown, text, or optional PDF sources")
    ingest.add_argument("paths", nargs="+", help="Files or directories to ingest")
    ingest.add_argument("--parser", choices=PARSER_CHOICES, default="auto")

    ingest_manifest = sub.add_parser("ingest-manifest", help="Ingest all source files registered in a corpus manifest")
    ingest_manifest.add_argument("manifest")
    ingest_manifest.add_argument("--parser", choices=PARSER_CHOICES, default="auto")

    alias = sub.add_parser("alias", help="Add a term alias")
    alias.add_argument("surface_form")
    alias.add_argument("canonical_form")
    alias.add_argument("--domain", default="")
    alias.add_argument("--type", default="")
    alias_import = sub.add_parser("alias-import", help="Import aliases from CSV")
    alias_import.add_argument("csv_path")

    search = sub.add_parser("search", help="Search evidence units")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=10)
    search.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE", help="Filter by doc_id, doc_family_id, doc_type, status, or version_label")

    ask = sub.add_parser("ask", help="Answer with citations from the corpus")
    ask.add_argument("question")
    ask.add_argument("--top-k", type=int, default=5)
    ask.add_argument("--mode", choices=["deterministic", "llm-assisted"], default="deterministic")
    ask.add_argument("--trace-id", default="", help="Persist tool calls under this trace id")

    eval_cmd = sub.add_parser("eval", help="Run a JSONL retrieval/no-answer eval")
    eval_cmd.add_argument("examples")
    eval_cmd.add_argument("--k", type=int, default=10)
    eval_cmd.add_argument("--mode", choices=["deterministic", "llm-assisted"], default="deterministic")

    evalset = sub.add_parser("evalset", help="Manage authored evaluation sets")
    evalset_sub = evalset.add_subparsers(dest="evalset_command", required=True)
    evalset_validate = evalset_sub.add_parser("validate", help="Validate MVP eval-set shape and category counts")
    evalset_validate.add_argument("examples")
    evalset_validate.add_argument("--taxonomy", default="eval/taxonomy.yaml")
    evalset_validate.add_argument("--relaxed", action="store_true")
    evalset_seed = evalset_sub.add_parser("seed-synthetic", help="Create a synthetic 80-question MVP eval set")
    evalset_seed.add_argument("examples")

    risks = sub.add_parser("risks", help="Validate risk register")
    risks_sub = risks.add_subparsers(dest="risks_command", required=True)
    risks_validate = risks_sub.add_parser("validate", help="Validate risk owners, mitigations, and statuses")
    risks_validate.add_argument("--path", default="docs/RISK_REGISTER.md")
    risks_validate.add_argument("--strict-owners", action="store_true", help="Reject placeholder role owners for release readiness")

    readiness = sub.add_parser("readiness", help="Check governed inputs needed before release gates")
    readiness_sub = readiness.add_subparsers(dest="readiness_command", required=True)
    readiness_governed = readiness_sub.add_parser("governed", help="Report release-blocking governed input gaps")
    readiness_governed.add_argument("--manifest", default="corpus/architecture/manifest.json")
    readiness_governed.add_argument("--eval", default="eval/mvp80_governed.jsonl")
    readiness_governed.add_argument("--taxonomy", default="eval/taxonomy.yaml")
    readiness_governed.add_argument("--legal-pack", default="corpus/legal-regression/manifest.json")
    readiness_governed.add_argument("--shadow-pack", default="corpus/production-shadow/manifest.json")
    readiness_governed.add_argument("--risk-register", default="docs/RISK_REGISTER.md")
    readiness_governed.add_argument("--pyproject", default="pyproject.toml")
    readiness_governed.add_argument("--readme", default="README.md")
    readiness_governed.add_argument("--strict-risk-owners", action="store_true", help="Reject placeholder role owners")
    readiness_governed.add_argument("--out", help="Optional JSON report path")

    corpus = sub.add_parser("corpus", help="Manage corpus manifests")
    corpus_sub = corpus.add_subparsers(dest="corpus_command", required=True)
    corpus_validate = corpus_sub.add_parser("validate", help="Validate an architecture corpus manifest")
    corpus_validate.add_argument("manifest")
    corpus_validate.add_argument("--relaxed", action="store_true", help="Validate schema without enforcing M0 size/archetype gates")
    corpus_template = corpus_sub.add_parser("template", help="Create an empty architecture corpus manifest")
    corpus_template.add_argument("manifest")
    corpus_seed = corpus_sub.add_parser("seed-synthetic", help="Create a 25-document synthetic architecture corpus fixture")
    corpus_seed.add_argument("manifest")
    corpus_seed.add_argument("--docs-per-archetype", type=int, default=5)
    corpus_pack_template = corpus_sub.add_parser("pack-template", help="Create an empty legal_regression or production_shadow manifest")
    corpus_pack_template.add_argument("manifest")
    corpus_pack_template.add_argument("--type", choices=["legal_regression", "production_shadow"], required=True)
    corpus_pack_validate = corpus_sub.add_parser("pack-validate", help="Validate a legal_regression or production_shadow manifest")
    corpus_pack_validate.add_argument("manifest")
    corpus_pack_validate.add_argument("--type", choices=["legal_regression", "production_shadow"], required=True)
    corpus_pack_seed = corpus_sub.add_parser("pack-seed-synthetic", help="Create a synthetic legal_regression or production_shadow manifest")
    corpus_pack_seed.add_argument("manifest")
    corpus_pack_seed.add_argument("--type", choices=["legal_regression", "production_shadow"], required=True)

    bakeoff = sub.add_parser("bakeoff", help="Run ingestion/parser quality reports")
    bakeoff_sub = bakeoff.add_subparsers(dest="bakeoff_command", required=True)
    parser_bakeoff = bakeoff_sub.add_parser("parser", help="Run a parser scorecard")
    parser_bakeoff.add_argument("manifest")
    parser_bakeoff.add_argument("--parser", choices=PARSER_CHOICES, default="auto")
    parser_bakeoff.add_argument("--out", help="Optional JSON report path")
    fallback_bakeoff = bakeoff_sub.add_parser("fallback", help="Run the local fallback parser scorecard")
    fallback_bakeoff.add_argument("manifest")
    fallback_bakeoff.add_argument("--out", help="Optional JSON report path")

    gates = sub.add_parser("gates", help="Run milestone gate reports")
    gates_sub = gates.add_subparsers(dest="gate_command", required=True)
    m0_gate = gates_sub.add_parser("m0", help="Run the M0 scope/corpus gate")
    m0_gate.add_argument("--manifest", default="corpus/architecture/manifest.json")
    m0_gate.add_argument("--taxonomy", default="eval/taxonomy.yaml")
    m0_gate.add_argument("--out", default="reports/m0_gate.json")
    m1_gate = gates_sub.add_parser("m1", help="Run the M1 parser bakeoff gate")
    m1_gate.add_argument("--manifest", default="corpus/architecture/manifest.json")
    m1_gate.add_argument("--parser", choices=PARSER_CHOICES, default="auto")
    m1_gate.add_argument("--out", default="reports/m1_gate.json")
    m2_gate = gates_sub.add_parser("m2", help="Run the M2 sparse retrieval gate against an indexed DB")
    m2_gate.add_argument("--db", default="grounded.db")
    m2_gate.add_argument("--eval", default="eval/synthetic_mvp_seed.jsonl")
    m2_gate.add_argument("--out", default="reports/m2_gate.json")
    m3_gate = gates_sub.add_parser("m3", help="Run the M3 bounded tool orchestration gate")
    m3_gate.add_argument("--db", default="grounded.db")
    m3_gate.add_argument("--eval", default="eval/synthetic_mvp_seed.jsonl")
    m3_gate.add_argument("--out", default="reports/m3_gate.json")
    m4_gate = gates_sub.add_parser("m4", help="Run the M4 end-to-end answer gate")
    m4_gate.add_argument("--db", default="grounded.db")
    m4_gate.add_argument("--eval", default="eval/synthetic_mvp_seed.jsonl")
    m4_gate.add_argument("--out", default="reports/m4_gate.json")
    m5_gate = gates_sub.add_parser("m5", help="Run the M5 thin RAG baseline comparison gate")
    m5_gate.add_argument("--db", default="grounded.db")
    m5_gate.add_argument("--eval", default="eval/synthetic_mvp_seed.jsonl")
    m5_gate.add_argument("--out", default="reports/m5_gate.json")
    m6_gate = gates_sub.add_parser("m6", help="Run the M6 scale and upgrade-decision gate")
    m6_gate.add_argument("--db", default="grounded.db")
    m6_gate.add_argument("--base-eval", default="eval/synthetic_mvp_seed.jsonl")
    m6_gate.add_argument("--scale-eval", default="eval/synthetic_mvp_seed.jsonl")
    m6_gate.add_argument("--out", default="reports/m6_gate.json")
    release_gate = gates_sub.add_parser("release", help="Run the final release gate aggregate")
    release_gate.add_argument("--manifest", default="corpus/architecture/manifest.json")
    release_gate.add_argument("--db", default="grounded.db")
    release_gate.add_argument("--eval", default="eval/synthetic_mvp_seed.jsonl")
    release_gate.add_argument("--scale-eval", default="eval/synthetic_mvp_seed.jsonl")
    release_gate.add_argument("--parser", choices=PARSER_CHOICES, default="auto")
    release_gate.add_argument("--legal-pack", default="corpus/legal-regression/manifest.json")
    release_gate.add_argument("--shadow-pack", default="corpus/production-shadow/manifest.json")
    release_gate.add_argument("--pyproject", default="pyproject.toml")
    release_gate.add_argument("--readme", default="README.md")
    release_gate.add_argument("--strict-risk-owners", action="store_true", help="Reject placeholder role owners in the aggregate release gate")
    release_gate.add_argument("--out", default="reports/release_gate.json")

    decisions = sub.add_parser("decisions", help="Create go/revise/stop decision reports from gate JSON")
    decisions_sub = decisions.add_subparsers(dest="decisions_command", required=True)
    decisions_report = decisions_sub.add_parser("report", help="Write a Markdown decision report from a gate JSON report")
    decisions_report.add_argument("gate_report")
    decisions_report.add_argument("--out", required=True)
    decisions_report.add_argument("--stop-reason", default="")

    traces = sub.add_parser("traces", help="Inspect persisted tool traces")
    traces_sub = traces.add_subparsers(dest="traces_command", required=True)
    traces_sub.add_parser("list", help="List trace ids with call counts")
    traces_show = traces_sub.add_parser("show", help="Show one persisted trace")
    traces_show.add_argument("trace_id")

    baselines = sub.add_parser("baselines", help="Run and explain baseline comparisons")
    baselines_sub = baselines.add_subparsers(dest="baselines_command", required=True)
    baselines_report = baselines_sub.add_parser("report", help="Write an M5 sparse-vs-thin-RAG comparison report")
    baselines_report.add_argument("--eval", default="eval/synthetic_mvp_seed.jsonl")
    baselines_report.add_argument("--out", default="reports/m5_baseline_comparison.md")

    args = parser.parse_args(argv)
    if args.command == "corpus":
        if args.corpus_command == "validate":
            result = validate_architecture_manifest(Path(args.manifest), strict_m0=not args.relaxed)
            print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
            return 0 if result.ok else 2
        if args.corpus_command == "template":
            write_manifest_template(Path(args.manifest))
            print(json.dumps({"ok": True, "manifest": args.manifest}, ensure_ascii=False))
            return 0
        if args.corpus_command == "seed-synthetic":
            write_synthetic_architecture_corpus(Path(args.manifest), docs_per_archetype=args.docs_per_archetype)
            result = validate_architecture_manifest(Path(args.manifest), strict_m0=True)
            print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
            return 0 if result.ok else 2
        if args.corpus_command == "pack-template":
            write_pack_template(Path(args.manifest), args.type)
            print(json.dumps({"ok": True, "manifest": args.manifest, "type": args.type}, ensure_ascii=False))
            return 0
        if args.corpus_command == "pack-validate":
            result = validate_pack_manifest(Path(args.manifest), args.type)
            print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
            return 0 if result.ok else 2
        if args.corpus_command == "pack-seed-synthetic":
            write_synthetic_pack(Path(args.manifest), args.type)
            result = validate_pack_manifest(Path(args.manifest), args.type)
            print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
            return 0 if result.ok else 2
    if args.command == "bakeoff":
        if args.bakeoff_command in {"fallback", "parser"}:
            parser_name = "fallback" if args.bakeoff_command == "fallback" else args.parser
            report = run_parser_bakeoff(Path(args.manifest), parser_name)
            write_report(report, Path(args.out) if args.out else None)
            print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
            return 0 if report.ok else 2
    if args.command == "evalset":
        if args.evalset_command == "validate":
            result = validate_eval_set(Path(args.examples), strict=not args.relaxed, taxonomy_path=Path(args.taxonomy))
            print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
            return 0 if result.ok else 2
        if args.evalset_command == "seed-synthetic":
            write_synthetic_mvp_eval(Path(args.examples))
            result = validate_eval_set(Path(args.examples), strict=True)
            print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
            return 0 if result.ok else 2
    if args.command == "risks":
        if args.risks_command == "validate":
            result = validate_risk_register(Path(args.path), strict_owners=args.strict_owners)
            print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
            return 0 if result.ok else 2
    if args.command == "readiness":
        if args.readiness_command == "governed":
            report = run_governed_readiness(
                Path(args.manifest),
                Path(args.eval),
                taxonomy_path=Path(args.taxonomy),
                legal_pack_path=Path(args.legal_pack),
                shadow_pack_path=Path(args.shadow_pack),
                risk_register_path=Path(args.risk_register),
                pyproject_path=Path(args.pyproject),
                readme_path=Path(args.readme),
                strict_risk_owners=args.strict_risk_owners,
            )
            payload = json.dumps(asdict(report), ensure_ascii=False, indent=2)
            if args.out:
                Path(args.out).parent.mkdir(parents=True, exist_ok=True)
                Path(args.out).write_text(payload + "\n", encoding="utf-8")
            print(payload)
            return 0 if report.ok else 2
    if args.command == "decisions":
        if args.decisions_command == "report":
            report = write_decision_report(Path(args.gate_report), Path(args.out), stop_reason=args.stop_reason)
            print(json.dumps({"ok": True, "decision": report.decision, "out": args.out}, ensure_ascii=False))
            return 0 if report.decision == "go" else 2
    if args.command == "gates":
        if args.gate_command == "m0":
            report = run_m0_gate(Path(args.manifest), Path(args.taxonomy))
            write_gate_report(report, Path(args.out))
            print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
            return 0 if report.decision == "go" else 2
        if args.gate_command == "m1":
            report = run_m1_gate(Path(args.manifest), args.parser)
            write_gate_report(report, Path(args.out))
            print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
            return 0 if report.decision == "go" else 2
        if args.gate_command == "m2":
            report = run_m2_gate(Path(args.db), Path(args.eval))
            write_gate_report(report, Path(args.out))
            print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
            return 0 if report.decision == "go" else 2
        if args.gate_command == "m3":
            report = run_m3_gate(Path(args.db), Path(args.eval))
            write_gate_report(report, Path(args.out))
            print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
            return 0 if report.decision == "go" else 2
        if args.gate_command == "m4":
            report = run_m4_gate(Path(args.db), Path(args.eval))
            write_gate_report(report, Path(args.out))
            print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
            return 0 if report.decision == "go" else 2
        if args.gate_command == "m5":
            report = run_m5_gate(Path(args.db), Path(args.eval))
            write_gate_report(report, Path(args.out))
            print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
            return 0 if report.decision == "go" else 2
        if args.gate_command == "m6":
            report = run_m6_gate(Path(args.db), Path(args.base_eval), Path(args.scale_eval))
            write_gate_report(report, Path(args.out))
            print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
            return 0 if report.decision == "go" else 2
        if args.gate_command == "release":
            report = run_release_gate(
                Path(args.manifest),
                Path(args.db),
                Path(args.eval),
                Path(args.scale_eval),
                parser=args.parser,
                legal_pack_path=Path(args.legal_pack),
                shadow_pack_path=Path(args.shadow_pack),
                pyproject_path=Path(args.pyproject),
                readme_path=Path(args.readme),
                strict_risk_owners=args.strict_risk_owners,
            )
            write_gate_report(report, Path(args.out))
            print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
            return 0 if report.decision == "go" else 2

    store = GroundedStore(Path(args.db))
    try:
        if args.command == "init":
            store.init_schema()
            print(json.dumps({"ok": True, "db": str(store.db_path)}, ensure_ascii=False))
            return 0
        store.init_schema()
        if args.command == "schema":
            print(json.dumps({"schema_version": store.schema_version(), "db": str(store.db_path)}, ensure_ascii=False))
            return 0
        if args.command == "ingest":
            files = list(iter_source_files([Path(p) for p in args.paths]))
            units = 0
            for file in files:
                _, ingested = store.ingest_path(file, parser=args.parser)
                units += len(ingested)
            print(json.dumps({"ok": True, "files": len(files), "units": units}, ensure_ascii=False))
            return 0
        if args.command == "ingest-manifest":
            units = store.ingest_manifest(Path(args.manifest), parser=args.parser)
            print(json.dumps({"ok": True, "manifest": args.manifest, "units": units}, ensure_ascii=False))
            return 0
        if args.command == "alias":
            store.add_alias(args.surface_form, args.canonical_form, domain=args.domain, alias_type=args.type)
            print(json.dumps({"ok": True}, ensure_ascii=False))
            return 0
        if args.command == "alias-import":
            count = store.import_alias_csv(Path(args.csv_path))
            print(json.dumps({"ok": True, "imported": count}, ensure_ascii=False))
            return 0
        if args.command == "search":
            hits = store.search_units(args.query, top_k=args.top_k, filters=parse_filters(args.filter))
            print(json.dumps([asdict(hit) for hit in hits], ensure_ascii=False, indent=2))
            return 0
        if args.command == "ask":
            answerer = answer_question if args.mode == "deterministic" else answer_question_llm_assisted
            answer = answerer(ToolSession(store, trace_id=args.trace_id or None), args.question, top_k=args.top_k)
            print(json.dumps(asdict(answer), ensure_ascii=False, indent=2))
            return 0
        if args.command == "eval":
            result = run_eval(store, load_jsonl(Path(args.examples)), k=args.k, mode=args.mode)
            print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
            return 0
        if args.command == "baselines":
            if args.baselines_command == "report":
                examples = load_jsonl(Path(args.eval))
                sparse = run_eval(store, examples, k=10)
                baseline = run_thin_rag_baseline(store, examples, top_k=10)
                comparison = compare_sparse_to_baseline(sparse, baseline)
                write_baseline_comparison_report(comparison, Path(args.out))
                print(json.dumps({"ok": True, "decision": comparison.decision, "out": args.out}, ensure_ascii=False))
                return 0 if comparison.decision == "go" else 2
        if args.command == "traces":
            if args.traces_command == "list":
                rows = store.list_tool_traces()
                print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))
                return 0
            if args.traces_command == "show":
                rows = store.get_tool_trace(args.trace_id)
                print(json.dumps([trace_row_dict(row) for row in rows], ensure_ascii=False, indent=2))
                return 0 if rows else 2
    finally:
        store.close()
    return 1


def iter_source_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.suffix.lower() in {".md", ".markdown", ".txt", ".text", ".pdf"}:
                    yield child
        else:
            yield path


def parse_filters(items: Iterable[str]) -> Dict[str, str]:
    filters: Dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid filter {item!r}; expected KEY=VALUE")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise ValueError(f"Invalid filter {item!r}; expected KEY=VALUE")
        filters[key] = value
    return filters


def trace_row_dict(row) -> dict:
    payload = dict(row)
    try:
        payload["args"] = json.loads(payload.pop("args_json"))
    except (KeyError, json.JSONDecodeError):
        pass
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
