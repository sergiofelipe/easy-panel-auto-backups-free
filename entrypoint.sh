#!/bin/sh
set -eu

CRON_SCHEDULE="${CRON_SCHEDULE:-0 2 * * *}"
RUN_ON_START="${RUN_ON_START:-true}"

# Persist env for cron jobs (cron starts with a minimal environment).
printenv | grep -E '^(EASYPANEL_|ONLY_ENABLED|DRY_RUN|TZ|WHATSAPP_)=' > /etc/environment || true

cat > /etc/cron.d/easypanel-backups <<EOF
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
${CRON_SCHEDULE} root . /etc/environment; cd /app && /usr/local/bin/python /app/run_backups.py >> /proc/1/fd/1 2>> /proc/1/fd/2
EOF

chmod 0644 /etc/cron.d/easypanel-backups

echo "[entrypoint] container ready — logs go to Docker stdout (visible in Dozzle)"
echo "[entrypoint] cron schedule: ${CRON_SCHEDULE}"
echo "[entrypoint] run on start: ${RUN_ON_START}"

if [ "${RUN_ON_START}" = "true" ] || [ "${RUN_ON_START}" = "1" ]; then
  echo "[entrypoint] running backups once on start..."
  /usr/local/bin/python /app/run_backups.py || true
fi

echo "[entrypoint] starting cron in foreground — waiting for next schedule"
exec cron -f
