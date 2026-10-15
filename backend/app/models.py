"""App tables live in the dq schema, separate from the data being checked."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Rule(Base):
    __tablename__ = "rules"
    __table_args__ = (
        Index("ix_rules_table", "schema_name", "table_name"),
        {"schema": "dq"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    schema_name: Mapped[str] = mapped_column(String(128))
    table_name: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(200))
    plain_language: Mapped[str] = mapped_column(Text)
    expectation_type: Mapped[str] = mapped_column(String(128))
    kwargs: Mapped[dict] = mapped_column(JSON)
    severity: Mapped[str] = mapped_column(String(16), default="warning")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    generator: Mapped[str] = mapped_column(String(32), default="profiler")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    results: Mapped[list[RunResult]] = relationship(back_populates="rule")


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_table", "schema_name", "table_name", "started_at"),
        {"schema": "dq"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    schema_name: Mapped[str] = mapped_column(String(128))
    table_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    results: Mapped[list[RunResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class RunResult(Base):
    __tablename__ = "run_results"
    __table_args__ = ({"schema": "dq"},)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("dq.runs.id", ondelete="CASCADE"))
    rule_id: Mapped[str | None] = mapped_column(
        ForeignKey("dq.rules.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    expectation_type: Mapped[str] = mapped_column(String(128))
    kwargs: Mapped[dict] = mapped_column(JSON)
    severity: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(16))
    unexpected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unexpected_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_failures: Mapped[list] = mapped_column(JSON, default=list)
    observed: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[Run] = relationship(back_populates="results")
    rule: Mapped[Rule | None] = relationship(back_populates="results")
