#!/bin/sh
set -e
echo "Applying database migrations"
python manage.py migrate --noinput
echo "Collecting static files"
python manage.py collectstatic --noinput
echo "Importing price CSV files from ${DATA_DIR:-/app/data}"
python manage.py import_csvs
echo "Starting web server on port ${PORT:-9011}"
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-9011} --workers 2 --timeout 120 --access-logfile - --error-logfile -
