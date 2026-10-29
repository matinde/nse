from django.core.management.base import BaseCommand

from market.services.ingest import import_csvs


class Command(BaseCommand):
    help = "Load yearly and monthly NSE CSV files into Postgres without rewriting them."

    def handle(self, *args, **options):
        written = import_csvs()
        self.stdout.write(self.style.SUCCESS(f"Imported {written} price rows."))
