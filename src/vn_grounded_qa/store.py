"""SQLite canonical store and sparse FTS retrieval."""

from __future__ import annotations

import sqlite3
import json
import re
import csv
from dataclasses import replace
from pathlib import Path
from typing import Iterable, List, Mapping, Optional

from .corpus import load_manifest
from .models import ContentUnit, DocumentMeta, SearchHit
from .normalize import ascii_fold, make_fts_query, normalize_text
from .parsers import parse_file, stable_id, units_from_ir

SCHEMA_VERSION = 1


class GroundedStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                doc_family_id TEXT,
                title TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                format TEXT NOT NULL,
                language TEXT NOT NULL,
                source_uri TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                version_label TEXT,
                effective_from TEXT,
                effective_to TEXT,
                status TEXT NOT NULL,
                parser_name TEXT NOT NULL,
                parser_version TEXT NOT NULL,
                ingest_time TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS content_units (
                unit_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                parent_unit_id TEXT,
                unit_type TEXT NOT NULL,
                heading_path TEXT,
                ordinal_path TEXT,
                sequence_no INTEGER NOT NULL,
                page_start INTEGER NOT NULL,
                page_end INTEGER NOT NULL,
                raw_text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                vi_segmented_text TEXT NOT NULL,
                ascii_folded_text TEXT NOT NULL,
                glossary_terms TEXT,
                table_text TEXT,
                unit_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS relations (
                relation_id TEXT PRIMARY KEY,
                from_unit_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                to_unit_id TEXT NOT NULL,
                confidence REAL NOT NULL,
                source TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS aliases (
                alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
                surface_form TEXT NOT NULL,
                canonical_form TEXT NOT NULL,
                lang TEXT NOT NULL DEFAULT 'vi',
                domain TEXT,
                alias_type TEXT,
                source TEXT
            );

            CREATE UNIQUE INDEX IF NOT EXISTS aliases_unique_term
            ON aliases(surface_form, canonical_form, ifnull(domain, ''));

            CREATE TABLE IF NOT EXISTS tool_traces (
                trace_id TEXT NOT NULL,
                call_index INTEGER NOT NULL,
                tool TEXT NOT NULL,
                args_json TEXT NOT NULL,
                result_count INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(trace_id, call_index)
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS content_units_fts USING fts5(
                title,
                heading_path,
                normalized_text,
                vi_segmented_text,
                glossary_terms,
                table_text,
                ascii_folded_text,
                content='',
                tokenize='unicode61 remove_diacritics 2'
            );
            """
        )
        self.set_schema_version(SCHEMA_VERSION)
        self.seed_aliases()
        self.conn.commit()

    def set_schema_version(self, version: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', ?)",
            (str(version),),
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, description) VALUES (?, ?)",
            (version, "canonical schema v1"),
        )

    def schema_version(self) -> int:
        row = self.conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
        return int(row["value"]) if row else 0

    def seed_aliases(self) -> None:
        builtins = [
            ("truy xuất", "retrieval", "vi", "core", "translation", "builtin"),
            ("tìm kiếm", "search", "vi", "core", "translation", "builtin"),
            ("bằng chứng", "evidence", "vi", "core", "translation", "builtin"),
            ("trích dẫn", "citation", "vi", "core", "translation", "builtin"),
            ("công cụ", "tool", "vi", "core", "translation", "builtin"),
            ("tác tử", "agent", "vi", "core", "translation", "builtin"),
        ]
        self.conn.executemany(
            """
            INSERT OR IGNORE INTO aliases(surface_form, canonical_form, lang, domain, alias_type, source)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            builtins,
        )

    def ingest_path(self, path: Path, parser: str = "auto") -> tuple[DocumentMeta, List[ContentUnit]]:
        ir = parse_file(path, parser=parser)
        units = units_from_ir(ir)
        self.upsert_document(ir.document_meta)
        self.replace_units(ir.document_meta.doc_id, units)
        self.conn.commit()
        return ir.document_meta, units

    def ingest_manifest(self, manifest_path: Path, parser: str = "auto") -> int:
        manifest = load_manifest(manifest_path)
        docs = manifest.get("documents", [])
        if not isinstance(docs, list):
            raise ValueError("documents must be a list")
        total_units = 0
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            _, units = self.ingest_manifest_document(manifest_path.parent, doc, parser=parser)
            total_units += len(units)
        self.conn.commit()
        return total_units

    def ingest_manifest_document(self, manifest_dir: Path, doc: Mapping[str, object], parser: str = "auto") -> tuple[DocumentMeta, List[ContentUnit]]:
        source_uri = str(doc["source_uri"])
        path = Path(source_uri)
        if not path.is_absolute():
            path = manifest_dir / path
        ir = parse_file(path, parser=parser)
        meta = manifest_meta(ir.document_meta, doc, str(path))
        units = [replace(unit, doc_id=meta.doc_id, unit_id=stable_id(meta.doc_id, unit.sequence_no, unit.unit_hash, prefix="unit_")) for unit in units_from_ir(replace(ir, document_meta=meta))]
        self.upsert_document(meta)
        self.replace_units(meta.doc_id, units)
        return meta, units

    def ingest_many(self, paths: Iterable[Path]) -> int:
        total = 0
        for path in paths:
            _, units = self.ingest_path(path)
            total += len(units)
        return total

    def upsert_document(self, meta: DocumentMeta) -> None:
        self.conn.execute(
            """
            INSERT INTO documents (
                doc_id, doc_family_id, title, doc_type, format, language,
                source_uri, source_hash, version_label, effective_from,
                effective_to, status, parser_name, parser_version, ingest_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                title=excluded.title,
                doc_family_id=excluded.doc_family_id,
                doc_type=excluded.doc_type,
                format=excluded.format,
                language=excluded.language,
                version_label=excluded.version_label,
                effective_from=excluded.effective_from,
                effective_to=excluded.effective_to,
                status=excluded.status,
                source_hash=excluded.source_hash,
                parser_name=excluded.parser_name,
                parser_version=excluded.parser_version,
                ingest_time=excluded.ingest_time
            """,
            (
                meta.doc_id,
                meta.doc_family_id or meta.doc_id,
                meta.title,
                meta.doc_type,
                meta.format,
                meta.language,
                meta.source_uri,
                meta.source_hash,
                meta.version_label,
                meta.effective_from,
                meta.effective_to,
                meta.status,
                meta.parser_name,
                meta.parser_version,
                meta.ingest_time,
            ),
        )

    def replace_units(self, doc_id: str, units: List[ContentUnit]) -> None:
        old_fts_rows = self.conn.execute(
            """
            SELECT
                cu.rowid,
                d.title,
                cu.heading_path,
                cu.normalized_text,
                cu.vi_segmented_text,
                cu.glossary_terms,
                cu.table_text,
                cu.ascii_folded_text
            FROM content_units cu
            JOIN documents d ON d.doc_id = cu.doc_id
            WHERE cu.doc_id = ?
            """,
            (doc_id,),
        ).fetchall()
        for row in old_fts_rows:
            self.delete_fts_row(row)
        self.conn.execute("DELETE FROM relations WHERE from_unit_id IN (SELECT unit_id FROM content_units WHERE doc_id = ?)", (doc_id,))
        self.conn.execute("DELETE FROM relations WHERE to_unit_id IN (SELECT unit_id FROM content_units WHERE doc_id = ?)", (doc_id,))
        self.conn.execute("DELETE FROM content_units WHERE doc_id = ?", (doc_id,))
        for unit in units:
            self.insert_unit(unit)
        self.insert_structural_relations(units)

    def delete_fts_row(self, row: sqlite3.Row) -> None:
        try:
            self.conn.execute("DELETE FROM content_units_fts WHERE rowid = ?", (row["rowid"],))
        except sqlite3.OperationalError as exc:
            if "contentless fts5" not in str(exc).lower():
                raise
            self.conn.execute(
                """
                INSERT INTO content_units_fts (
                    content_units_fts, rowid, title, heading_path, normalized_text,
                    vi_segmented_text, glossary_terms, table_text, ascii_folded_text
                )
                VALUES ('delete', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["rowid"],
                    row["title"],
                    row["heading_path"],
                    row["normalized_text"],
                    row["vi_segmented_text"],
                    row["glossary_terms"],
                    row["table_text"],
                    row["ascii_folded_text"],
                ),
            )

    def insert_unit(self, unit: ContentUnit) -> None:
        cur = self.conn.execute(
            """
            INSERT INTO content_units (
                unit_id, doc_id, parent_unit_id, unit_type, heading_path,
                ordinal_path, sequence_no, page_start, page_end, raw_text,
                normalized_text, vi_segmented_text, ascii_folded_text,
                glossary_terms, table_text, unit_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unit.unit_id,
                unit.doc_id,
                unit.parent_unit_id,
                unit.unit_type,
                unit.heading_path,
                unit.ordinal_path,
                unit.sequence_no,
                unit.page_start,
                unit.page_end,
                unit.raw_text,
                unit.normalized_text,
                unit.vi_segmented_text,
                unit.ascii_folded_text,
                unit.glossary_terms,
                unit.table_text,
                unit.unit_hash,
            ),
        )
        title = self.conn.execute("SELECT title FROM documents WHERE doc_id = ?", (unit.doc_id,)).fetchone()["title"]
        self.conn.execute(
            """
            INSERT INTO content_units_fts (
                rowid, title, heading_path, normalized_text, vi_segmented_text,
                glossary_terms, table_text, ascii_folded_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cur.lastrowid,
                title,
                unit.heading_path,
                unit.normalized_text,
                unit.vi_segmented_text,
                unit.glossary_terms,
                unit.table_text,
                unit.ascii_folded_text,
            ),
        )

    def insert_structural_relations(self, units: List[ContentUnit]) -> None:
        ordered = sorted(units, key=lambda unit: unit.sequence_no)
        for previous, current in zip(ordered, ordered[1:]):
            self.insert_relation(previous.unit_id, "next", current.unit_id, 1.0, "sequence")
            self.insert_relation(current.unit_id, "previous", previous.unit_id, 1.0, "sequence")
        heading_index = {unit.heading_path: unit for unit in ordered if unit.heading_path}
        for unit in ordered:
            parent_path = parent_heading_path(unit.heading_path)
            parent = heading_index.get(parent_path)
            if parent and parent.unit_id != unit.unit_id:
                self.insert_relation(parent.unit_id, "child", unit.unit_id, 0.8, "heading_path")
                self.insert_relation(unit.unit_id, "parent", parent.unit_id, 0.8, "heading_path")
            for relation_type in heuristic_relation_types(unit.raw_text):
                target = previous_unit(ordered, unit.sequence_no)
                if target:
                    self.insert_relation(unit.unit_id, relation_type, target.unit_id, 0.5, "heuristic")
            for target in referenced_units(ordered, unit):
                self.insert_relation(unit.unit_id, "references", target.unit_id, 0.7, "heading_reference")
        for left_index, left in enumerate(ordered):
            left_topics = same_topic_keys(left)
            if not left_topics:
                continue
            for right in ordered[left_index + 1 :]:
                if left.doc_id != right.doc_id:
                    continue
                right_topics = same_topic_keys(right)
                if left_topics.intersection(right_topics):
                    self.insert_relation(left.unit_id, "same_topic", right.unit_id, 0.6, "topic_key")
                    self.insert_relation(right.unit_id, "same_topic", left.unit_id, 0.6, "topic_key")

    def insert_relation(self, from_unit_id: str, relation_type: str, to_unit_id: str, confidence: float, source: str) -> None:
        relation_id = stable_id(from_unit_id, relation_type, to_unit_id, prefix="rel_")
        self.conn.execute(
            """
            INSERT OR REPLACE INTO relations(relation_id, from_unit_id, relation_type, to_unit_id, confidence, source)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (relation_id, from_unit_id, relation_type, to_unit_id, confidence, source),
        )

    def add_alias(self, surface_form: str, canonical_form: str, lang: str = "vi", domain: str = "", alias_type: str = "", source: str = "manual") -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO aliases(surface_form, canonical_form, lang, domain, alias_type, source) VALUES (?, ?, ?, ?, ?, ?)",
            (surface_form, canonical_form, lang, domain, alias_type, source),
        )
        self.conn.commit()

    def import_alias_csv(self, path: Path) -> int:
        count = 0
        with Path(path).open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                surface = str(row.get("surface_form", "")).strip()
                canonical = str(row.get("canonical_form", "")).strip()
                if not surface or not canonical:
                    continue
                before = self.conn.total_changes
                self.conn.execute(
                    "INSERT OR IGNORE INTO aliases(surface_form, canonical_form, lang, domain, alias_type, source) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        surface,
                        canonical,
                        str(row.get("lang", "vi") or "vi"),
                        str(row.get("domain", "") or ""),
                        str(row.get("alias_type", "") or ""),
                        str(row.get("source", "csv") or "csv"),
                    ),
                )
                if self.conn.total_changes > before:
                    count += 1
        self.conn.commit()
        return count

    def resolve_terms(self, query: str) -> List[str]:
        normalized = normalize_text(query)
        folded = ascii_fold(query)
        rows = self.conn.execute("SELECT surface_form, canonical_form FROM aliases").fetchall()
        terms = []
        for row in rows:
            surface = normalize_text(row["surface_form"])
            canonical = normalize_text(row["canonical_form"])
            if surface in normalized or canonical in normalized or ascii_fold(surface) in folded or ascii_fold(canonical) in folded:
                terms.extend([row["surface_form"], row["canonical_form"]])
        return sorted(set(terms))

    def search_units(
        self,
        query: str,
        top_k: int = 10,
        doc_type: Optional[str] = None,
        status: str = "active",
        filters: Optional[Mapping[str, object]] = None,
    ) -> List[SearchHit]:
        extras = self.resolve_terms(query)
        fts_query = make_fts_query(query, extras)
        active_filters = dict(filters or {})
        if doc_type and "doc_type" not in active_filters:
            active_filters["doc_type"] = doc_type
        if status and "status" not in active_filters:
            active_filters["status"] = status
        allowed_filters = {
            "doc_id": "d.doc_id",
            "doc_family_id": "d.doc_family_id",
            "doc_type": "d.doc_type",
            "status": "d.status",
            "version_label": "d.version_label",
        }
        unknown = sorted(set(active_filters) - set(allowed_filters))
        if unknown:
            raise ValueError(f"Unsupported search filters: {', '.join(unknown)}")
        params: List[object] = [fts_query]
        filter_clauses = []
        for key in sorted(active_filters):
            value = active_filters[key]
            if value is None or value == "":
                continue
            filter_clauses.append(f"{allowed_filters[key]} = ?")
            params.append(str(value))
        filter_sql = " AND ".join(filter_clauses) if filter_clauses else "1 = 1"
        params.append(top_k)
        rows = self.conn.execute(
            f"""
            SELECT
                cu.unit_id, cu.doc_id, d.title, cu.heading_path,
                cu.page_start, cu.page_end, cu.raw_text,
                d.doc_family_id, d.version_label, d.effective_from, d.effective_to,
                bm25(content_units_fts, 3.0, 2.5, 1.5, 2.0, 2.0, 1.2, 1.0) AS rank
            FROM content_units_fts
            JOIN content_units cu ON cu.rowid = content_units_fts.rowid
            JOIN documents d ON d.doc_id = cu.doc_id
            WHERE content_units_fts MATCH ? AND {filter_sql}
            ORDER BY rank
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            SearchHit(
                row["unit_id"],
                row["doc_id"],
                row["title"],
                row["heading_path"] or "",
                row["page_start"],
                row["page_end"],
                row["raw_text"],
                float(row["rank"]),
                row["doc_family_id"] or "",
                row["version_label"] or "",
                row["effective_from"] or "",
                row["effective_to"] or "",
            )
            for row in rows
        ]

    def read_units(self, unit_ids: Iterable[str]) -> List[SearchHit]:
        ids = list(unit_ids)
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"""
            SELECT
                cu.unit_id, cu.doc_id, d.title, cu.heading_path,
                cu.page_start, cu.page_end, cu.raw_text,
                d.doc_family_id, d.version_label, d.effective_from, d.effective_to,
                0.0 AS rank
            FROM content_units cu
            JOIN documents d ON d.doc_id = cu.doc_id
            WHERE cu.unit_id IN ({placeholders})
            ORDER BY cu.doc_id, cu.sequence_no
            """,
            ids,
        ).fetchall()
        return [
            SearchHit(
                row["unit_id"],
                row["doc_id"],
                row["title"],
                row["heading_path"] or "",
                row["page_start"],
                row["page_end"],
                row["raw_text"],
                float(row["rank"]),
                row["doc_family_id"] or "",
                row["version_label"] or "",
                row["effective_from"] or "",
                row["effective_to"] or "",
            )
            for row in rows
        ]

    def expand_context(self, unit_id: str, depth: int = 1) -> List[SearchHit]:
        if depth > 1:
            depth = 1
        unit_ids = {unit_id}
        relation_rows = self.conn.execute(
            """
            SELECT to_unit_id
            FROM relations
            WHERE from_unit_id = ? AND relation_type IN ('previous', 'next', 'parent', 'child', 'references')
            """,
            (unit_id,),
        ).fetchall()
        unit_ids.update(row["to_unit_id"] for row in relation_rows)
        rows = self.read_units(unit_ids)
        if not rows:
            return []
        return rows

    def get_document(self, doc_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()

    def get_document_outline(self, doc_id: str) -> List[str]:
        rows = self.conn.execute(
            """
            SELECT heading_path, MIN(sequence_no) AS first_sequence
            FROM content_units
            WHERE doc_id = ? AND ifnull(heading_path, '') != ''
            GROUP BY heading_path
            ORDER BY first_sequence
            """,
            (doc_id,),
        ).fetchall()
        return [str(row["heading_path"]) for row in rows]

    def record_tool_call(self, trace_id: str, call_index: int, tool: str, args: Mapping[str, object], result_count: int) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO tool_traces(trace_id, call_index, tool, args_json, result_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (trace_id, call_index, tool, json.dumps(args, ensure_ascii=False, sort_keys=True), result_count),
        )
        self.conn.commit()

    def get_tool_trace(self, trace_id: str) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM tool_traces WHERE trace_id = ? ORDER BY call_index",
            (trace_id,),
        ).fetchall()

    def list_tool_traces(self) -> List[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT trace_id, COUNT(*) AS call_count, MIN(created_at) AS first_call_at, MAX(created_at) AS last_call_at
            FROM tool_traces
            GROUP BY trace_id
            ORDER BY last_call_at DESC, trace_id
            """
        ).fetchall()

    def get_applicable_version(self, doc_family_id: str, as_of: str = "") -> Optional[sqlite3.Row]:
        """Resolve the active document version for a family and optional ISO date."""

        if as_of:
            return self.conn.execute(
                """
                SELECT *
                FROM documents
                WHERE doc_family_id = ?
                  AND status = 'active'
                  AND (effective_from IS NULL OR effective_from = '' OR effective_from <= ?)
                  AND (effective_to IS NULL OR effective_to = '' OR effective_to >= ?)
                ORDER BY effective_from DESC, ingest_time DESC
                LIMIT 1
                """,
                (doc_family_id, as_of, as_of),
            ).fetchone()
        return self.conn.execute(
            """
            SELECT *
            FROM documents
            WHERE doc_family_id = ? AND status = 'active'
            ORDER BY
                CASE WHEN effective_from IS NULL OR effective_from = '' THEN 0 ELSE 1 END DESC,
                effective_from DESC,
                ingest_time DESC
            LIMIT 1
            """,
            (doc_family_id,),
        ).fetchone()

    def version_conflicts(self) -> List[str]:
        rows = self.conn.execute(
            """
            SELECT doc_id, doc_family_id, version_label, effective_from, effective_to, status
            FROM documents
            WHERE status = 'active'
            ORDER BY doc_family_id, effective_from, ingest_time
            """
        ).fetchall()
        conflicts: List[str] = []
        by_family: dict[str, List[sqlite3.Row]] = {}
        labels_seen: set[tuple[str, str]] = set()
        for row in rows:
            family = str(row["doc_family_id"] or row["doc_id"])
            by_family.setdefault(family, []).append(row)
            label = str(row["version_label"] or "").strip()
            if label:
                key = (family, label)
                if key in labels_seen:
                    conflicts.append(f"{family}: duplicate active version_label {label}")
                labels_seen.add(key)
        for family, family_rows in by_family.items():
            for left_index, left in enumerate(family_rows):
                for right in family_rows[left_index + 1 :]:
                    if effective_windows_overlap(left["effective_from"] or "", left["effective_to"] or "", right["effective_from"] or "", right["effective_to"] or ""):
                        conflicts.append(f"{family}: overlapping active versions {left['doc_id']} and {right['doc_id']}")
        return conflicts


