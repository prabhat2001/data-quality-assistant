"""Read table shape and recommend checks from the data itself.

This is the development path used when no LLM key is configured, and it is
also the evidence the language model sees when a key is present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.catalog import RuleDraft, quote_ident, require_ident
from app.services.jsonutil import json_safe

NUMERIC_TYPES = {
    "smallint",
    "integer",
    "bigint",
    "decimal",
    "numeric",
    "real",
    "double precision",
    "money",
}
NON_NEGATIVE_HINTS = ("price", "amount", "cost", "quantity", "qty", "total", "revenue", "balance")
STATUS_HINTS = ("status", "category", "country", "type", "state", "segment", "currency")


@dataclass
class ColumnProfile:
    name: str
    data_type: str
    nullable: bool
    null_count: int
    null_percent: float
    distinct_count: int
    min_value: Any | None = None
    max_value: Any | None = None
    top_values: list[dict[str, Any]] | None = None

    @property
    def is_numeric(self) -> bool:
        return self.data_type in NUMERIC_TYPES

    @property
    def is_text(self) -> bool:
        return self.data_type in {"text", "character varying", "character"}

    def as_public(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "data_type": self.data_type,
            "nullable": self.nullable,
            "null_count": self.null_count,
            "null_percent": round(self.null_percent, 1),
            "distinct_count": self.distinct_count,
            "min_value": json_safe(self.min_value),
            "max_value": json_safe(self.max_value),
        }
        if self.top_values:
            payload["top_values"] = self.top_values
        return payload


@dataclass
class TableProfile:
    schema_name: str
    table_name: str
    row_count: int
    columns: list[ColumnProfile]
    sample_rows: list[dict[str, Any]]

    def column_names(self) -> set[str]:
        return {column.name for column in self.columns}

    def highlights(self) -> list[str]:
        if self.row_count == 0:
            return ["This table has no rows yet."]
        notes: list[str] = []
        for column in self.columns:
            if column.null_count:
                notes.append(
                    f"{column.null_count} of {self.row_count} values in {column.name} are empty."
                )
            if column.is_numeric and isinstance(column.min_value, (int, float)) and column.min_value < 0:
                notes.append(f"{column.name} goes down to {json_safe(column.min_value)}.")
        return notes[:6]

    def for_prompt(self) -> dict[str, Any]:
        return {
            "schema": self.schema_name,
            "table": self.table_name,
            "row_count": self.row_count,
            "columns": [column.as_public() for column in self.columns],
            "sample_rows": self.sample_rows[:5],
        }


def _table_exists(session: Session, schema_name: str, table_name: str) -> bool:
    row = session.execute(
        text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema_name AND table_name = :table_name
            """
        ),
        {"schema_name": schema_name, "table_name": table_name},
    ).first()
    return row is not None


def list_tables(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT n.nspname AS schema_name,
                   c.relname AS table_name,
                   GREATEST(c.reltuples, 0)::bigint AS estimate
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r'
              AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'dq')
            ORDER BY n.nspname, c.relname
            """
        )
    ).mappings()
    tables = []
    for row in rows:
        schema_name = row["schema_name"]
        table_name = row["table_name"]
        require_ident(schema_name)
        require_ident(table_name)
        estimate = int(row["estimate"] or 0)
        if estimate <= 0:
            qualified = f"{quote_ident(schema_name)}.{quote_ident(table_name)}"
            estimate = int(session.execute(text(f"SELECT COUNT(*) FROM {qualified}")).scalar() or 0)
        tables.append(
            {"schema_name": schema_name, "table_name": table_name, "row_count": estimate}
        )
    return tables


def profile_table(session: Session, schema_name: str, table_name: str) -> TableProfile:
    schema_name = require_ident(schema_name)
    table_name = require_ident(table_name)
    if not _table_exists(session, schema_name, table_name):
        raise LookupError(f"Table {schema_name}.{table_name} was not found")

    meta = session.execute(
        text(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = :schema_name AND table_name = :table_name
            ORDER BY ordinal_position
            """
        ),
        {"schema_name": schema_name, "table_name": table_name},
    ).mappings()
    column_meta = list(meta)
    if not column_meta:
        raise LookupError(f"Table {schema_name}.{table_name} has no columns")

    select_bits = ["COUNT(*) AS row_count"]
    for column in column_meta:
        name = require_ident(column["column_name"])
        quoted = quote_ident(name)
        select_bits.append(f'COUNT({quoted}) AS "{name}__present"')
        select_bits.append(f'COUNT(DISTINCT {quoted}) AS "{name}__distinct"')
        if column["data_type"] in NUMERIC_TYPES or str(column["data_type"]).startswith(
            ("date", "timestamp")
        ):
            select_bits.append(f'MIN({quoted}) AS "{name}__min"')
            select_bits.append(f'MAX({quoted}) AS "{name}__max"')

    qualified = f"{quote_ident(schema_name)}.{quote_ident(table_name)}"
    stats = session.execute(text(f"SELECT {', '.join(select_bits)} FROM {qualified}")).mappings().one()
    row_count = int(stats["row_count"] or 0)

    columns: list[ColumnProfile] = []
    for column in column_meta:
        name = column["column_name"]
        present = int(stats[f"{name}__present"] or 0)
        null_count = row_count - present
        profile = ColumnProfile(
            name=name,
            data_type=column["data_type"],
            nullable=column["is_nullable"] == "YES",
            null_count=null_count,
            null_percent=(100.0 * null_count / row_count) if row_count else 0.0,
            distinct_count=int(stats[f"{name}__distinct"] or 0),
            min_value=stats.get(f"{name}__min"),
            max_value=stats.get(f"{name}__max"),
        )
        if profile.is_text and 1 < profile.distinct_count <= 15 and row_count:
            quoted = quote_ident(name)
            grouped = session.execute(
                text(
                    f"""
                    SELECT {quoted} AS value, COUNT(*) AS count
                    FROM {qualified}
                    WHERE {quoted} IS NOT NULL
                    GROUP BY 1
                    ORDER BY count DESC, value
                    LIMIT 15
                    """
                )
            ).mappings()
            profile.top_values = [
                {"value": json_safe(item["value"]), "count": int(item["count"])} for item in grouped
            ]
        columns.append(profile)

    sample_result = session.execute(text(f"SELECT * FROM {qualified} LIMIT 8")).mappings()
    sample_rows = [{key: json_safe(value) for key, value in row.items()} for row in sample_result]
    return TableProfile(schema_name, table_name, row_count, columns, sample_rows)


