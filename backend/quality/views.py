"""JSON API. Paths and payloads match the previous FastAPI service."""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from quality.llm_config import current_llm_settings
from quality.models import Rule, Run
from quality.services.rules import execute, from_language, suggest, update_rule

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def json_response(payload: Any, status: int = 200) -> JsonResponse:
    return JsonResponse(payload, status=status, safe=False, encoder=DjangoJSONEncoder)


def not_found(request, exception):
    return json_response({"detail": "Not found"}, status=404)


def server_error(request):
    return json_response({"detail": "Internal Server Error"}, status=500)


def root(request):
    return json_response(
        {
            "service": "data-quality-assistant",
            "ui": "http://localhost:3000",
            "docs": "/api/health",
        }
    )


def _rule_payload(rule: Rule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "schema_name": rule.schema_name,
        "table_name": rule.table_name,
        "title": rule.title,
        "plain_language": rule.plain_language,
        "expectation_type": rule.expectation_type,
        "kwargs": rule.kwargs or {},
        "severity": rule.severity,
        "enabled": rule.enabled,
        "generator": rule.generator,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def _result_payload(result) -> dict[str, Any]:
    return {
        "id": result.id,
        "rule_id": result.rule_id,
        "title": result.title,
        "expectation_type": result.expectation_type,
        "kwargs": result.kwargs or {},
        "severity": result.severity,
        "outcome": result.outcome,
        "unexpected_count": result.unexpected_count,
        "unexpected_percent": result.unexpected_percent,
        "sample_failures": result.sample_failures or [],
        "observed": result.observed or {},
        "error_message": result.error_message,
    }


def _run_payload(run: Run) -> dict[str, Any]:
    results = list(run.results.all())
    return {
        "id": run.id,
        "schema_name": run.schema_name,
        "table_name": run.table_name,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "passed_count": run.passed_count,
        "failed_count": run.failed_count,
        "warning_count": run.warning_count,
        "error_count": run.error_count,
        "error_message": run.error_message,
        "results": [_result_payload(result) for result in results],
    }


def _read_json(request) -> dict[str, Any]:
    if not request.body:
        return {}
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError as exc:
        raise ApiError(400, "Request body must be JSON") from exc
    if not isinstance(payload, dict):
        raise ApiError(400, "Request body must be a JSON object")
    return payload


def _call(handler, request, *args, **kwargs):
    try:
        return handler(request, *args, **kwargs)
    except ApiError as exc:
        return json_response({"detail": exc.detail}, status=exc.status)
    except LookupError as exc:
        return json_response({"detail": str(exc)}, status=404)
    except ValueError as exc:
        return json_response({"detail": str(exc)}, status=400)
    except RuntimeError as exc:
        return json_response({"detail": str(exc)}, status=502)
    except Exception:
        logger.exception("API request failed")
        return json_response({"detail": "Internal Server Error"}, status=500)


def endpoint(handler):
    @csrf_exempt
    def view(request, *args, **kwargs):
        return _call(handler, request, *args, **kwargs)

    return view


@endpoint
def health(request):
    llm = current_llm_settings()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        database = "ok"
        status = "ok"
    except Exception:
        database = "unavailable"
        status = "degraded"
    provider = llm.llm_provider.strip().lower()
    if llm.llm_configured():
        message = f"Using {provider} ({llm.llm_model()})."
        mode = "llm"
    else:
        message = (
            "No API key is configured. Suggestions use the built-in profiler. "
            "Set OPENAI_API_KEY and LLM_PROVIDER=openai in backend/.env."
        )
        mode = "profiler"
    return json_response(
        {
            "status": status,
            "database": database,
            "llm_provider": provider,
            "llm_model": llm.llm_model(),
            "llm_configured": llm.llm_configured(),
            "suggestion_mode": mode,
            "message": message,
        }
    )


@endpoint
def tables(request):
    from quality.services.profiler import list_tables

    return json_response(list_tables())


@endpoint
def table_detail(request, schema_name: str, table_name: str):
    from quality.services.profiler import profile_table

    profile = profile_table(schema_name, table_name)
    return json_response(
        {
            "schema_name": profile.schema_name,
            "table_name": profile.table_name,
            "row_count": profile.row_count,
            "columns": [column.as_public() for column in profile.columns],
            "sample_rows": profile.sample_rows,
            "highlights": profile.highlights(),
        }
    )


@endpoint
def rules(request):
    schema_name = request.GET.get("schema_name")
    table_name = request.GET.get("table_name")
    if not schema_name or not table_name:
        raise ApiError(400, "schema_name and table_name are required")
    rows = Rule.objects.filter(schema_name=schema_name, table_name=table_name).order_by("created_at")
    return json_response([_rule_payload(rule) for rule in rows])


@endpoint
def suggestions(request, schema_name: str, table_name: str):
    if request.method != "POST":
        raise ApiError(405, "Method not allowed")
    payload = suggest(schema_name, table_name)
    payload["created"] = [_rule_payload(rule) for rule in payload["created"]]
    return json_response(payload)


@endpoint
def natural_language(request):
    if request.method != "POST":
        raise ApiError(405, "Method not allowed")
    body = _read_json(request)
    schema_name = body.get("schema_name")
    table_name = body.get("table_name")
    text = body.get("text")
    if not isinstance(schema_name, str) or not isinstance(table_name, str):
        raise ApiError(400, "schema_name and table_name are required")
    if not isinstance(text, str) or not 3 <= len(text) <= 1000:
        raise ApiError(400, "Describe the check in 3 to 1000 characters")
    payload = from_language(schema_name, table_name, text)
    payload["rules"] = [_rule_payload(rule) for rule in payload["rules"]]
    return json_response(payload)


@endpoint
def rule_detail(request, rule_id: str):
    rule = Rule.objects.filter(id=rule_id).first()
    if rule is None:
        raise ApiError(404, "Check not found")
    if request.method == "DELETE":
        rule.delete()
        return HttpResponse(status=204)
    if request.method == "PATCH":
        body = _read_json(request)
        allowed = {"title", "plain_language", "severity", "enabled", "kwargs"}
        changes = {key: body[key] for key in allowed if key in body}
        updated = update_rule(rule, changes)
        return json_response(_rule_payload(updated))
    raise ApiError(405, "Method not allowed")


@endpoint
def runs(request):
    if request.method == "POST":
        body = _read_json(request)
        schema_name = body.get("schema_name")
        table_name = body.get("table_name")
        rule_ids = body.get("rule_ids")
        if not isinstance(schema_name, str) or not isinstance(table_name, str):
            raise ApiError(400, "schema_name and table_name are required")
        if rule_ids is not None and not isinstance(rule_ids, list):
            raise ApiError(400, "rule_ids must be a list")
        run = execute(schema_name, table_name, settings.DATABASE_URL, rule_ids)
        return json_response(_run_payload(run))
    schema_name = request.GET.get("schema_name")
    table_name = request.GET.get("table_name")
    if not schema_name or not table_name:
        raise ApiError(400, "schema_name and table_name are required")
    rows = (
        Run.objects.filter(schema_name=schema_name, table_name=table_name)
        .prefetch_related("results")
        .order_by("-started_at")[:8]
    )
    return json_response([_run_payload(run) for run in rows])


@endpoint
def latest_run(request):
    schema_name = request.GET.get("schema_name")
    table_name = request.GET.get("table_name")
    if not schema_name or not table_name:
        raise ApiError(400, "schema_name and table_name are required")
    run = (
        Run.objects.filter(schema_name=schema_name, table_name=table_name, status="completed")
        .prefetch_related("results")
        .order_by("-started_at")
        .first()
    )
    if run is None:
        raise ApiError(404, "No saved results for this table yet")
    return json_response(_run_payload(run))


@endpoint
def run_detail(request, run_id: str):
    run = Run.objects.filter(id=run_id).prefetch_related("results").first()
    if run is None:
        raise ApiError(404, "Run not found")
    return json_response(_run_payload(run))
