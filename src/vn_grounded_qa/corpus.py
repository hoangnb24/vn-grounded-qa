"""Corpus manifest validation for milestone gates."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

REQUIRED_ARCHETYPES = {"legal", "policy_sop", "technical_markdown", "table_pdf", "faq"}
LEGAL_REGRESSION_COVERAGE_TAGS = {"legal_citation", "cross_reference", "version_status"}
PRODUCTION_SHADOW_COVERAGE_TAGS = {"representative_deployment", "governed_provenance"}
REQUIRED_DOC_FIELDS = {
    "doc_id",
    "title",
    "doc_type",
    "archetype",
    "source_uri",
    "format",
    "language",
    "provenance_owner",
    "license",
    "status",
}
ALLOWED_DOCUMENT_STATUSES = {"candidate", "accepted", "active", "rejected", "shadow"}


@dataclass(frozen=True)
class CorpusValidationResult:
    ok: bool
    document_count: int
    archetype_counts: Dict[str, int]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PackValidationResult:
    ok: bool
    pack_type: str
    document_count: int
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def load_manifest(path: Path) -> Mapping[str, object]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Corpus manifest must be a JSON object")
    return data


def validate_architecture_manifest(path: Path, strict_m0: bool = True) -> CorpusValidationResult:
    manifest = load_manifest(path)
    docs = manifest.get("documents")
    errors: List[str] = []
    warnings: List[str] = []
    if not isinstance(docs, list):
        return CorpusValidationResult(False, 0, {}, ["documents must be a list"], [])

    seen_ids = set()
    archetype_counts: Dict[str, int] = {}
    for index, doc in enumerate(docs):
        location = f"documents[{index}]"
        if not isinstance(doc, dict):
            errors.append(f"{location} must be an object")
            continue
        missing = sorted(field for field in REQUIRED_DOC_FIELDS if not str(doc.get(field, "")).strip())
        if missing:
            errors.append(f"{location} missing required fields: {', '.join(missing)}")
        doc_id = str(doc.get("doc_id", "")).strip()
        if doc_id in seen_ids:
            errors.append(f"{location} duplicate doc_id: {doc_id}")
        if doc_id:
            seen_ids.add(doc_id)
        archetype = str(doc.get("archetype", "")).strip()
        if archetype:
            archetype_counts[archetype] = archetype_counts.get(archetype, 0) + 1
            if archetype not in REQUIRED_ARCHETYPES:
                errors.append(f"{location} unknown archetype: {archetype}")
        source_uri = str(doc.get("source_uri", "")).strip()
        if source_uri and not source_exists(path.parent, source_uri):
            warnings.append(f"{location} source_uri does not exist locally: {source_uri}")
        if doc.get("status") not in ALLOWED_DOCUMENT_STATUSES:
            errors.append(f"{location} status must be candidate, accepted, active, rejected, or shadow")
        validate_effective_window(doc, location, errors)

    if strict_m0:
        count = len(docs)
        if count < 24 or count > 36:
            errors.append(f"M0 architecture corpus must contain 24-36 documents; found {count}")
        missing_arch = sorted(REQUIRED_ARCHETYPES - set(archetype_counts))
        if missing_arch:
            errors.append(f"M0 architecture corpus missing archetypes: {', '.join(missing_arch)}")

    return CorpusValidationResult(not errors, len(docs), dict(sorted(archetype_counts.items())), errors, warnings)


def validate_pack_manifest(path: Path, pack_type: str) -> PackValidationResult:
    manifest = load_manifest(path)
    docs = manifest.get("documents")
    errors: List[str] = []
    warnings: List[str] = []
    if not isinstance(docs, list):
        return PackValidationResult(False, pack_type, 0, ["documents must be a list"], [])
    for index, doc in enumerate(docs):
        location = f"documents[{index}]"
        if not isinstance(doc, dict):
            errors.append(f"{location} must be an object")
            continue
        missing = sorted(field for field in REQUIRED_DOC_FIELDS if not str(doc.get(field, "")).strip())
        if missing:
            errors.append(f"{location} missing required fields: {', '.join(missing)}")
        if pack_type == "legal_regression" and str(doc.get("archetype")) != "legal":
            errors.append(f"{location} legal regression pack only accepts legal archetype")
        if pack_type == "production_shadow" and str(doc.get("status")) != "shadow":
            errors.append(f"{location} production shadow documents must use status=shadow")
        source_uri = str(doc.get("source_uri", "")).strip()
        if source_uri and not source_exists(path.parent, source_uri):
            warnings.append(f"{location} source_uri does not exist locally: {source_uri}")
        validate_effective_window(doc, location, errors)
    if pack_type == "legal_regression" and not (12 <= len(docs) <= 20):
        errors.append(f"legal regression pack must contain 12-20 documents; found {len(docs)}")
    if pack_type == "legal_regression":
        coverage = collect_coverage_tags(docs)
        missing = sorted(LEGAL_REGRESSION_COVERAGE_TAGS - coverage)
        if missing:
            errors.append(f"legal regression pack missing coverage tags: {', '.join(missing)}")
    if pack_type == "production_shadow" and len(docs) < 1:
        errors.append("production shadow pack must contain at least 1 document")
    if pack_type == "production_shadow":
        coverage = collect_coverage_tags(docs)
        missing = sorted(PRODUCTION_SHADOW_COVERAGE_TAGS - coverage)
        if missing:
            errors.append(f"production shadow pack missing coverage tags: {', '.join(missing)}")
    return PackValidationResult(not errors, pack_type, len(docs), errors, warnings)


def collect_coverage_tags(docs: object) -> set[str]:
    tags: set[str] = set()
    if not isinstance(docs, list):
        return tags
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        value = doc.get("coverage_tags") or []
        if isinstance(value, list):
            tags.update(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, str):
            tags.update(item.strip() for item in value.split(",") if item.strip())
    return tags


def write_pack_template(path: Path, pack_type: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "name": pack_type,
        "description": f"{pack_type} corpus manifest.",
        "documents": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_synthetic_pack(path: Path, pack_type: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fixtures = path.parent / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    if pack_type == "legal_regression":
        docs: List[Dict[str, str]] = []
        for index in range(1, 13):
            doc_id = f"synthetic_legal_regression_{index:02d}"
            filename = f"{doc_id}.md"
            (fixtures / filename).write_text(
                f"""# Quy định pháp lý hồi quy {index:02d}

