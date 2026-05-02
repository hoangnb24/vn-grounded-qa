from pathlib import Path

from vn_grounded_qa.cli import main
from vn_grounded_qa.risks import is_placeholder_owner, validate_risk_register


def test_risk_register_validates_repo_file() -> None:
    result = validate_risk_register(Path("docs/RISK_REGISTER.md"))
    assert result.ok is True
    assert result.risk_count == 8


def test_risk_cli_validate() -> None:
    assert main(["risks", "validate"]) == 0


def test_strict_risk_owner_validation_accepts_repo_deployment_owner() -> None:
    result = validate_risk_register(Path("docs/RISK_REGISTER.md"), strict_owners=True)
    assert result.ok is True


def test_strict_risk_owner_validation_rejects_role_placeholders(tmp_path: Path) -> None:
    risk_register = tmp_path / "RISK_REGISTER.md"
    risk_register.write_text(
        """# Risk Register

| ID | Risk | Detector | Mitigation | Owner | Status |
|---|---|---|---|---|---|
| CR-1 | Ingestion fidelity too low | M1 parser scorecards | Better parser routing | Governance owner | open |
""",
        encoding="utf-8",
    )
    result = validate_risk_register(risk_register, strict_owners=True)
    assert result.ok is False
    assert any("placeholder role owner" in error for error in result.errors)


def test_risk_cli_strict_owners_passes_after_deployment_owners_are_set() -> None:
    assert main(["risks", "validate", "--strict-owners"]) == 0


def test_placeholder_owner_detection() -> None:
    assert is_placeholder_owner("Governance owner") is True
    assert is_placeholder_owner("TBD") is True
    assert is_placeholder_owner("Nguyen Van A") is False
