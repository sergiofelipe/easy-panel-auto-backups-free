#!/bin/sh
set -eu

# Worker poll interval. Default every minute so each backup's EasyPanel cron can be honored.
CRON_SCHEDULE="${CRON_SCHEDULE:-* * * * *}"
RUN_ON_START="${RUN_ON_START:-true}"

# Persist env for cron jobs (cron starts with a minimal environment).
# set -a makes sourced assignments export to child processes (needed for Python).
# Do NOT persist FORCE_BACKUP_RUN — that is only for the optional on-start pass.
ENV_FILE=/etc/easypanel-backups.env
printenv | grep -E '^(EASYPANEL_|ONLY_ENABLED|DRY_RUN|TZ|WHATSAPP_|RESPECT_BACKUP_CRON|VERBOSE_POLL|STATE_DIR)=' > "${ENV_FILE}" || true

cat > /etc/cron.d/easypanel-backups <<EOF
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
${CRON_SCHEDULE} root set -a; . ${ENV_FILE}; set +a; cd /app && /usr/local/bin/python /app/run_backups.py >> /proc/1/fd/1 2>> /proc/1/fd/2
EOF

chmod 0644 /etc/cron.d/easypanel-backups

echo "[entrypoint] container ready — logs go to Docker stdout (visible in Dozzle)"
echo "[entrypoint] worker poll cron: ${CRON_SCHEDULE}"
echo "[entrypoint] respect backup cron: ${RESPECT_BACKUP_CRON:-true}"
echo "[entrypoint] run on start: ${RUN_ON_START}"

# Diagnose without leaking secrets (common deploy footgun).
if [ -n "${EASYPANEL_URL:-}" ]; then
  echo "[entrypoint] EASYPANEL_URL: set (${#EASYPANEL_URL} chars)"
else
  echo "[entrypoint] EASYPANEL_URL: MISSING — add it in the service Environment tab and redeploy"
fi
if [ -n "${EASYPANEL_TOKEN:-}" ]; then
  echo "[entrypoint] EASYPANEL_TOKEN: set (${#EASYPANEL_TOKEN} chars)"
else
  echo "[entrypoint] EASYPANEL_TOKEN: MISSING — add it in the service Environment tab and redeploy"
fi

if [ "${RUN_ON_START}" = "true" ] || [ "${RUN_ON_START}" = "1" ]; then
  echo "[entrypoint] running backups once on start (FORCE_BACKUP_RUN=1, ignores per-backup cron)..."
  FORCE_BACKUP_RUN=1 /usr/local/bin/python /app/run_backups.py || true
fi

echo "[entrypoint] starting cron in foreground — polling for due EasyPanel backup schedules"
exec cron -f