## Điều 1. Hiệu lực

Quy định LEGAL-REG-{index:02d} có hiệu lực từ ngày 2026-01-01.

## Điều 2. Dẫn chiếu

Khoản này tham chiếu Điều 1 và yêu cầu lưu citation chính xác.
""",
                encoding="utf-8",
            )
            stub = document_stub(doc_id, f"Quy định pháp lý hồi quy {index:02d}", "legal", f"fixtures/{filename}", "md")
            stub["status"] = "accepted"
            stub["doc_family_id"] = f"legal_regression_family_{index:02d}"
            stub["version_label"] = "v1"
            stub["coverage_tags"] = ["legal_citation", "cross_reference", "version_status"]
            docs.append(stub)
        write_manifest_template(path, docs)
        return
    if pack_type == "production_shadow":
        filename = "synthetic_shadow_01.md"
        (fixtures / filename).write_text(
            """# Production Shadow FAQ

## Câu hỏi thường gặp

Hỏi: Shadow corpus dùng để làm gì?

Đáp: Shadow corpus kiểm tra hệ thống trên tài liệu được quản trị nhưng không dùng để huấn luyện prompt.
""",
            encoding="utf-8",
        )
        stub = document_stub("synthetic_shadow_01", "Production Shadow FAQ", "faq", f"fixtures/{filename}", "md")
        stub["status"] = "shadow"
        stub["coverage_tags"] = ["representative_deployment", "governed_provenance"]
        write_manifest_template(path, [stub])
        return
    raise ValueError(f"Unsupported pack type: {pack_type}")


def source_exists(manifest_dir: Path, source_uri: str) -> bool:
    if source_uri.startswith(("http://", "https://", "s3://", "gs://")):
        return True
    path = Path(source_uri)
    if not path.is_absolute():
        path = manifest_dir / path
    return path.exists()


def validate_effective_window(doc: Mapping[str, object], location: str, errors: List[str]) -> None:
    effective_from = str(doc.get("effective_from") or "").strip()
    effective_to = str(doc.get("effective_to") or "").strip()
    if effective_from and effective_to and effective_from > effective_to:
        errors.append(f"{location} effective_from must be <= effective_to")


def write_manifest_template(path: Path, documents: Sequence[Mapping[str, object]] = ()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "name": "architecture_corpus_v1",
        "description": "Architecture corpus for Vietnamese Grounded QA M0/M1/M2 gates.",
        "documents": list(documents),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def document_stub(doc_id: str, title: str, archetype: str, source_uri: str, fmt: str = "md") -> Dict[str, str]:
    return {
        "doc_id": doc_id,
        "title": title,
        "doc_type": archetype,
        "archetype": archetype,
        "source_uri": source_uri,
        "format": fmt,
        "language": "vi",
        "provenance_owner": "repo-seed",
        "license": "internal-test-fixture",
        "status": "candidate",
        "notes": "Synthetic seed document for validator and pipeline smoke tests.",
    }


def write_synthetic_architecture_corpus(manifest_path: Path, docs_per_archetype: int = 5) -> None:
    """Create a deterministic synthetic M0-sized corpus for local gates.

    The generated documents are fixtures, not a substitute for a governed
    production corpus. They exist so parser, retrieval, and orchestration gates
    can run before private enterprise documents are selected.
    """

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    fixtures_dir = manifest_path.parent / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    documents: List[Dict[str, str]] = []
    for archetype in sorted(REQUIRED_ARCHETYPES):
        for index in range(1, docs_per_archetype + 1):
            doc_id = f"synthetic_{archetype}_{index:02d}"
            filename = f"{doc_id}.md"
            title = synthetic_title(archetype, index)
            (fixtures_dir / filename).write_text(synthetic_document(archetype, index, title), encoding="utf-8")
            stub = document_stub(doc_id, title, archetype, f"fixtures/{filename}", "md")
            stub["status"] = "accepted"
            stub["doc_family_id"] = f"family_{archetype}_{index:02d}"
            stub["version_label"] = "v1"
            stub["notes"] = "Synthetic architecture corpus fixture; replace with governed document for release gates."
            documents.append(stub)
    write_manifest_template(manifest_path, documents)


def synthetic_title(archetype: str, index: int) -> str:
    labels = {
        "faq": "FAQ Hệ thống nhân sự",
        "legal": "Quy định tuân thủ nội bộ",
        "policy_sop": "SOP phê duyệt nghiệp vụ",
        "table_pdf": "Bảng hạn mức vận hành",
        "technical_markdown": "Tài liệu kỹ thuật module",
    }
    return f"{labels[archetype]} {index:02d}"


def synthetic_document(archetype: str, index: int, title: str) -> str:
    code = f"{archetype.upper().replace('_', '-')}-{index:02d}"
    if archetype == "legal":
        return f"""# {title}

