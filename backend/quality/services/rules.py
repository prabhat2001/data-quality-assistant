"""Save checks and execute them."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from quality.llm_config import LlmSettings, current_llm_settings
from quality.models import Rule, Run, RunResult, new_id
from quality.services.catalog import RuleDraft, coerce_rule, signature
from quality.services.gx_engine import run_rules
from quality.services.llm import LlmError, suggest_with_llm, translate_with_llm
from quality.services.nl import translate_locally
from quality.services.profiler import TableProfile, profile_table, recommend_rules


def _store(profile: TableProfile, draft: RuleDraft, generator: str) -> Rule:
    columns = profile.column_names()
    checked = coerce_rule(
        {
            "title": draft.title,
            "plain_language": draft.plain_language,
            "expectation_type": draft.expectation_type,
            "kwargs": draft.kwargs,
            "severity": draft.severity,
        },
        columns,
    )
    now = timezone.now()
    return Rule.objects.create(
        id=new_id(),
        schema_name=profile.schema_name,
        table_name=profile.table_name,
        title=checked.title,
        plain_language=checked.plain_language,
        expectation_type=checked.expectation_type,
        kwargs=checked.kwargs,
        severity=checked.severity,
        enabled=True,
        generator=generator,
        created_at=now,
        updated_at=now,
    )


def _existing_signatures(schema_name: str, table_name: str) -> set[str]:
    rows = Rule.objects.filter(schema_name=schema_name, table_name=table_name)
    return {signature(row.expectation_type, row.kwargs or {}) for row in rows}


def suggest(schema_name: str, table_name: str, settings: LlmSettings | None = None):
    settings = settings or current_llm_settings()
    profile = profile_table(schema_name, table_name)
    generator = "profiler"
    note = (
        "No API key is set, so these checks come from the table profile. "
        "Add OPENAI_API_KEY in backend/.env to use the OpenAI model."
    )
    provider = None
    model = None
    drafts: list[RuleDraft]
    if settings.llm_configured():
        provider = settings.llm_provider.strip().lower()
        model = settings.llm_model()
        try:
            drafts = suggest_with_llm(settings, profile.for_prompt(), profile.column_names())
            generator = "llm"
            note = f"Suggested by {provider} ({model}) from the table profile."
        except LlmError as exc:
            drafts = recommend_rules(profile)
            note = (
                f"The language model could not be reached ({exc}). "
                "Showing checks from the table profile instead."
            )
    else:
        drafts = recommend_rules(profile)

    known = _existing_signatures(profile.schema_name, profile.table_name)
    created: list[Rule] = []
    with transaction.atomic():
        for draft in drafts:
            key = signature(draft.expectation_type, draft.kwargs)
            if key in known:
                continue
            known.add(key)
            created.append(_store(profile, draft, generator))
    if not created:
        note = "No new checks were added. The suggestions are already saved for this table. " + note
    return {
        "generator": generator if created else "none",
        "provider": provider,
        "model": model,
        "note": note,
        "created": created,
    }


def from_language(schema_name: str, table_name: str, text: str, settings: LlmSettings | None = None):
    settings = settings or current_llm_settings()
    profile = profile_table(schema_name, table_name)
    translated_by = "rules"
    note = "Translated with the built-in phrase rules because no API key is configured."
    try:
        if settings.llm_configured():
            drafts = translate_with_llm(settings, profile.for_prompt(), profile.column_names(), text)
            translated_by = "llm"
            note = f"Translated by {settings.llm_provider.strip().lower()} ({settings.llm_model()})."
        else:
            drafts = translate_locally(text, profile.columns)
    except LlmError as exc:
        drafts = translate_locally(text, profile.columns)
        note = f"The language model could not be reached ({exc}). Translated with phrase rules instead."
        translated_by = "rules"

    known = _existing_signatures(profile.schema_name, profile.table_name)
    created: list[Rule] = []
    with transaction.atomic():
        for draft in drafts:
            key = signature(draft.expectation_type, draft.kwargs)
            if key in known:
                continue
            known.add(key)
            created.append(_store(profile, draft, "natural_language"))
    if not created:
        raise ValueError("That check is already saved for this table.")
    return {"rules": created, "translated_by": translated_by, "note": note}


def update_rule(rule: Rule, changes: dict) -> Rule:
    profile = profile_table(rule.schema_name, rule.table_name)
    kwargs = changes["kwargs"] if "kwargs" in changes and changes["kwargs"] is not None else rule.kwargs
    severity = changes["severity"] if "severity" in changes and changes["severity"] is not None else rule.severity
    title = changes["title"] if "title" in changes and changes["title"] is not None else rule.title
    plain = (
        changes["plain_language"]
        if "plain_language" in changes and changes["plain_language"] is not None
        else rule.plain_language
    )
    checked = coerce_rule(
        {
            "title": title,
            "plain_language": plain,
            "expectation_type": rule.expectation_type,
            "kwargs": kwargs,
            "severity": severity,
        },
        profile.column_names(),
    )
    rule.title = checked.title
    rule.plain_language = checked.plain_language
    rule.kwargs = checked.kwargs
    rule.severity = checked.severity
    if "enabled" in changes and changes["enabled"] is not None:
        rule.enabled = bool(changes["enabled"])
    rule.updated_at = timezone.now()
    rule.save()
    return rule


def execute(
    schema_name: str,
    table_name: str,
    database_url: str,
    rule_ids: list[str] | None = None,
) -> Run:
    profile = profile_table(schema_name, table_name)
    query = Rule.objects.filter(
        schema_name=profile.schema_name,
        table_name=profile.table_name,
        enabled=True,
    )
    if rule_ids:
        query = query.filter(id__in=rule_ids)
    rules = list(query.order_by("created_at"))
    if not rules:
        raise ValueError("There are no active checks to run. Suggest or add one first.")

    run = Run.objects.create(
        id=new_id(),
        schema_name=profile.schema_name,
        table_name=profile.table_name,
        status="running",
        started_at=timezone.now(),
    )

    try:
        outcomes = run_rules(database_url, profile.schema_name, profile.table_name, rules)
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)[:500]
        run.finished_at = timezone.now()
        run.save()
        raise RuntimeError(run.error_message) from exc

    counts = {"passed": 0, "failed": 0, "warning": 0, "error": 0}
    results = []
    for outcome in outcomes:
        counts[outcome["outcome"]] = counts.get(outcome["outcome"], 0) + 1
        results.append(
            RunResult(
                id=new_id(),
                run_id=run.id,
                rule_id=outcome["rule_id"],
                title=outcome["title"],
                expectation_type=outcome["expectation_type"],
                kwargs=outcome["kwargs"],
                severity=outcome["severity"],
                outcome=outcome["outcome"],
                unexpected_count=outcome["unexpected_count"],
                unexpected_percent=outcome["unexpected_percent"],
                sample_failures=outcome["sample_failures"],
                observed=outcome["observed"],
                error_message=outcome["error_message"],
            )
        )
    RunResult.objects.bulk_create(results)
    run.status = "completed"
    run.finished_at = timezone.now()
    run.passed_count = counts["passed"]
    run.failed_count = counts["failed"]
    run.warning_count = counts["warning"]
    run.error_count = counts["error"]
    run.save()
    return Run.objects.prefetch_related("results").get(id=run.id)
