"""Create the dq schema, apply migrations, and load demo tables on startup."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)


def prepare_runtime() -> None:
    with connection.cursor() as cursor:
        cursor.execute("CREATE SCHEMA IF NOT EXISTS dq")
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'dq'
              AND table_name IN ('rules', 'runs', 'run_results')
            """
        )
        tables_ready = cursor.fetchone()[0] == 3

    from django.db.migrations.recorder import MigrationRecorder

    applied = MigrationRecorder(connection).applied_migrations()
    if tables_ready and ("quality", "0001_initial") not in applied:
        # Tables created by the previous service live in schema dq, which
        # Django's table listing does not see, so mark that migration applied.
        call_command("migrate", "quality", "0001_initial", fake=True, interactive=False, verbosity=1)
    else:
        call_command("migrate", interactive=False, verbosity=1, fake_initial=True)
    from quality.models import Run

    Run.objects.filter(status="running").update(
        status="failed",
        error_message="Interrupted before the run finished",
        finished_at=timezone.now(),
    )
    if settings.SEED_DEMO_DATA:
        from quality.seed import seed_if_needed

        created = seed_if_needed()
        if created:
            logger.info("Loaded demo tables customers, orders, and products.")