## Điều 1. Phạm vi áp dụng

Quy định {code} áp dụng cho nhân viên chính thức khi xử lý hồ sơ khách hàng.

## Điều 2. Nghĩa vụ lưu vết

Nhân viên phải lưu bằng chứng phê duyệt trong hệ thống HRM trước khi hoàn tất hồ sơ.

## Khoản 2. Ngoại lệ

Trường hợp khẩn cấp phải được trưởng bộ phận xác nhận bằng email trong vòng 24 giờ.
"""
    if archetype == "policy_sop":
        return f"""# {title}

## Mục đích

SOP {code} mô tả quy trình phê duyệt yêu cầu trên HRM.

## Các bước

1. Nhân viên tạo yêu cầu và đính kèm bằng chứng.
2. Quản lý trực tiếp kiểm tra thông tin.
3. Bộ phận nhân sự phê duyệt cuối cùng trong 2 ngày làm việc.

## Kiểm soát

Yêu cầu thiếu bằng chứng phải trả về trạng thái bổ sung.
"""
    if archetype == "technical_markdown":
        return f"""# {title}

## API tra cứu

Module {code} cung cấp endpoint `/search_units` để tìm evidence unit theo từ khóa.

## Cấu hình

Biến `QA_TOP_K` đặt số lượng kết quả mặc định. Giá trị khuyến nghị là 10.

## Lỗi thường gặp

Nếu không có citation, hệ thống phải trả về insufficient evidence.
"""
    if archetype == "table_pdf":
        return f"""# {title}

## Bảng hạn mức

| Loại yêu cầu | Hạn mức | Người phê duyệt |
|---|---:|---|
| Mua công cụ {index} | 5000000 VND | Quản lý trực tiếp |
| Gia hạn dịch vụ {index} | 12000000 VND | Trưởng bộ phận |

## Ghi chú

Bảng {code} là fixture Markdown mô phỏng table-heavy PDF cho kiểm thử parser.
"""
    return f"""# {title}

## Câu hỏi thường gặp

Hỏi: HRM dùng để làm gì trong quy trình {index}?

Đáp: HRM dùng để tạo yêu cầu, lưu bằng chứng và theo dõi trạng thái phê duyệt.

Hỏi: Khi thiếu bằng chứng thì xử lý thế nào?

Đáp: Hệ thống trả yêu cầu về trạng thái bổ sung.
"""
