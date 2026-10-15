"""HTTP API for tables, checks, and saved results."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db import get_session
from app.models import Rule, Run
from app.schemas import (
    HealthOut,
    NaturalLanguageIn,
    NaturalLanguageOut,
    RuleOut,
    RuleUpdate,
    RunOut,
    RunRequest,
    SuggestionOut,
    TableDetail,
    TableSummary,
)
from app.services.profiler import list_tables, profile_table
from app.services.rules import execute, from_language, suggest, update_rule

router = APIRouter(prefix="/api")


def _not_found(exc: LookupError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.get("/health", response_model=HealthOut)
def health(session: Session = Depends(get_session)) -> HealthOut:
    settings = get_settings()
    try:
        session.execute(text("SELECT 1"))
        database = "ok"
        status = "ok"
    except Exception:
        database = "unavailable"
        status = "degraded"
    configured = settings.llm_configured()
    provider = settings.llm_provider.strip().lower()
    if configured:
        message = f"Using {provider} ({settings.llm_model()})."
        mode = "llm"
    else:
        message = (
            "No API key is configured. Suggestions use the built-in profiler. "
            "Add a free Gemini key as GEMINI_API_KEY, or set LLM_PROVIDER=openai when you switch to a paid key."
        )
        mode = "profiler"
    return HealthOut(
        status=status,
        database=database,
        llm_provider=provider,
        llm_model=settings.llm_model(),
        llm_configured=configured,
        suggestion_mode=mode,
        message=message,
    )


@router.get("/tables", response_model=list[TableSummary])
def get_tables(session: Session = Depends(get_session)) -> list[dict]:
    return list_tables(session)


@router.get("/tables/{schema_name}/{table_name}", response_model=TableDetail)
def get_table(schema_name: str, table_name: str, session: Session = Depends(get_session)) -> dict:
    try:
        profile = profile_table(session, schema_name, table_name)
    except LookupError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "schema_name": profile.schema_name,
        "table_name": profile.table_name,
        "row_count": profile.row_count,
        "columns": [column.as_public() for column in profile.columns],
        "sample_rows": profile.sample_rows,
        "highlights": profile.highlights(),
    }


@router.get("/rules", response_model=list[RuleOut])
def get_rules(schema_name: str, table_name: str, session: Session = Depends(get_session)) -> list[Rule]:
    return list(
        session.scalars(
            select(Rule)
            .where(Rule.schema_name == schema_name, Rule.table_name == table_name)
            .order_by(Rule.created_at)
        )
    )


@router.post("/tables/{schema_name}/{table_name}/suggestions", response_model=SuggestionOut)
def post_suggestions(
    schema_name: str, table_name: str, session: Session = Depends(get_session)
) -> dict:
    try:
        return suggest(session, schema_name, table_name)
    except LookupError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/rules/natural-language", response_model=NaturalLanguageOut)
def post_natural_language(body: NaturalLanguageIn, session: Session = Depends(get_session)) -> dict:
    try:
        return from_language(session, body.schema_name, body.table_name, body.text)
    except LookupError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/rules/{rule_id}", response_model=RuleOut)
def patch_rule(rule_id: str, body: RuleUpdate, session: Session = Depends(get_session)) -> Rule:
    rule = session.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Check not found")
    try:
        return update_rule(session, rule, body.model_dump(exclude_unset=True))
    except LookupError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: str, session: Session = Depends(get_session)) -> None:
    rule = session.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Check not found")
    session.delete(rule)
    session.commit()


@router.post("/runs", response_model=RunOut)
def post_run(body: RunRequest, session: Session = Depends(get_session)) -> Run:
    settings = get_settings()
    try:
        return execute(session, body.schema_name, body.table_name, settings.database_url, body.rule_ids)
    except LookupError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/runs/latest", response_model=RunOut)
def get_latest_run(schema_name: str, table_name: str, session: Session = Depends(get_session)) -> Run:
    run = session.scalars(
        select(Run)
        .where(Run.schema_name == schema_name, Run.table_name == table_name, Run.status == "completed")
        .options(selectinload(Run.results))
        .order_by(Run.started_at.desc())
    ).first()
    if run is None:
        raise HTTPException(status_code=404, detail="No saved results for this table yet")
    return run


@router.get("/runs", response_model=list[RunOut])
def get_runs(schema_name: str, table_name: str, session: Session = Depends(get_session)) -> list[Run]:
    return list(
        session.scalars(
            select(Run)
            .where(Run.schema_name == schema_name, Run.table_name == table_name)
            .options(selectinload(Run.results))
            .order_by(Run.started_at.desc())
            .limit(8)
        )
    )


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, session: Session = Depends(get_session)) -> Run:
    run = session.scalars(
        select(Run).where(Run.id == run_id).options(selectinload(Run.results))
    ).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
