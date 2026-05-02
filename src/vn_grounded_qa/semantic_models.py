"""Pydantic contracts for bounded LLM-assisted semantic judgments."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryPlan(StrictModel):
    rewritten_queries: list[str] = Field(default_factory=list, max_length=3)
    intent: str = Field(max_length=160)
    entities: list[str] = Field(default_factory=list, max_length=8)
    doc_type_filter: Optional[str] = Field(default=None, max_length=80)
    needs_version_resolution: bool
    needs_cross_document_reasoning: bool
    reason: str = Field(max_length=600)

    @field_validator("rewritten_queries", "entities")
    @classmethod
    def non_empty_items(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class EvidenceJudgment(StrictModel):
    unit_id: str = Field(min_length=1, max_length=160)
    role: Literal["supports", "contradicts", "background", "irrelevant"]
    supported_claim: str = Field(default="", max_length=700)
    reason: str = Field(max_length=600)
    confidence: Literal["high", "medium", "low"]


class EvidenceDecision(StrictModel):
    answerability: Literal["answerable", "insufficient", "contradictory", "unclear_version"]
    judgments: list[EvidenceJudgment] = Field(default_factory=list, max_length=12)
    required_unit_ids: list[str] = Field(default_factory=list, max_length=5)
    reason: str = Field(max_length=800)

    @field_validator("required_unit_ids")
    @classmethod
    def required_ids_are_clean(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class AnswerDraft(StrictModel):
    answer: str = Field(max_length=4000)
    used_unit_ids: list[str] = Field(default_factory=list, max_length=5)
    confidence_label: Literal["high", "medium", "low", "insufficient"]

    @field_validator("used_unit_ids")
    @classmethod
    def used_ids_are_clean(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]

