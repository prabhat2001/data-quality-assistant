"""Run stored checks with an in-memory Great Expectations context."""

from __future__ import annotations

import os
from typing import Any

# Keep GX from writing a project folder or phoning home during a run.
os.environ.setdefault("GX_ANALYTICS_ENABLED", "false")

import great_expectations as gx
import great_expectations.expectations as gxe

from quality.services.catalog import ALLOWED_KWARGS
from quality.services.jsonutil import json_safe

EXPECTATION_CLASSES = {
    "expect_column_values_to_not_be_null": gxe.ExpectColumnValuesToNotBeNull,
    "expect_column_values_to_be_unique": gxe.ExpectColumnValuesToBeUnique,
    "expect_column_values_to_be_in_set": gxe.ExpectColumnValuesToBeInSet,
    "expect_column_values_to_be_between": gxe.ExpectColumnValuesToBeBetween,
    "expect_column_value_lengths_to_be_between": gxe.ExpectColumnValueLengthsToBeBetween,
    "expect_column_values_to_match_regex": gxe.ExpectColumnValuesToMatchRegex,
    "expect_table_row_count_to_be_between": gxe.ExpectTableRowCountToBeBetween,
    "expect_compound_columns_to_be_unique": gxe.ExpectCompoundColumnsToBeUnique,
}


def build_expectation(expectation_type: str, kwargs: dict[str, Any]):
    if expectation_type not in EXPECTATION_CLASSES:
        raise ValueError(f"Unsupported check type: {expectation_type}")
    allowed = ALLOWED_KWARGS[expectation_type]
    cleaned = {key: value for key, value in kwargs.items() if key in allowed}
    return EXPECTATION_CLASSES[expectation_type](**cleaned)


def _samples(result: dict[str, Any]) -> list[Any]:
    for key in ("partial_unexpected_list", "unexpected_list"):
        values = result.get(key)
        if hasattr(values, "tolist"):
            values = values.tolist()
        if isinstance(values, list) and values:
            return json_safe(values[:8])
    return []


def _trim_observed(result: dict[str, Any]) -> dict[str, Any]:
    observed = json_safe(result)
    if not isinstance(observed, dict):
        return {}
    for key in ("partial_unexpected_list", "unexpected_list", "partial_unexpected_counts"):
        if isinstance(observed.get(key), list):
            observed[key] = observed[key][:8]
    return observed


def _one_result(batch, rule) -> dict[str, Any]:
    base = {
        "rule_id": rule.id,
        "title": rule.title,
        "expectation_type": rule.expectation_type,
        "kwargs": rule.kwargs,
        "severity": rule.severity,
        "unexpected_count": None,
        "unexpected_percent": None,
        "sample_failures": [],
        "observed": {},
        "error_message": None,
    }
    try:
        expectation = build_expectation(rule.expectation_type, rule.kwargs or {})
        raw = batch.validate(expectation, result_format="SUMMARY")
        data = raw.to_json_dict()
    except Exception as exc:
        base["outcome"] = "error"
        base["error_message"] = str(exc)[:500]
        return base

    exception_info = data.get("exception_info") or {}
    if isinstance(exception_info, dict) and exception_info.get("raised_exception"):
        base["outcome"] = "error"
        base["error_message"] = str(exception_info.get("exception_message") or "Check failed to run")[:500]
        return base

    result = data.get("result") or {}
    success = bool(data.get("success"))
    if success:
        outcome = "passed"
    elif rule.severity == "warning":
        outcome = "warning"
    else:
        outcome = "failed"
    unexpected_count = result.get("unexpected_count")
    unexpected_percent = result.get("unexpected_percent")
    base.update(
        {
            "outcome": outcome,
            "unexpected_count": int(unexpected_count) if unexpected_count is not None else None,
            "unexpected_percent": float(unexpected_percent) if unexpected_percent is not None else None,
            "sample_failures": _samples(result),
            "observed": _trim_observed(result),
        }
    )
    return base


def run_rules(database_url: str, schema_name: str, table_name: str, rules: list) -> list[dict[str, Any]]:
    context = gx.get_context(mode="ephemeral")
    datasource = context.data_sources.add_postgres(
        name="warehouse",
        connection_string=database_url,
    )
    asset = datasource.add_table_asset(
        name="checked_table",
        table_name=table_name,
        schema_name=schema_name,
    )
    batch_definition = asset.add_batch_definition_whole_table(name="whole_table")
    batch = batch_definition.get_batch()
    return [_one_result(batch, rule) for rule in rules]
