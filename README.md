# NSE Investment Explorer

A simple Streamlit dashboard for exploring Nairobi Securities Exchange prices. Yearly history and one CSV per month are loaded into Postgres. Each new session close is appended to the current month file.

## Features
- Single-stock price chart and historical investment calculator
- Compare selected stocks on a normalized performance chart
- Historical gainers/decliners leaderboard
- Data coverage and quality checks
- Download cleaned price history

## Run with Docker
From this folder:

`docker compose up --build`

- Explorer: http://localhost:9010
- Operator admin: http://localhost:9011/admin/ (create the account yourself with `python manage.py createsuperuser`)

The explorer reads Postgres. On startup the web service imports every yearly CSV and every `data/NSE_{Month}_{Year}_prices.csv`. A Celery job appends each new session close to the current month file at 16:45 Africa/Nairobi on weekdays. `./data` is mounted into the containers, so October, November, and later month files stay on the host.

To pull today's close without waiting for the clock, after the stack is up:

`docker compose exec web python manage.py fetch_closes`

## Run the explorer only
The explorer needs `DATABASE_URL` pointing at the Postgres service started by Docker. Use `docker compose up --build` rather than `streamlit run` on its own.

## Data notes
- Yearly files cover 2023, 2024, 2025 and January–June 2026. From October 2026 each month has its own CSV, named `NSE_{Month}_{Year}_prices.csv`.
- The app uses the recorded day price for charts and calculations.
- The provided `Adjusted Price` column contains `-` throughout, so dividend-inclusive total returns are not calculated.
- The app uses the latest record in the database. A weekday job adds that session's close after 16:45 Africa/Nairobi.
- Results exclude transaction fees, taxes and dividends.
- Some records may have missing volume, represented by `-`.
