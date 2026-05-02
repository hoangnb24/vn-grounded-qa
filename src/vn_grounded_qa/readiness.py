"""Governed-input readiness checks for release preparation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List
import re

from .corpus import validate_architecture_manifest, validate_pack_manifest
from .eval import validate_eval_set, validate_eval_taxonomy
from .risks import validate_risk_register


@dataclass(frozen=True)
class ReadinessItem:
    name: str
    ok: bool
    evidence: str
    details: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReadinessReport:
    ok: bool
    items: List[ReadinessItem]
    blockers: List[str]


def run_governed_readiness(
    manifest_path: Path,
    eval_path: Path,
    taxonomy_path: Path = Path("eval/taxonomy.yaml"),
    legal_pack_path: Path = Path("corpus/legal-regression/manifest.json"),
    shadow_pack_path: Path = Path("corpus/production-shadow/manifest.json"),
    risk_register_path: Path = Path("docs/RISK_REGISTER.md"),
    pyproject_path: Path = Path("pyproject.toml"),
    readme_path: Path = Path("README.md"),
    strict_risk_owners: bool = False,
) -> ReadinessReport:
    items = [
        _checked(
            "architecture corpus ready",
            lambda: _architecture_item(manifest_path),
        ),
        _checked(
            "evaluation taxonomy ready",
            lambda: _taxonomy_item(taxonomy_path),
        ),
        _checked(
            "governed MVP eval set ready",
            lambda: _eval_item(eval_path, taxonomy_path),
        ),
        _checked(
            "legal regression pack ready",
            lambda: _pack_item(legal_pack_path, "legal_regression"),
        ),
        _checked(
            "production shadow pack ready",
            lambda: _pack_item(shadow_pack_path, "production_shadow"),
        ),
        _checked(
            "risk register ready",
            lambda: _risk_item(risk_register_path, strict_risk_owners),
        ),
        _checked(
            "project license selected",
            lambda: validate_project_license(pyproject_path, readme_path),
        ),
    ]
    blockers = [item.name for item in items if not item.ok]
    return ReadinessReport(not blockers, items, blockers)


def _checked(name: str, fn: Callable[[], ReadinessItem]) -> ReadinessItem:
    try:
        return fn()
    except FileNotFoundError as exc:
        return ReadinessItem(name, False, str(exc.filename or exc), ["file missing"])
    except Exception as exc:
        return ReadinessItem(name, False, str(exc), [exc.__class__.__name__])


def _architecture_item(path: Path) -> ReadinessItem:
    result = validate_architecture_manifest(path, strict_m0=True)
    evidence = f"{path}:{result.document_count} docs; archetypes={result.archetype_counts}"
    return ReadinessItem("architecture corpus ready", result.ok and not result.warnings, evidence, [*result.errors, *result.warnings])


def _taxonomy_item(path: Path) -> ReadinessItem:
    errors = validate_eval_taxonomy(path)
    return ReadinessItem("evaluation taxonomy ready", not errors, str(path), errors)


def _eval_item(eval_path: Path, taxonomy_path: Path) -> ReadinessItem:
    result = validate_eval_set(eval_path, strict=True, taxonomy_path=taxonomy_path)
    evidence = f"{eval_path}:{result.total} questions; auto_generated={result.auto_generated_count}; categories={result.category_counts}"
    return ReadinessItem("governed MVP eval set ready", result.ok, evidence, [*result.errors, *result.warnings])


def _pack_item(path: Path, pack_type: str) -> ReadinessItem:
    result = validate_pack_manifest(path, pack_type)
    evidence = f"{path}:{result.document_count} docs"
    label = "legal regression pack ready" if pack_type == "legal_regression" else "production shadow pack ready"
    return ReadinessItem(label, result.ok and not result.warnings, evidence, [*result.errors, *result.warnings])


def _risk_item(path: Path, strict_risk_owners: bool) -> ReadinessItem:
    result = validate_risk_register(path, strict_owners=strict_risk_owners)
    label = "risk register ready"
    evidence = f"{path}:{result.risk_count} risks; statuses={result.statuses}"
    return ReadinessItem(label, result.ok, evidence, result.errors)


def validate_project_license(pyproject_path: Path, readme_path: Path) -> ReadinessItem:
    pyproject_text = pyproject_path.read_text(encoding="utf-8")
    readme_text = readme_path.read_text(encoding="utf-8")
    errors: List[str] = []
    license_text = ""

    match = re.search(r'license\s*=\s*\{\s*text\s*=\s*"([^"]*)"\s*\}', pyproject_text)
    if not match:
        errors.append(f"{pyproject_path}: missing project.license text")
    else:
        license_text = match.group(1).strip()
        if not license_text or license_text.upper() == "TBD":
            errors.append(f"{pyproject_path}: license is not selected")

    readme_license = _readme_license_section(readme_text)
    if not readme_license:
        errors.append(f"{readme_path}: missing License section content")
    elif readme_license.upper() == "TBD":
        errors.append(f"{readme_path}: license is not selected")

    if license_text and readme_license and license_text.upper() != "TBD" and readme_license.upper() != "TBD" and license_text != readme_license:
        errors.append(f"{readme_path}: license does not match {pyproject_path}")

    evidence = f"{pyproject_path}; {readme_path}"
    return ReadinessItem("project license selected", not errors, evidence, errors)


def _readme_license_section(text: str) -> str:
    match = re.search(r"^## License\s*\n(?P<body>.*?)(?:\n## |\Z)", text, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return ""
    return match.group("body").strip()
