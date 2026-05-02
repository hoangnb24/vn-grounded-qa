"""Parser-neutral ingestion into Parsed IR and canonical units."""

from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from .models import ContentUnit, DocumentMeta, ParsedBlock, ParsedIR
from .normalize import ascii_fold, normalize_text, segment_vi

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NUMBERED_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*\.?)\s+(.+?)\s*$")
FAQ_RE = re.compile(r"^(?:q|câu hỏi|hỏi)\s*[:：]\s*(.+)$", re.IGNORECASE)
FAQ_ANSWER_RE = re.compile(r"^(?:a|trả lời|đáp)\s*[:：]\s*(.+)$", re.IGNORECASE)
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+?)\s*$")
STEP_RE = re.compile(r"^(?:bước|step)\s+\d+\s*[:.)-]?\s+(.+)$", re.IGNORECASE)
LEGAL_ARTICLE_RE = re.compile(r"^điều\s+\d+[a-zA-Z]?\b", re.IGNORECASE)
LEGAL_CLAUSE_RE = re.compile(r"^(?:khoản\s+\d+|[a-zđ]\)|\d+[.)])\s+", re.IGNORECASE)
IMAGE_RE = re.compile(r"!\[(?P<caption>[^\]]*)\]\((?P<src>[^)]+)\)")
IDENTIFIER_RE = re.compile(
    r"(?<!\w)(?:/[A-Za-z0-9_./-]+|[A-Z]{2,}[A-Z0-9_./-]*|[A-Z]+-\d+[A-Z0-9-]*|\d+(?:\.\d+)+|[A-Za-z]+_[A-Za-z0-9_]+)(?!\w)"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_id(*parts: object, prefix: str = "") -> str:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}{digest}" if prefix else digest


SUPPORTED_PARSERS = {"auto", "fallback", "docling", "marker"}


def parse_file(path: Path, parser: str = "auto") -> ParsedIR:
    if parser not in SUPPORTED_PARSERS:
        raise ValueError(f"Unsupported parser: {parser}")
    if parser == "auto":
        return parse_auto(path)
    if parser == "docling":
        return parse_docling(path)
    if parser == "marker":
        return parse_marker(path)
    return parse_fallback(path)


def parse_auto(path: Path) -> ParsedIR:
    errors: List[str] = []
    for parser in ["docling", "marker"]:
        try:
            return parse_file(path, parser=parser)
        except Exception as exc:  # noqa: BLE001 - auto mode must degrade to the local parser.
            errors.append(f"{parser}: {exc}")
    ir = parse_fallback(path)
    warnings = list(ir.quality.get("parser_warnings") or [])
    warnings.append("auto parser fell back to local parser after optional parser failures: " + " | ".join(errors))
    return ParsedIR(ir.document_meta, ir.pages, ir.blocks, {**ir.quality, "parser_warnings": warnings})


def parse_fallback(path: Path) -> ParsedIR:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return parse_markdown(path)
    if suffix in {".txt", ".text"}:
        return parse_text(path)
    if suffix == ".pdf":
        return parse_pdf(path)
    raise ValueError(f"Unsupported source format: {path.suffix}")


def parse_docling(path: Path) -> ParsedIR:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise RuntimeError("Docling parser unavailable. Install with: pip install 'vn-grounded-qa[docling]'") from exc

    data = path.read_bytes()
    converter = DocumentConverter()
    result = converter.convert(str(path))
    document = result.document
    if hasattr(document, "export_to_markdown"):
        markdown = document.export_to_markdown()
    elif hasattr(document, "export_to_text"):
        markdown = document.export_to_text()
    else:
        raise RuntimeError("Docling document object has no export_to_markdown/export_to_text method")
    return parse_markdown_text(path, data, markdown, "docling")


def parse_marker(path: Path) -> ParsedIR:
    data = path.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        commands = [
            ["marker_single", str(path), "--output_dir", str(output_dir), "--output_format", "markdown"],
            ["marker", str(path), "--output_dir", str(output_dir), "--output_format", "markdown"],
        ]
        last_error = ""
        for command in commands:
            try:
                completed = subprocess.run(command, check=False, capture_output=True, text=True)
            except FileNotFoundError as exc:
                last_error = str(exc)
                continue
            if completed.returncode != 0:
                last_error = (completed.stderr or completed.stdout or "").strip()
                continue
            markdown_files = sorted(output_dir.rglob("*.md"))
            if markdown_files:
                markdown = markdown_files[0].read_text(encoding="utf-8")
                return parse_markdown_text(path, data, markdown, "marker")
            last_error = "Marker completed but produced no Markdown file"
        raise RuntimeError("Marker parser unavailable or failed. Install with: pip install 'vn-grounded-qa[marker]'. Last error: " + last_error)


