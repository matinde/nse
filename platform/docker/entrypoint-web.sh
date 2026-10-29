#!/bin/sh
set -e
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py import_csvs
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-9011} --workers 2 --timeout 120
