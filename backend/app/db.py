"""Database engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Base

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS dq"))
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        session.execute(
            text(
                """
                UPDATE dq.runs
                SET status = 'failed',
                    error_message = 'Interrupted before the run finished',
                    finished_at = NOW()
                WHERE status = 'running'
                """
            )
        )
        session.commit()


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
