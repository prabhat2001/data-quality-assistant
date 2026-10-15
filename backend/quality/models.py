"""Checks and saved runs live in the dq schema, separate from the data being checked."""

from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


def new_id() -> str:
    return str(uuid.uuid4())


class JsonValueField(models.JSONField):
    """Read both raw JSON text and values psycopg has already decoded."""

    def from_db_value(self, value, expression, connection):
        if value is None or isinstance(value, (dict, list)):
            return value
        return super().from_db_value(value, expression, connection)

    def deconstruct(self):
        name, _path, args, kwargs = super().deconstruct()
        return name, "django.db.models.JSONField", args, kwargs


class Rule(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id)
    schema_name = models.CharField(max_length=128)
    table_name = models.CharField(max_length=128)
    title = models.CharField(max_length=200)
    plain_language = models.TextField()
    expectation_type = models.CharField(max_length=128)
    kwargs = JsonValueField(default=dict)
    severity = models.CharField(max_length=16, default="warning")
    enabled = models.BooleanField(default=True)
    generator = models.CharField(max_length=32, default="profiler")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = '"dq"."rules"'
        indexes = [models.Index(fields=["schema_name", "table_name"], name="ix_rules_table")]


class Run(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id)
    schema_name = models.CharField(max_length=128)
    table_name = models.CharField(max_length=128)
    status = models.CharField(max_length=16, default="running")
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    passed_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    warning_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        db_table = '"dq"."runs"'
        indexes = [
            models.Index(
                fields=["schema_name", "table_name", "started_at"],
                name="ix_runs_table",
            )
        ]


class RunResult(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id)
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="results", db_column="run_id")
    rule = models.ForeignKey(
        Rule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results",
        db_column="rule_id",
    )
    title = models.CharField(max_length=200)
    expectation_type = models.CharField(max_length=128)
    kwargs = JsonValueField(default=dict)
    severity = models.CharField(max_length=16)
    outcome = models.CharField(max_length=16)
    unexpected_count = models.IntegerField(null=True, blank=True)
    unexpected_percent = models.FloatField(null=True, blank=True)
    sample_failures = JsonValueField(default=list)
    observed = JsonValueField(default=dict)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        db_table = '"dq"."run_results"'
