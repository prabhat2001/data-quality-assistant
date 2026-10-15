"""API request and response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ColumnOut(BaseModel):
    name: str
    data_type: str
    nullable: bool
    null_count: int
    null_percent: float
    distinct_count: int
    min_value: Any | None = None
    max_value: Any | None = None


class TableSummary(BaseModel):
    schema_name: str
    table_name: str
    row_count: int


class TableDetail(TableSummary):
    columns: list[ColumnOut]
    sample_rows: list[dict[str, Any]]
    highlights: list[str]


class RuleOut(BaseModel):
    id: str
    schema_name: str
    table_name: str
    title: str
    plain_language: str
    expectation_type: str
    kwargs: dict[str, Any]
    severity: str
    enabled: bool
    generator: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RuleUpdate(BaseModel):
    title: str | None = None
    plain_language: str | None = None
    severity: str | None = None
    enabled: bool | None = None
    kwargs: dict[str, Any] | None = None


class NaturalLanguageIn(BaseModel):
    schema_name: str
    table_name: str
    text: str = Field(min_length=3, max_length=1000)


class NaturalLanguageOut(BaseModel):
    rules: list[RuleOut]
    translated_by: str
    note: str


class SuggestionOut(BaseModel):
    generator: str
    provider: str | None = None
    model: str | None = None
    note: str
    created: list[RuleOut]


class RunResultOut(BaseModel):
    id: str
    rule_id: str | None
    title: str
    expectation_type: str
    kwargs: dict[str, Any]
    severity: str
    outcome: str
    unexpected_count: int | None
    unexpected_percent: float | None
    sample_failures: list[Any]
    observed: dict[str, Any]
    error_message: str | None

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: str
    schema_name: str
    table_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    passed_count: int
    failed_count: int
    warning_count: int
    error_count: int
    error_message: str | None
    results: list[RunResultOut] = []

    model_config = {"from_attributes": True}


class RunRequest(BaseModel):
    schema_name: str
    table_name: str
    rule_ids: list[str] | None = None


class HealthOut(BaseModel):
    status: str
    database: str
    llm_provider: str
    llm_model: str
    llm_configured: bool
    suggestion_mode: str
    message: str