def document_meta(path: Path, data: bytes, parser_name: str) -> DocumentMeta:
    title = path.stem.replace("_", " ").replace("-", " ").strip() or path.name
    return DocumentMeta(
        doc_id=stable_id(path.resolve(), sha256_bytes(data), prefix="doc_"),
        source_uri=str(path),
        source_hash=sha256_bytes(data),
        format=path.suffix.lower().lstrip(".") or "txt",
        parser_name=parser_name,
        parser_version="0.1.0",
        doc_family_id="",
        title=title,
    )


def parse_markdown(path: Path) -> ParsedIR:
    data = path.read_bytes()
    text = data.decode("utf-8")
    return parse_markdown_text(path, data, text, "markdown-lite")


def parse_markdown_text(path: Path, data: bytes, text: str, parser_name: str) -> ParsedIR:
    blocks: List[ParsedBlock] = []
    paragraph: List[str] = []
    code_lines: List[str] = []
    table_rows: List[str] = []
    list_items: List[Tuple[str, str]] = []
    in_code = False
    code_info = ""
    order = 0

    def next_order() -> int:
        nonlocal order
        value = order
        order += 1
        return value

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            value = "\n".join(paragraph).strip()
            block_type = classify_text_block(value)
            block_order = next_order()
            blocks.append(ParsedBlock(stable_id(path, block_order, value, prefix="blk_"), block_type, value, block_order))
            paragraph = []

    def flush_code() -> None:
        nonlocal code_lines, code_info
        value = "\n".join(code_lines).strip("\n")
        block_order = next_order()
        blocks.append(
            ParsedBlock(
                stable_id(path, block_order, value, prefix="blk_"),
                "code_block",
                value,
                block_order,
                attributes={"language": code_info},
            )
        )
        code_lines = []
        code_info = ""

    def flush_table() -> None:
        nonlocal table_rows
        if not table_rows:
            return
        table_text = "\n".join(table_rows)
        table_order = next_order()
        table_id = stable_id(path, table_order, table_text, prefix="blk_")
        blocks.append(ParsedBlock(table_id, "table", table_text, table_order))
        for row_index, row in enumerate(table_rows):
            row_order = next_order()
            row_id = stable_id(path, row_order, row, prefix="blk_")
            blocks.append(ParsedBlock(row_id, "table_row", row, row_order, parent_block_id=table_id, attributes={"row_index": row_index}))
            for cell_index, cell in enumerate(markdown_table_cells(row)):
                cell_order = next_order()
                blocks.append(
                    ParsedBlock(
                        stable_id(path, cell_order, cell, prefix="blk_"),
                        "table_cell",
                        cell,
                        cell_order,
                        parent_block_id=row_id,
                        attributes={"row_index": row_index, "cell_index": cell_index},
                    )
                )
        table_rows = []

    def flush_list() -> None:
        nonlocal list_items
        if not list_items:
            return
        list_text = "\n".join(raw for raw, _ in list_items)
        list_order = next_order()
        list_id = stable_id(path, list_order, list_text, prefix="blk_")
        blocks.append(ParsedBlock(list_id, "list", list_text, list_order))
        for item_index, (raw, value) in enumerate(list_items):
            item_order = next_order()
            block_type = "step" if STEP_RE.match(value) or STEP_RE.match(raw.strip()) else "list_item"
            blocks.append(
                ParsedBlock(
                    stable_id(path, item_order, raw, prefix="blk_"),
                    block_type,
                    value,
                    item_order,
                    parent_block_id=list_id,
                    attributes={"item_index": item_index},
                )
            )
        list_items = []

    def flush_structured_runs() -> None:
        flush_table()
        flush_list()

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                flush_structured_runs()
                flush_paragraph()
                in_code = True
                code_info = line.strip().strip("`").strip()
            continue
        if in_code:
            code_lines.append(line.rstrip())
            continue

        heading = HEADING_RE.match(line)
        if heading:
            flush_structured_runs()
            flush_paragraph()
            heading_text = heading.group(2).strip()
            level = len(heading.group(1))
            block_type = heading_block_type(heading_text, level, blocks)
            block_order = next_order()
            blocks.append(
                ParsedBlock(
                    stable_id(path, block_order, line, prefix="blk_"),
                    block_type,
                    heading_text,
                    block_order,
                    attributes={"level": level},
                )
            )
        elif line.strip().startswith("|") and line.strip().endswith("|"):
            flush_list()
            flush_paragraph()
            table_rows.append(line.strip())
        elif IMAGE_RE.search(line.strip()):
            flush_structured_runs()
            flush_paragraph()
            image = IMAGE_RE.search(line.strip())
            assert image is not None
            caption = image.group("caption").strip()
            block_text = caption or image.group("src").strip()
            block_order = next_order()
            blocks.append(
                ParsedBlock(
                    stable_id(path, block_order, line, prefix="blk_"),
                    "figure",
                    block_text,
                    block_order,
                    attributes={"src": image.group("src").strip()},
                )
            )
            if caption:
                caption_order = next_order()
                blocks.append(ParsedBlock(stable_id(path, caption_order, caption, prefix="blk_"), "caption", caption, caption_order))
        elif line.lstrip().startswith(">"):
            flush_structured_runs()
            flush_paragraph()
            value = line.lstrip()[1:].strip()
            block_order = next_order()
            blocks.append(ParsedBlock(stable_id(path, block_order, value, prefix="blk_"), "quote", value, block_order))
        elif LIST_ITEM_RE.match(line):
            flush_table()
            flush_paragraph()
            value = LIST_ITEM_RE.match(line).group(1).strip()  # type: ignore[union-attr]
            list_items.append((line, value))
        elif not line.strip():
            flush_structured_runs()
            flush_paragraph()
        else:
            flush_structured_runs()
            paragraph.append(line.rstrip())
    if in_code:
        flush_code()
    flush_structured_runs()
    flush_paragraph()
    meta = document_meta(path, data, parser_name)
    return ParsedIR(meta, [{"page_no": 1, "dimensions": None, "blocks": [b.block_id for b in blocks]}], blocks, quality(blocks))


