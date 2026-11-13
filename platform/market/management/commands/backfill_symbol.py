from django.core.management.base import BaseCommand

from market.services.afx import SessionNotClosed
from market.services.ingest import backfill_symbol_history


class Command(BaseCommand):
    help = "Store today's close for one ticker from the NSE daily equity price list."

    def add_arguments(self, parser):
        parser.add_argument("code")

    def handle(self, *args, **options):
        code = options["code"].strip().upper()
        try:
            written = backfill_symbol_history(code)
        except (LookupError, SessionNotClosed) as exc:
            self.stderr.write(str(exc))
            raise SystemExit(1) from exc
        self.stdout.write(self.style.SUCCESS(f"Stored the NSE close for {code} ({written} rows)."))
