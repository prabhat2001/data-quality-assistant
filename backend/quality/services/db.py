"""Small helpers for the raw SQL that profiles warehouse tables."""

from __future__ import annotations

from typing import Any

from django.db import connection


def query_all(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        if params is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, params)
        if cursor.description is None:
            return []
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def query_one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rows = query_all(sql, params)
    return rows[0] if rows else None


def query_scalar(sql: str, params: dict[str, Any] | None = None) -> Any:
    with connection.cursor() as cursor:
        if params is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, params)
        row = cursor.fetchone()
        return None if row is None else row[0]