def _draft(
    title: str,
    plain: str,
    expectation_type: str,
    kwargs: dict[str, Any],
    severity: str,
) -> RuleDraft:
    return RuleDraft(title, plain, expectation_type, kwargs, severity)


def _allowed_set(top_values: list[dict[str, Any]]) -> list[Any]:
    """Keep ordinary frequent values and leave out placeholder junk such as '??'."""
    if len(top_values) < 2:
        return []
    junk_words = {"unknown", "n/a", "na", "none", "null", "undefined", "misc??"}
    normal: list[Any] = []
    junk = False
    for item in top_values:
        text = str(item["value"]).strip()
        if "?" in text or text.lower() in junk_words:
            junk = True
        else:
            normal.append(item["value"])
    if junk and len(normal) >= 2:
        return normal
    return []


def _lookup_ids(session: Session, schema_name: str, referenced_table: str) -> list[Any] | None:
    if not _table_exists(session, schema_name, referenced_table):
        return None
    columns = session.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = :schema_name AND table_name = :table_name AND column_name = 'id'
            """
        ),
        {"schema_name": schema_name, "table_name": referenced_table},
    ).first()
    if columns is None:
        return None
    qualified = f"{quote_ident(schema_name)}.{quote_ident(referenced_table)}"
    rows = session.execute(text(f"SELECT id FROM {qualified} ORDER BY id LIMIT 201")).scalars()
    values = [json_safe(value) for value in rows]
    if not values or len(values) > 200:
        return None
    return values


def recommend_rules(session: Session, profile: TableProfile) -> list[RuleDraft]:
    drafts: list[RuleDraft] = []
    if profile.row_count == 0:
        return [
            _draft(
                "Table has rows",
                f"{profile.table_name} should contain data before it is used.",
                "expect_table_row_count_to_be_between",
                {"min_value": 1},
                "warning",
            )
        ]

    for column in profile.columns:
        name = column.name
        lower = name.lower()
        mostly_filled = column.null_percent <= 15

        if lower == "id" or lower.endswith("_id"):
            if mostly_filled:
                article = "an" if name[:1].lower() in "aeiou" else "a"
                drafts.append(
                    _draft(
                        f"{name} is always filled in",
                        f"Every row should have {article} {name}. Empty identifiers cannot be joined or traced.",
                        "expect_column_values_to_not_be_null",
                        {"column": name},
                        "critical",
                    )
                )
            if column.distinct_count == profile.row_count - column.null_count and column.distinct_count > 1:
                drafts.append(
                    _draft(
                        f"{name} has no duplicates",
                        f"Each {name} should appear once.",
                        "expect_column_values_to_be_unique",
                        {"column": name},
                        "critical",
                    )
                )

        if lower.endswith("_id") and lower != "id":
            referenced = lower[: -len("_id")]
            if not referenced.endswith("s"):
                referenced += "s"
            if IDENT_OK(referenced):
                ids = _lookup_ids(session, profile.schema_name, referenced)
                if ids:
                    drafts.append(
                        _draft(
                            f"{name} matches a {referenced[:-1]}",
                            f"Each {name} should point at a row in {referenced}.",
                            "expect_column_values_to_be_in_set",
                            {"column": name, "value_set": ids},
                            "critical",
                        )
                    )

        if lower in {"sku", "code"} or lower.endswith("_sku"):
            drafts.append(
                _draft(
                    f"{name} is unique",
                    f"Each {name} should identify one row. Duplicates make the catalog ambiguous.",
                    "expect_column_values_to_be_unique",
                    {"column": name},
                    "critical",
                )
            )

        if "email" in lower and column.is_text:
            drafts.append(
                _draft(
                    "Email is required",
                    "Every row should have an email address.",
                    "expect_column_values_to_not_be_null",
                    {"column": name},
                    "critical",
                )
            )
            drafts.append(
                _draft(
                    "Email looks like an email",
                    "Email addresses should contain a name, an @ sign, and a domain.",
                    "expect_column_values_to_match_regex",
                    {"column": name, "regex": r"^[^@\s]+@[^@\s]+\.[^@\s]+$"},
                    "critical",
                )
            )
            non_null = profile.row_count - column.null_count
            if non_null and column.distinct_count < non_null:
                drafts.append(
                    _draft(
                        "Email is unique",
                        "The same email address should not be used on more than one row.",
                        "expect_column_values_to_be_unique",
                        {"column": name},
                        "critical",
                    )
                )

        if lower in {"age"} or lower.endswith("_age"):
            drafts.append(
                _draft(
                    "Age is a realistic number",
                    "Age should be between 0 and 120.",
                    "expect_column_values_to_be_between",
                    {"column": name, "min_value": 0, "max_value": 120},
                    "warning",
                )
            )

        if any(hint in lower for hint in NON_NEGATIVE_HINTS) and column.is_numeric:
            observed_max = column.max_value if isinstance(column.max_value, (int, float)) else None
            kwargs: dict[str, Any] = {"column": name, "min_value": 0}
            if isinstance(observed_max, (int, float)) and observed_max >= 0:
                kwargs["max_value"] = observed_max
            drafts.append(
                _draft(
                    f"{name} is zero or greater",
                    f"{name.replace('_', ' ')} should not be negative.",
                    "expect_column_values_to_be_between",
                    kwargs,
                    "critical",
                )
            )
            if mostly_filled and column.null_count:
                drafts.append(
                    _draft(
                        f"{name} is filled in",
                        f"{name.replace('_', ' ')} should be present on every row.",
                        "expect_column_values_to_not_be_null",
                        {"column": name},
                        "critical",
                    )
                )

        if column.top_values and any(hint in lower for hint in STATUS_HINTS):
            allowed = _allowed_set(column.top_values)
            if allowed:
                shown = ", ".join(str(value) for value in allowed)
                drafts.append(
                    _draft(
                        f"{name} uses a known value",
                        f"{name.replace('_', ' ')} should be one of: {shown}.",
                        "expect_column_values_to_be_in_set",
                        {"column": name, "value_set": allowed},
                        "warning",
                    )
                )
            if mostly_filled and column.null_count:
                drafts.append(
                    _draft(
                        f"{name} is filled in",
                        f"{name.replace('_', ' ')} should not be left empty.",
                        "expect_column_values_to_not_be_null",
                        {"column": name},
                        "warning",
                    )
                )

        if column.is_text and "email" not in lower and mostly_filled and column.null_count and lower in {
            "name",
            "full_name",
            "title",
        }:
            drafts.append(
                _draft(
                    f"{name} is filled in",
                    f"{name.replace('_', ' ')} should not be left empty.",
                    "expect_column_values_to_not_be_null",
                    {"column": name},
                    "warning",
                )
            )

        if (lower.endswith("_at") or lower.endswith("_on") or "date" in lower) and mostly_filled and column.null_count:
            drafts.append(
                _draft(
                    f"{name} is filled in",
                    f"{name.replace('_', ' ')} should be present so the row can be placed in time.",
                    "expect_column_values_to_not_be_null",
                    {"column": name},
                    "warning",
                )
            )

    drafts.append(
        _draft(
            "Table is not empty",
            f"{profile.table_name} should contain at least one row.",
            "expect_table_row_count_to_be_between",
            {"min_value": 1},
            "warning",
        )
    )
    return _dedupe(drafts)[:12]


def IDENT_OK(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name))


def _dedupe(drafts: list[RuleDraft]) -> list[RuleDraft]:
    seen: set[str] = set()
    unique: list[RuleDraft] = []
    for draft in drafts:
        key = f"{draft.expectation_type}|{sorted(draft.kwargs.items())}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(draft)
    return unique