def manifest_meta(parsed: DocumentMeta, doc: Mapping[str, object], source_uri: str) -> DocumentMeta:
    doc_id = str(doc.get("doc_id") or parsed.doc_id)
    return replace(
        parsed,
        doc_id=doc_id,
        doc_family_id=str(doc.get("doc_family_id") or doc_id),
        title=str(doc.get("title") or parsed.title),
        doc_type=str(doc.get("doc_type") or doc.get("archetype") or parsed.doc_type),
        format=str(doc.get("format") or parsed.format),
        language=str(doc.get("language") or parsed.language),
        source_uri=source_uri,
        version_label=str(doc.get("version_label") or parsed.version_label),
        effective_from=str(doc.get("effective_from") or parsed.effective_from),
        effective_to=str(doc.get("effective_to") or parsed.effective_to),
        status="active" if str(doc.get("status") or parsed.status) == "accepted" else str(doc.get("status") or parsed.status),
    )


def parent_heading_path(heading_path: str) -> str:
    parts = [part.strip() for part in (heading_path or "").split(">") if part.strip()]
    if len(parts) <= 1:
        return ""
    return " > ".join(parts[:-1])


def previous_unit(units: List[ContentUnit], sequence_no: int) -> Optional[ContentUnit]:
    for unit in units:
        if unit.sequence_no == sequence_no - 1:
            return unit
    return None


