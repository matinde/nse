import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.beat_schedule = {
    "fetch-nse-session-closes": {
        "task": "market.tasks.fetch_session_closes",
        "schedule": crontab(hour=16, minute=45, day_of_week="1-5"),
    }
}
app.autodiscover_tasks()
