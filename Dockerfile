FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Sao_Paulo \
    CRON_SCHEDULE="0 2 * * *" \
    RUN_ON_START=true \
    ONLY_ENABLED=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends cron tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY run_backups.py /app/run_backups.py
COPY entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh /app/run_backups.py

CMD ["/app/entrypoint.sh"]