def heuristic_relation_types(text: str) -> List[str]:
    folded = ascii_fold(text)
    relations = []
    if any(term in folded for term in ["ngoai le", "truong hop khan cap", "exception"]):
        relations.append("exception_to")
    if any(term in folded for term in ["thay the", "supersede", "supersedes"]):
        relations.append("supersedes")
    if any(term in folded for term in ["sua doi", "bo sung", "amend", "amends"]):
        relations.append("amends")
    if any(term in folded for term in ["dinh nghia", "la ", "defines"]):
        relations.append("defines")
    return relations


def referenced_units(units: List[ContentUnit], source: ContentUnit) -> List[ContentUnit]:
    folded = ascii_fold(source.raw_text)
    targets: List[ContentUnit] = []
    for unit in units:
        if unit.unit_id == source.unit_id:
            continue
        heading = unit.heading_path.split(">")[-1].strip()
        if heading and ascii_fold(heading) in folded:
            targets.append(unit)
    explicit_refs = re.findall(r"(dieu\s+\d+|khoan\s+\d+)", folded)
    for ref in explicit_refs:
        for unit in units:
            if unit.unit_id != source.unit_id and ref in ascii_fold(unit.heading_path + " " + unit.raw_text):
                targets.append(unit)
    seen = set()
    unique = []
    for target in targets:
        if target.unit_id not in seen:
            seen.add(target.unit_id)
            unique.append(target)
    return unique


def same_topic_keys(unit: ContentUnit) -> set[str]:
    keys: set[str] = set()
    heading_leaf = unit.heading_path.split(">")[-1].strip()
    if heading_leaf:
        keys.add("heading:" + ascii_fold(heading_leaf))
    for term in (unit.glossary_terms or "").split():
        if term:
            keys.add("term:" + ascii_fold(term))
    return keys


def effective_windows_overlap(left_from: str, left_to: str, right_from: str, right_to: str) -> bool:
    """Return true when two ISO-like effective windows overlap.

    Empty bounds are open-ended. The project stores dates as ISO-like strings,
    so lexicographic comparison is deterministic for the documented format.
    """

    min_date = "0000-00-00"
    max_date = "9999-99-99"
    left_start = left_from or min_date
    left_end = left_to or max_date
    right_start = right_from or min_date
    right_end = right_to or max_date
    return left_start <= right_end and right_start <= left_end
