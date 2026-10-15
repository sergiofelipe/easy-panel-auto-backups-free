FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Sao_Paulo \
    CRON_SCHEDULE="* * * * *" \
    POLL_INTERVAL_SECONDS=60 \
    RESPECT_BACKUP_CRON=true \
    RUN_ON_START=true \
    ONLY_ENABLED=true \
    WORKER_LOOP=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY run_backups.py /app/run_backups.py
COPY entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh /app/run_backups.py

CMD ["/app/entrypoint.sh"]
