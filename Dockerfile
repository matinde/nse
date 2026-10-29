FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --retries 10 --timeout 120 -r requirements.txt

COPY app.py .
COPY data/ ./data/

EXPOSE 9010

CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0", "--server.port", "9010"]