def parse_text(path: Path) -> ParsedIR:
    data = path.read_bytes()
    text = data.decode("utf-8")
    blocks: List[ParsedBlock] = []
    paragraphs = [chunk.strip() for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]
    for order, paragraph in enumerate(paragraphs):
        block_type = "heading" if NUMBERED_HEADING_RE.match(paragraph.splitlines()[0]) else classify_text_block(paragraph)
        blocks.append(ParsedBlock(stable_id(path, order, paragraph, prefix="blk_"), block_type, paragraph, order))
    meta = document_meta(path, data, "text-lite")
    return ParsedIR(meta, [{"page_no": 1, "dimensions": None, "blocks": [b.block_id for b in blocks]}], blocks, quality(blocks))


def parse_pdf(path: Path) -> ParsedIR:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF ingestion requires the optional dependency: pip install 'vn-grounded-qa[pdf]'") from exc

    data = path.read_bytes()
    reader = PdfReader(str(path))
    blocks: List[ParsedBlock] = []
    pages = []
    order = 0
    for page_index, page in enumerate(reader.pages, start=1):
        page_blocks = []
        text = page.extract_text() or ""
        for paragraph in [chunk.strip() for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]:
            block = ParsedBlock(stable_id(path, page_index, order, paragraph, prefix="blk_"), "paragraph", paragraph, order, page_index)
            blocks.append(block)
            page_blocks.append(block.block_id)
            order += 1
        pages.append({"page_no": page_index, "dimensions": None, "blocks": page_blocks})
    meta = document_meta(path, data, "pypdf-lite")
    return ParsedIR(meta, pages, blocks, quality(blocks))


def quality(blocks: Sequence[ParsedBlock]) -> dict:
    heading_count = sum(1 for block in blocks if block.block_type in {"title", "heading", "legal_article", "legal_clause"})
    return {
        "ocr_coverage": None,
        "block_count": len(blocks),
        "heading_confidence": 1.0 if heading_count else 0.5,
        "parser_warnings": [],
    }


