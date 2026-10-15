#!/bin/sh
set -eu

# Worker poll interval. Default every minute so each backup's EasyPanel cron can be honored.
CRON_SCHEDULE="${CRON_SCHEDULE:-* * * * *}"
RUN_ON_START="${RUN_ON_START:-true}"

# Persist env for cron jobs (cron starts with a minimal environment).
# Do NOT persist FORCE_BACKUP_RUN — that is only for the optional on-start pass.
printenv | grep -E '^(EASYPANEL_|ONLY_ENABLED|DRY_RUN|TZ|WHATSAPP_|RESPECT_BACKUP_CRON|VERBOSE_POLL|STATE_DIR)=' > /etc/environment || true

cat > /etc/cron.d/easypanel-backups <<EOF
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
${CRON_SCHEDULE} root . /etc/environment; cd /app && /usr/local/bin/python /app/run_backups.py >> /proc/1/fd/1 2>> /proc/1/fd/2
EOF

chmod 0644 /etc/cron.d/easypanel-backups

echo "[entrypoint] container ready — logs go to Docker stdout (visible in Dozzle)"
echo "[entrypoint] worker poll cron: ${CRON_SCHEDULE}"
echo "[entrypoint] respect backup cron: ${RESPECT_BACKUP_CRON:-true}"
echo "[entrypoint] run on start: ${RUN_ON_START}"

if [ "${RUN_ON_START}" = "true" ] || [ "${RUN_ON_START}" = "1" ]; then
  echo "[entrypoint] running backups once on start (FORCE_BACKUP_RUN=1, ignores per-backup cron)..."
  FORCE_BACKUP_RUN=1 /usr/local/bin/python /app/run_backups.py || true
fi

echo "[entrypoint] starting cron in foreground — polling for due EasyPanel backup schedules"
exec cron -f
