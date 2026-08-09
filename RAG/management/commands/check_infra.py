"""
Startup/readiness validation for Postgres, pgvector, Redis, Celery
workers (when async processing is enabled), and every configured LLM
provider - a CLI wrapper around health_service.get_health_status(),
the same check backing the public /health/ endpoint.

Deliberately a standalone command, not wired into Django's boot
sequence (AppConfig.ready()) - this codebase already has one
documented footgun from querying the database there (a RuntimeWarning
surfaced during this project's test runs), and forcing an infra check
into every single `manage.py` invocation (migrate, shell, test, ...)
would slow all of them down for a check only a deploy/CI script
actually needs. Run it explicitly:

    python manage.py check_infra

Exits 0 if every check that's actually relevant to this deployment's
configuration passes, 1 otherwise - suitable as a deploy-script/CI
gate, not just a human-readable report.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from RAG.services.health_service import get_health_status


class Command(BaseCommand):
    help = "Validate Postgres, pgvector, Redis, Celery, and configured LLM providers are reachable."

    def handle(self, *args, **options):

        # live_llm_check=True: a one-off CLI run should answer "are the
        # providers reachable right now", the same live generate() call
        # Monitoring's manual "Check Now" button uses - unlike the
        # public /health/ endpoint and Monitoring's 15s auto-refresh,
        # this command isn't polled continuously, so there's no
        # API-quota cost concern here.
        health = get_health_status(live_llm_check=True)
        checks = health["checks"]

        self.stdout.write("Infrastructure check")
        self.stdout.write("=====================")

        self._report("PostgreSQL", checks["database"])
        self._report("pgvector extension", checks["pgvector"])

        redis_relevant = settings.USE_REDIS_CACHE or settings.ENABLE_ASYNC_PROCESSING
        self._report(
            "Redis",
            checks["redis"],
            note="not required (USE_REDIS_CACHE and ENABLE_ASYNC_PROCESSING are both off)" if not redis_relevant else None,
        )

        if settings.ENABLE_ASYNC_PROCESSING:
            workers = health["celery_workers"] or 0
            self._report(f"Celery workers ({workers} responded)", workers > 0)
        else:
            self.stdout.write(self.style.WARNING("  - Celery workers: skipped (ENABLE_ASYNC_PROCESSING is off)"))

        llm_providers = checks["llm_providers"]

        if not llm_providers:
            self.stdout.write(self.style.WARNING("  - LLM providers: none configured - add an API key to .env"))
        else:
            for provider, result in llm_providers.items():
                latency = f" ({result['latency_ms']}ms)" if result.get("latency_ms") else ""
                self._report(f"LLM provider: {provider}{latency}", result["ok"])

        self.stdout.write("=====================")

        if health["status"] == "ok":
            self.stdout.write(self.style.SUCCESS(f"Overall status: {health['status'].upper()}"))
        else:
            self.stdout.write(self.style.ERROR(f"Overall status: {health['status'].upper()}"))
            raise SystemExit(1)

    def _report(self, label, ok, note=None):

        if note:
            self.stdout.write(f"  - {label}: {note}")
            return

        symbol = self.style.SUCCESS("OK") if ok else self.style.ERROR("FAIL")
        self.stdout.write(f"  - {label}: {symbol}")
