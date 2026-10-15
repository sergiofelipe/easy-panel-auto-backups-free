#!/bin/sh
set -eu

# Worker poll interval. Default every minute so each backup's EasyPanel cron can be honored.
CRON_SCHEDULE="${CRON_SCHEDULE:-* * * * *}"
RUN_ON_START="${RUN_ON_START:-true}"
ENV_FILE="${EASYPANEL_BACKUPS_ENV_FILE:-/etc/easypanel-backups.env}"
APP_ENV_FILE="${ENV_FILE_PATH:-/app/.env}"

# Persist env for cron jobs (cron starts with a nearly empty environment).
# Python also loads /app/.env itself — EasyPanel "Create env file" often writes
# secrets there instead of (or in addition to) process env.
# Do NOT persist FORCE_BACKUP_RUN — that is only for the optional on-start pass.
: > "${ENV_FILE}"
printenv | grep -E '^(EASYPANEL_|ONLY_ENABLED|DRY_RUN|TZ|WHATSAPP_|RESPECT_BACKUP_CRON|VERBOSE_POLL|STATE_DIR)=' >> "${ENV_FILE}" || true

if [ -f "${APP_ENV_FILE}" ]; then
  grep -E '^(EASYPANEL_|ONLY_ENABLED|DRY_RUN|TZ|WHATSAPP_|RESPECT_BACKUP_CRON|VERBOSE_POLL|STATE_DIR)=' "${APP_ENV_FILE}" >> "${ENV_FILE}" || true
  echo "[entrypoint] merged ${APP_ENV_FILE} into ${ENV_FILE}"
elif [ -f /app/.env ]; then
  grep -E '^(EASYPANEL_|ONLY_ENABLED|DRY_RUN|TZ|WHATSAPP_|RESPECT_BACKUP_CRON|VERBOSE_POLL|STATE_DIR)=' /app/.env >> "${ENV_FILE}" || true
  echo "[entrypoint] merged /app/.env into ${ENV_FILE}"
else
  echo "[entrypoint] no /app/.env found (ok if vars are only in process env)"
fi

chmod 600 "${ENV_FILE}" || true
ENV_KEYS="$(grep -c '=' "${ENV_FILE}" 2>/dev/null || echo 0)"

cat > /etc/cron.d/easypanel-backups <<EOF
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
${CRON_SCHEDULE} root cd /app && /usr/local/bin/python /app/run_backups.py >> /proc/1/fd/1 2>> /proc/1/fd/2
EOF

chmod 0644 /etc/cron.d/easypanel-backups

echo "[entrypoint] container ready — logs go to Docker stdout (visible in Dozzle)"
echo "[entrypoint] worker poll cron: ${CRON_SCHEDULE}"
echo "[entrypoint] respect backup cron: ${RESPECT_BACKUP_CRON:-true}"
echo "[entrypoint] run on start: ${RUN_ON_START}"
echo "[entrypoint] persisted env file: ${ENV_FILE} (${ENV_KEYS} keys)"

# Diagnose without leaking secrets. Prefer process env; fall back to .env file.
env_len() {
  # $1 = var name
  eval "val=\${$1:-}"
  if [ -n "$val" ]; then
    echo "${#val}"
    return
  fi
  if [ -f /app/.env ]; then
    line="$(grep -E "^$1=" /app/.env | tail -n 1 || true)"
    if [ -n "$line" ]; then
      echo "$(( ${#line} - ${#1} - 1 ))"
      return
    fi
  fi
  echo 0
}

URL_LEN="$(env_len EASYPANEL_URL)"
TOKEN_LEN="$(env_len EASYPANEL_TOKEN)"

if [ "${URL_LEN}" != "0" ]; then
  echo "[entrypoint] EASYPANEL_URL: set (${URL_LEN} chars)"
else
  echo "[entrypoint] EASYPANEL_URL: MISSING — add it in Environment (or .env) and redeploy"
fi
if [ "${TOKEN_LEN}" != "0" ]; then
  echo "[entrypoint] EASYPANEL_TOKEN: set (${TOKEN_LEN} chars)"
else
  echo "[entrypoint] EASYPANEL_TOKEN: MISSING — add it in Environment (or .env) and redeploy"
fi

WA_LEN="$(env_len WHATSAPP_SYSTEM_ACCESS_TOKEN)"
if [ "${WA_LEN}" != "0" ]; then
  echo "[entrypoint] WHATSAPP_*: set"
else
  echo "[entrypoint] WHATSAPP_*: not set (alerts disabled)"
fi

if [ "${RUN_ON_START}" = "true" ] || [ "${RUN_ON_START}" = "1" ]; then
  echo "[entrypoint] running backups once on start (FORCE_BACKUP_RUN=1, ignores per-backup cron)..."
  FORCE_BACKUP_RUN=1 /usr/local/bin/python /app/run_backups.py || true
fi

echo "[entrypoint] starting cron in foreground — polling for due EasyPanel backup schedules"
exec cron -f
