"""Risk register validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

ALLOWED_RISK_STATUSES = {"open", "mitigating", "accepted", "closed"}
REQUIRED_RISK_IDS = {"CR-1", "CR-2", "CR-3", "CR-4", "CR-5", "MR-1", "MR-2", "MR-3"}


@dataclass(frozen=True)
class RiskRegisterValidationResult:
    ok: bool
    risk_count: int
    statuses: Dict[str, int]
    errors: List[str] = field(default_factory=list)


def validate_risk_register(path: Path, strict_owners: bool = False) -> RiskRegisterValidationResult:
    rows = parse_markdown_table(path)
    errors: List[str] = []
    statuses: Dict[str, int] = {}
    seen = set()
    for row in rows:
        risk_id = row.get("ID", "").strip()
        if not risk_id or risk_id == "---":
            continue
        seen.add(risk_id)
        for field in ["Risk", "Detector", "Mitigation", "Owner", "Status"]:
            if not row.get(field, "").strip():
                errors.append(f"{risk_id}: missing {field}")
        owner = row.get("Owner", "").strip()
        if strict_owners and is_placeholder_owner(owner):
            errors.append(f"{risk_id}: owner must be a deployment owner, not placeholder role owner: {owner}")
        status = row.get("Status", "").strip()
        statuses[status] = statuses.get(status, 0) + 1
        if status not in ALLOWED_RISK_STATUSES:
            errors.append(f"{risk_id}: invalid status {status}")
    missing = sorted(REQUIRED_RISK_IDS - seen)
    if missing:
        errors.append(f"missing risk IDs: {', '.join(missing)}")
    return RiskRegisterValidationResult(not errors, len(seen), dict(sorted(statuses.items())), errors)


def is_placeholder_owner(owner: str) -> bool:
    normalized = owner.strip().lower()
    return not normalized or normalized.endswith(" owner") or normalized in {"tbd", "todo", "unassigned", "team"}


def parse_markdown_table(path: Path) -> List[Dict[str, str]]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip().startswith("|")]
    if len(lines) < 3:
        return []
    headers = [cell.strip() for cell in lines[0].strip("|").split("|")]
    rows: List[Dict[str, str]] = []
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != len(headers):
            continue
        rows.append(dict(zip(headers, cells)))
    return rows
