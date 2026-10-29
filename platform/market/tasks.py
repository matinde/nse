import requests
from celery import shared_task

from market.services.afx import SessionNotClosed
from market.services.ingest import fetch_session_closes as run_fetch


@shared_task(bind=True, max_retries=8)
def fetch_session_closes(self):
    try:
        return run_fetch()
    except SessionNotClosed as exc:
        raise self.retry(exc=exc, countdown=15 * 60)
    except requests.RequestException as exc:
        raise self.retry(exc=exc, countdown=5 * 60)
