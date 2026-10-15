"""Start the API and prepare the database on the serving process."""

from __future__ import annotations

import logging

from django.core.management.commands.runserver import Command as DjangoRunserver

logger = logging.getLogger(__name__)


class Command(DjangoRunserver):
    def inner_run(self, *args, **options):
        from quality.bootstrap import prepare_runtime

        prepare_runtime()
        super().inner_run(*args, **options)
