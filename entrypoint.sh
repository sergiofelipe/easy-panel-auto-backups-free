#!/bin/sh
set -eu

cd /app

echo "[entrypoint] container ready — logs go to Docker stdout (visible in Dozzle)"
echo "[entrypoint] mode: in-process worker loop (no system cron — keeps container env)"
echo "[entrypoint] respect backup cron: ${RESPECT_BACKUP_CRON:-true}"
echo "[entrypoint] run on start: ${RUN_ON_START:-true}"
echo "[entrypoint] poll interval seconds: ${POLL_INTERVAL_SECONDS:-60}"

# EasyPanel "Create env file" → usually /app/.env (optional; process env also works now).
if [ -f /app/.env ]; then
  echo "[entrypoint] found /app/.env ($(wc -l < /app/.env | tr -d ' ') lines)"
else
  echo "[entrypoint] /app/.env not found — relying on process environment (+ discovery in Python)"
fi

# WORKER_LOOP=true is the default in run_backups.py; inherits this shell's env from Docker.
exec /usr/local/bin/python -u /app/run_backups.py --loop
