"""Runtime validators for documented data contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping


def load_answer_contract_schema(path: Path = Path("docs/ANSWER_CONTRACT.schema.json")) -> Mapping[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_answer_contract(payload: Mapping[str, Any], schema: Mapping[str, Any] | None = None) -> List[str]:
    """Validate an answer payload against the documented answer contract.

    This intentionally implements only the JSON Schema features used by
    `docs/ANSWER_CONTRACT.schema.json`, keeping runtime validation
    dependency-free for the MVP.
    """

    schema = schema or load_answer_contract_schema()
    errors: List[str] = []
    validate_object(payload, schema, "$", errors)
    validate_answer_invariants(payload, errors)
    return errors


def validate_answer_invariants(payload: Mapping[str, Any], errors: List[str]) -> None:
    if not isinstance(payload, dict):
        return
    if payload.get("insufficient_evidence") is True and payload.get("confidence_label") != "insufficient":
        errors.append("$.confidence_label: must be insufficient when insufficient_evidence is true")
    if payload.get("insufficient_evidence") is False and payload.get("confidence_label") == "insufficient":
        errors.append("$.confidence_label: cannot be insufficient when insufficient_evidence is false")
    if payload.get("insufficient_evidence") is False:
        if payload.get("citations") == []:
            errors.append("$.citations: supported answers must include at least one citation")
        if payload.get("used_unit_ids") == []:
            errors.append("$.used_unit_ids: supported answers must include at least one used unit")
        if payload.get("used_doc_ids") == []:
            errors.append("$.used_doc_ids: supported answers must include at least one used document")
    used_unit_ids = payload.get("used_unit_ids")
    used_doc_ids = payload.get("used_doc_ids")
    citations = payload.get("citations")
    if isinstance(used_unit_ids, list) and isinstance(citations, list):
        used = {item for item in used_unit_ids if isinstance(item, str)}
        for index, citation in enumerate(citations):
            if isinstance(citation, dict) and isinstance(citation.get("unit_id"), str) and citation["unit_id"] not in used:
                errors.append(f"$.citations[{index}].unit_id: cited unit is not present in used_unit_ids")
    if isinstance(used_doc_ids, list) and isinstance(citations, list):
        used_docs = {item for item in used_doc_ids if isinstance(item, str)}
        for index, citation in enumerate(citations):
            if isinstance(citation, dict) and isinstance(citation.get("doc_id"), str) and citation["doc_id"] not in used_docs:
                errors.append(f"$.citations[{index}].doc_id: cited document is not present in used_doc_ids")


def validate_object(payload: Any, schema: Mapping[str, Any], path: str, errors: List[str]) -> None:
    if schema.get("type") == "object":
        if not isinstance(payload, dict):
            errors.append(f"{path}: expected object")
            return
        required = schema.get("required") or []
        for key in required:
            if key not in payload:
                errors.append(f"{path}: missing required field {key}")
        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            for key in payload:
                if key not in properties:
                    errors.append(f"{path}: unexpected field {key}")
        for key, value in payload.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                validate_value(value, child_schema, f"{path}.{key}", errors)
        return
    validate_value(payload, schema, path, errors)


def validate_value(value: Any, schema: Mapping[str, Any], path: str, errors: List[str]) -> None:
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} not in enum")
    expected_type = schema.get("type")
    if expected_type == "string" and not isinstance(value, str):
        errors.append(f"{path}: expected string")
    elif expected_type == "boolean" and not isinstance(value, bool):
        errors.append(f"{path}: expected boolean")
    elif expected_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{path}: expected integer")
        elif "minimum" in schema and value < int(schema["minimum"]):
            errors.append(f"{path}: expected >= {schema['minimum']}")
    elif expected_type == "array":
        if not isinstance(value, list):
            errors.append(f"{path}: expected array")
            return
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                validate_object(item, item_schema, f"{path}[{index}]", errors)
    elif expected_type == "object":
        validate_object(value, schema, path, errors)