def units_from_ir(ir: ParsedIR) -> List[ContentUnit]:
    units: List[ContentUnit] = []
    headings: List[Tuple[int, str]] = []
    pending_table: List[ParsedBlock] = []

    def current_heading_path() -> str:
        return " > ".join(title for _, title in headings)

    def add_unit(blocks: Iterable[ParsedBlock], unit_type: str) -> None:
        block_list = list(blocks)
        if not block_list:
            return
        raw_text = "\n".join(block.text for block in block_list).strip()
        searchable_text = markdown_table_shadow(raw_text) if unit_type == "table" else raw_text
        if not raw_text:
            return
        seq = len(units) + 1
        heading_path = current_heading_path()
        page_start = min(block.page_no for block in block_list)
        page_end = max(block.page_no for block in block_list)
        unit_hash = sha256_bytes(raw_text.encode("utf-8"))
        units.append(
            ContentUnit(
                unit_id=stable_id(ir.document_meta.doc_id, seq, unit_hash, prefix="unit_"),
                doc_id=ir.document_meta.doc_id,
                parent_unit_id=None,
                unit_type=unit_type,
                heading_path=heading_path,
                ordinal_path=str(seq),
                sequence_no=seq,
                page_start=page_start,
                page_end=page_end,
                raw_text=searchable_text,
                normalized_text=normalize_text(searchable_text),
                vi_segmented_text=segment_vi(searchable_text),
                ascii_folded_text=ascii_fold(searchable_text),
                glossary_terms=extract_glossary_terms(searchable_text),
                table_text=searchable_text if unit_type == "table" else "",
                unit_hash=unit_hash,
            )
        )

    index = 0
    while index < len(ir.blocks):
        block = ir.blocks[index]
        if block.block_type in {"title", "heading", "legal_article", "legal_clause"}:
            if pending_table:
                add_unit(pending_table, "table")
                pending_table = []
            level = int(block.attributes.get("level", 1))
            headings = [(lvl, title) for lvl, title in headings if lvl < level]
            headings.append((level, block.text.strip()))
            index += 1
            continue
        if block.block_type == "table_row":
            pending_table.append(block)
            index += 1
            continue
        if block.block_type in {"list", "table", "table_cell"}:
            index += 1
            continue
        if pending_table:
            add_unit(pending_table, "table")
            pending_table = []
        if FAQ_RE.match(block.text.strip()):
            next_block = ir.blocks[index + 1] if index + 1 < len(ir.blocks) else None
            if next_block and FAQ_ANSWER_RE.match(next_block.text.strip()):
                add_unit([block, next_block], "faq_answer")
                index += 2
                continue
            add_unit([block], "faq_question")
            index += 1
            continue
        add_unit([block], block.block_type)
        index += 1
    if pending_table:
        add_unit(pending_table, "table")
    return attach_parent_unit_ids(units)


def attach_parent_unit_ids(units: List[ContentUnit]) -> List[ContentUnit]:
    first_unit_by_heading: dict[str, ContentUnit] = {}
    for unit in units:
        if unit.heading_path and unit.heading_path not in first_unit_by_heading:
            first_unit_by_heading[unit.heading_path] = unit
    with_parents = []
    for unit in units:
        parent_id = None
        parent_heading = parent_heading_path(unit.heading_path)
        if parent_heading:
            parent = first_unit_by_heading.get(parent_heading)
            if parent and parent.unit_id != unit.unit_id:
                parent_id = parent.unit_id
        with_parents.append(replace(unit, parent_unit_id=parent_id))
    return with_parents


def heading_block_type(text: str, level: int, existing_blocks: Sequence[ParsedBlock]) -> str:
    if level == 1 and not any(block.block_type in {"title", "heading"} for block in existing_blocks):
        return "title"
    if LEGAL_ARTICLE_RE.match(text):
        return "legal_article"
    if LEGAL_CLAUSE_RE.match(text):
        return "legal_clause"
    return "heading"


def classify_text_block(text: str) -> str:
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    if FAQ_RE.match(first_line):
        return "faq_question"
    if FAQ_ANSWER_RE.match(first_line):
        return "faq_answer"
    if STEP_RE.match(first_line):
        return "step"
    if LEGAL_ARTICLE_RE.match(first_line):
        return "legal_article"
    if LEGAL_CLAUSE_RE.match(first_line):
        return "legal_clause"
    return "paragraph"


def extract_glossary_terms(text: str) -> str:
    terms = IDENTIFIER_RE.findall(text)
    return " ".join(sorted(set(terms)))


def markdown_table_shadow(text: str) -> str:
    rows = []
    for line in text.splitlines():
        cells = markdown_table_cells(line)
        if cells and not all(set(cell) <= {"-", ":"} for cell in cells):
            rows.append(cells)
    if len(rows) < 2:
        return text
    headers = rows[0]
    values = rows[1:]
    lines = []
    for row in values:
        pairs = []
        for index, value in enumerate(row):
            header = headers[index] if index < len(headers) else f"Cột {index + 1}"
            pairs.append(f"{header}: {value}")
        lines.append("; ".join(pairs))
    return "\n".join(lines)


def markdown_table_cells(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parent_heading_path(heading_path: str) -> str:
    parts = [part.strip() for part in (heading_path or "").split(">") if part.strip()]
    if len(parts) <= 1:
        return ""
    return " > ".join(parts[:-1])
