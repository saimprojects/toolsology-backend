from __future__ import annotations

import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from sourcing.services import auto_match_all, sync_all_active_bots


# Stable application-specific PostgreSQL advisory-lock identifier.
SYNC_LOCK_ID = 846_020_260_802


class Command(BaseCommand):
    help = "Sync every active supplier bot, once or continuously."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep syncing at the configured interval.")
        parser.add_argument("--interval", type=int, help="Override interval in seconds (minimum 60).")

    def _try_lock(self) -> bool:
        if connection.vendor != "postgresql":
            return True
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [SYNC_LOCK_ID])
            return bool(cursor.fetchone()[0])

    def _unlock(self):
        if connection.vendor != "postgresql":
            return
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [SYNC_LOCK_ID])

    def sync_once(self):
        if not self._try_lock():
            self.stdout.write("Supplier sync skipped: another worker owns the lock.")
            return
        try:
            results = sync_all_active_bots()
            matched = auto_match_all()
            synced = sum(item["synced"] for item in results if not item["error"])
            errors = [item for item in results if item["error"]]
            self.stdout.write(
                f"Supplier sync complete: {len(results) - len(errors)} bots OK, "
                f"{synced} products, {matched} new links, {len(errors)} errors."
            )
            for item in errors:
                self.stderr.write(f"{item['bot']}: {item['error']}")
        finally:
            self._unlock()

    def handle(self, *args, **options):
        interval = max(
            60,
            options.get("interval") or settings.SUPPLIER_SYNC_INTERVAL_SECONDS,
        )
        if not settings.SUPPLIER_AUTO_SYNC_ENABLED:
            self.stdout.write("Supplier auto-sync is disabled by configuration.")
            return

        self.sync_once()
        if not options["loop"]:
            return

        self.stdout.write(f"Supplier auto-sync running every {interval} seconds.")
        while True:
            time.sleep(interval)
            try:
                self.sync_once()
            except Exception as exc:  # keep future syncs alive after one bad run
                self.stderr.write(f"Unexpected supplier sync error: {exc}")
