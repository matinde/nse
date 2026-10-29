#!/bin/sh
set -e
data_dir="${DATA_DIR:-/app/data}"
mkdir -p "$data_dir"
if [ -d /app/seed-data ]; then
  for file in /app/seed-data/*.csv; do
    [ -f "$file" ] || continue
    name=$(basename "$file")
    if [ ! -f "$data_dir/$name" ]; then
      cp "$file" "$data_dir/$name"
      echo "Copied $name into $data_dir"
    fi
  done
fi
echo "Applying database migrations"
python manage.py migrate --noinput
echo "Collecting static files"
python manage.py collectstatic --noinput
echo "Importing price CSV files from ${DATA_DIR:-/app/data}"
python manage.py import_csvs
echo "Starting operator admin on port 9012"
gunicorn config.wsgi:application --bind 0.0.0.0:9012 --workers 2 --timeout 120 --access-logfile - --error-logfile - &
echo "Starting chart on port ${PORT:-9011}"
exec streamlit run app.py --server.address 0.0.0.0 --server.port "${PORT:-9011}" --server.headless true --server.enableCORS false --server.enableXsrfProtection false --server.fileWatcherType none
