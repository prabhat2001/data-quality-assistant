"""Turn a short sentence into a check when the language model is unavailable."""

from __future__ import annotations

import re

from app.services.catalog import RuleDraft
from app.services.profiler import ColumnProfile

EMAIL_REGEX = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def _match_column(text: str, columns: list[ColumnProfile]) -> ColumnProfile | None:
    lower = text.lower()
    by_name = {column.name.lower(): column for column in columns}
    for column in sorted(columns, key=lambda item: len(item.name), reverse=True):
        pattern = r"\b" + re.escape(column.name.lower()).replace("_", r"[ _]") + r"\b"
        if re.search(pattern, lower):
            return column
    for word in re.findall(r"[a-z][a-z0-9_]*", lower):
        if word in by_name:
            return by_name[word]
        if word.endswith("s") and word[:-1] in by_name:
            return by_name[word[:-1]]
        if word.endswith("es") and word[:-2] in by_name:
            return by_name[word[:-2]]
    if re.search(r"\be-?mail\b", lower):
        for column in columns:
            if "email" in column.name.lower():
                return column
    return None


def _values_from_phrase(phrase: str) -> list[str]:
    parts = re.split(r",|\bor\b", phrase)
    values = []
    for part in parts:
        cleaned = part.strip(" .\"'`")
        cleaned = re.sub(r"^(and|or)\s+", "", cleaned, flags=re.I)
        if cleaned and cleaned.lower() not in {"and", "or"}:
            values.append(cleaned)
    return values


def translate_locally(text: str, columns: list[ColumnProfile]) -> list[RuleDraft]:
    lower = text.lower().strip()
    column = _match_column(text, columns)
    names = ", ".join(item.name for item in columns)

    between = re.search(
        r"between\s+(-?\d+(?:\.\d+)?)\s+and\s+(-?\d+(?:\.\d+)?)",
        lower,
    )
    if between and column is not None:
        minimum = float(between.group(1))
        maximum = float(between.group(2))
        if minimum.is_integer():
            minimum = int(minimum)
        if maximum.is_integer():
            maximum = int(maximum)
        return [
            RuleDraft(
                title=f"{column.name} stays in range",
                plain_language=text.strip(),
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": column.name, "min_value": minimum, "max_value": maximum},
                severity="warning",
            )
        ]

    value_match = re.search(r"\b(?:one of|only be|must be|should be)\b\s+(.+)$", text, re.I)
    if value_match and column is not None and ("," in value_match.group(1) or " or " in value_match.group(1).lower()):
        values = _values_from_phrase(value_match.group(1))
        if len(values) >= 2:
            return [
                RuleDraft(
                    title=f"{column.name} uses an allowed value",
                    plain_language=text.strip(),
                    expectation_type="expect_column_values_to_be_in_set",
                    kwargs={"column": column.name, "value_set": values},
                    severity="warning",
                )
            ]

    if column is None and re.search(r"\b(row count|at least|not empty|have rows|has rows)\b", lower):
        numbers = re.findall(r"\d+", lower)
        minimum = int(numbers[0]) if numbers else 1
        return [
            RuleDraft(
                title="Table has enough rows",
                plain_language=text.strip(),
                expectation_type="expect_table_row_count_to_be_between",
                kwargs={"min_value": minimum},
                severity="warning",
            )
        ]

    if column is None:
        raise ValueError(
            f"Name a column from this table so the check can be saved. Columns: {names}."
        )

    if re.search(r"\b(unique|no duplicates|duplicate)\b", lower):
        return [
            RuleDraft(
                title=f"{column.name} is unique",
                plain_language=text.strip(),
                expectation_type="expect_column_values_to_be_unique",
                kwargs={"column": column.name},
                severity="critical",
            )
        ]

    wants_email = "email" in column.name.lower() or re.search(r"\be-?mail\b", lower)
    if wants_email and re.search(r"\b(format|valid|look|pattern|@)\b", lower):
        return [
            RuleDraft(
                title="Email has a valid shape",
                plain_language=text.strip(),
                expectation_type="expect_column_values_to_match_regex",
                kwargs={"column": column.name, "regex": EMAIL_REGEX},
                severity="critical",
            )
        ]

    if re.search(r"\b(required|not null|empty|missing|present|filled|always have|must have)\b", lower):
        return [
            RuleDraft(
                title=f"{column.name} is required",
                plain_language=text.strip(),
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": column.name},
                severity="critical",
            )
        ]

    raise ValueError(
        "Try a sentence like \"email is required\", \"amount should be between 0 and 1000\", "
        "or \"status should be one of paid, pending, shipped\"."
    )
