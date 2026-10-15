"""Allowed Great Expectations checks and how plain-language drafts become kwargs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

COLUMN_EXPECTATIONS = {
    "expect_column_values_to_not_be_null",
    "expect_column_values_to_be_unique",
    "expect_column_values_to_be_in_set",
    "expect_column_values_to_be_between",
    "expect_column_value_lengths_to_be_between",
    "expect_column_values_to_match_regex",
}

ALLOWED_KWARGS = {
    "expect_column_values_to_not_be_null": {"column"},
    "expect_column_values_to_be_unique": {"column"},
    "expect_column_values_to_be_in_set": {"column", "value_set"},
    "expect_column_values_to_be_between": {"column", "min_value", "max_value"},
    "expect_column_value_lengths_to_be_between": {"column", "min_value", "max_value"},
    "expect_column_values_to_match_regex": {"column", "regex"},
    "expect_table_row_count_to_be_between": {"min_value", "max_value"},
    "expect_compound_columns_to_be_unique": {"column_list"},
}

REQUIRED_KWARGS = {
    "expect_column_values_to_not_be_null": {"column"},
    "expect_column_values_to_be_unique": {"column"},
    "expect_column_values_to_be_in_set": {"column", "value_set"},
    "expect_column_values_to_be_between": {"column"},
    "expect_column_value_lengths_to_be_between": {"column"},
    "expect_column_values_to_match_regex": {"column", "regex"},
    "expect_table_row_count_to_be_between": set(),
    "expect_compound_columns_to_be_unique": {"column_list"},
}

PLAIN_LABELS = {
    "expect_column_values_to_not_be_null": "Required value",
    "expect_column_values_to_be_unique": "Unique value",
    "expect_column_values_to_be_in_set": "Allowed values",
    "expect_column_values_to_be_between": "Numeric range",
    "expect_column_value_lengths_to_be_between": "Text length",
    "expect_column_values_to_match_regex": "Pattern",
    "expect_table_row_count_to_be_between": "Row count",
    "expect_compound_columns_to_be_unique": "Unique combination",
}


@dataclass
class RuleDraft:
    title: str
    plain_language: str
    expectation_type: str
    kwargs: dict[str, Any]
    severity: str


def require_ident(name: str) -> str:
    if not isinstance(name, str) or not IDENT.fullmatch(name):
        raise ValueError(f"Invalid name: {name!r}")
    return name


def quote_ident(name: str) -> str:
    return f'"{require_ident(name)}"'


def _number(value: Any) -> int | float:
    if isinstance(value, bool) or value is None:
        raise ValueError("Expected a number")
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"-?\d+", text):
            return int(text)
        return float(text)
    raise ValueError("Expected a number")


def coerce_rule(raw: dict[str, Any], columns: set[str]) -> RuleDraft:
    if not isinstance(raw, dict):
        raise ValueError("Each check must be an object")
    expectation_type = str(raw.get("expectation_type") or "").strip()
    if expectation_type not in ALLOWED_KWARGS:
        raise ValueError(f"Unsupported check type: {expectation_type}")

    incoming = raw.get("kwargs") or {}
    if not isinstance(incoming, dict):
        raise ValueError("kwargs must be an object")
    kwargs: dict[str, Any] = {}
    for key, value in incoming.items():
        if key in ALLOWED_KWARGS[expectation_type] and value is not None:
            kwargs[key] = value

    missing = REQUIRED_KWARGS[expectation_type] - set(kwargs)
    if expectation_type in {
        "expect_column_values_to_be_between",
        "expect_column_value_lengths_to_be_between",
        "expect_table_row_count_to_be_between",
    }:
        if "min_value" not in kwargs and "max_value" not in kwargs:
            raise ValueError("A range needs a minimum or a maximum")
    if missing:
        raise ValueError(f"Missing {', '.join(sorted(missing))}")

    if "column" in kwargs:
        column = str(kwargs["column"]).strip()
        if column not in columns:
            raise ValueError(f"Unknown column: {column}")
        kwargs["column"] = column

    if "column_list" in kwargs:
        values = kwargs["column_list"]
        if isinstance(values, str):
            values = [part.strip() for part in values.split(",") if part.strip()]
        if not isinstance(values, list) or len(values) < 2:
            raise ValueError("A combination check needs at least two columns")
        cleaned = []
        for item in values:
            name = str(item).strip()
            if name not in columns:
                raise ValueError(f"Unknown column: {name}")
            cleaned.append(name)
        kwargs["column_list"] = cleaned

    if "value_set" in kwargs:
        values = kwargs["value_set"]
        if isinstance(values, str):
            values = [part.strip() for part in values.split(",") if part.strip()]
        if not isinstance(values, list) or not values:
            raise ValueError("Allowed values cannot be empty")
        cleaned_values = []
        for item in values:
            if isinstance(item, bool) or item is None:
                raise ValueError("Allowed values must be text or numbers")
            if isinstance(item, (int, float)):
                cleaned_values.append(item)
            else:
                text = str(item).strip()
                if text:
                    cleaned_values.append(text)
        if not cleaned_values:
            raise ValueError("Allowed values cannot be empty")
        kwargs["value_set"] = cleaned_values

    for key in ("min_value", "max_value"):
        if key in kwargs:
            kwargs[key] = _number(kwargs[key])
    if (
        "min_value" in kwargs
        and "max_value" in kwargs
        and kwargs["min_value"] > kwargs["max_value"]
    ):
        raise ValueError("Minimum is greater than maximum")

    if "regex" in kwargs:
        pattern = str(kwargs["regex"])
        re.compile(pattern)
        kwargs["regex"] = pattern

    severity = str(raw.get("severity") or "warning").strip().lower()
    if severity not in {"critical", "warning"}:
        severity = "warning"

    title = str(raw.get("title") or PLAIN_LABELS[expectation_type]).strip()
    plain = str(raw.get("plain_language") or title).strip()
    if not title or not plain:
        raise ValueError("A check needs a title and a description")

    return RuleDraft(
        title=title[:200],
        plain_language=plain[:800],
        expectation_type=expectation_type,
        kwargs=kwargs,
        severity=severity,
    )


def signature(expectation_type: str, kwargs: dict[str, Any]) -> str:
    normalized = dict(kwargs)
    if isinstance(normalized.get("value_set"), list):
        normalized["value_set"] = sorted(normalized["value_set"], key=lambda item: str(item))
    return expectation_type + "|" + repr(sorted(normalized.items()))
