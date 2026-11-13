import requests
from django.core.management.base import BaseCommand

from market.services.ingest import backfill_symbol_history


class Command(BaseCommand):
    help = "Add earlier closes for one ticker from its history page. Existing sessions are left as they are."

    def add_arguments(self, parser):
        parser.add_argument("code")

    def handle(self, *args, **options):
        code = options["code"].strip().upper()
        try:
            written = backfill_symbol_history(code)
        except (LookupError, requests.RequestException) as exc:
            self.stderr.write(str(exc))
            raise SystemExit(1) from exc
        self.stdout.write(self.style.SUCCESS(f"Stored {written} earlier closes for {code}."))
