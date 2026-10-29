from django.core.management.base import BaseCommand

from market.services.afx import SessionNotClosed
from market.services.ingest import fetch_session_closes


class Command(BaseCommand):
    help = "Append today's NSE close to the month CSV and Postgres."

    def handle(self, *args, **options):
        try:
            written = fetch_session_closes()
        except SessionNotClosed as exc:
            self.stderr.write(str(exc))
            raise SystemExit(1) from exc
        self.stdout.write(self.style.SUCCESS(f"Stored {written} new close rows."))
