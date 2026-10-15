#!/usr/bin/env python3
"""Trigger Easypanel database backups via the public API.

Replaces the panel's built-in scheduler when the license does not run cron jobs.
Polls often (default every minute) and only runs backups whose EasyPanel cron
matches the current minute (TZ). Docs: https://easypanel.io/docs/api
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

DATABASE_TYPES = frozenset({"postgres", "mysql", "mariadb", "mongo"})
STATE_DIR = Path(os.getenv("STATE_DIR", "/tmp/easypanel-backup-state"))

# Logs go to stdout so Dozzle (and docker logs) pick them up automatically.
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
logging.basicConfig(level=logging.INFO, handlers=[_handler], force=True)
log = logging.getLogger("easypanel-backups")


def banner(title: str) -> None:
    line = "=" * 56
    log.info(line)
    log.info(title)
    log.info(line)


def _parse_cron_field(field: str, minimum: int, maximum: int) -> set[int]:
    """Parse one standard cron field (*, lists, ranges, steps) into ints."""
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = int(step_s)
            if step < 1:
                raise ValueError(f"invalid cron step in {field!r}")
        else:
            base = part

        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            a, b = base.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = int(base)
            end = maximum if "/" in part else start

        if start < minimum or end > maximum or start > end:
            raise ValueError(f"cron field out of range {minimum}-{maximum}: {field!r}")
        values.update(range(start, end + 1, step))
    return values


def cron_matches(expr: str, dt: datetime) -> bool:
    """Return True if a 5-field cron expression matches dt (local time).

    Day-of-month and day-of-week follow Vixie cron: if both are restricted
    (not *), the day matches when either field matches.
    """
    fields = expr.strip().split()
    if len(fields) != 5:
        raise ValueError(f"expected 5 cron fields, got {len(fields)}: {expr!r}")

    minute_f, hour_f, dom_f, month_f, dow_f = fields
    if dt.minute not in _parse_cron_field(minute_f, 0, 59):
        return False
    if dt.hour not in _parse_cron_field(hour_f, 0, 23):
        return False
    if dt.month not in _parse_cron_field(month_f, 1, 12):
        return False

    # Python: Mon=0..Sun=6 → cron: Sun=0..Sat=6 (also accept 7 = Sunday)
    cron_dow = (dt.weekday() + 1) % 7
    dow_values = _parse_cron_field(dow_f, 0, 7)
    if 7 in dow_values:
        dow_values.add(0)
    dow_ok = cron_dow in dow_values
    dom_ok = dt.day in _parse_cron_field(dom_f, 1, 31)

    dom_any = dom_f.strip() == "*"
    dow_any = dow_f.strip() == "*"
    if dom_any and dow_any:
        return True
    if not dom_any and not dow_any:
        return dom_ok or dow_ok
    if dom_any:
        return dow_ok
    return dom_ok


def backup_cron_expr(backup: dict[str, Any]) -> str | None:
    for key in ("cron", "schedule", "cronExpression", "crontab"):
        raw = backup.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def claim_fire_slot(backup_id: str, minute_key: str) -> bool:
    """Atomically claim this backup for this minute. False = already claimed."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{backup_id}_{minute_key}"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False


def cleanup_state(keep_minutes: int = 180) -> None:
    """Drop old claim files so /tmp does not grow forever."""
    if not STATE_DIR.is_dir():
        return
    cutoff = datetime.now().timestamp() - keep_minutes * 60
    for path in STATE_DIR.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue


class EasyPanelClient:
    def __init__(self, base_url: str, token: str, timeout: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        if not self.base_url.endswith("/api"):
            self.base_url = f"{self.base_url}/api"
        self.token = token
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        data = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{method} {path} -> network error: {exc}") from exc

    def get_session(self) -> Any:
        return self._request("GET", "getSession")

    def list_projects_and_services(self) -> Any:
        return self._request("GET", "listProjectsAndServices")

    def list_database_backups(self, project_name: str, service_name: str) -> Any:
        return self._request(
            "GET",
            "listDatabaseBackups",
            params={"projectName": project_name, "serviceName": service_name},
        )

    def run_database_backup(self, backup_id: str) -> Any:
        return self._request("POST", "runDatabaseBackup", body={"id": backup_id})


def _csv_set(value: str | None) -> set[str] | None:
    if not value or not value.strip():
        return None
    return {item.strip() for item in value.split(",") if item.strip()}


def _as_list(payload: Any) -> list[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("json", "data", "result", "backups", "items", "services", "projects"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return nested
            if isinstance(nested, dict):
                unwrapped = _as_list(nested)
                if unwrapped:
                    return unwrapped
        # Single backup object
        if "id" in payload:
            return [payload]
    return []


def extract_services(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("services"), list):
        return [s for s in payload["services"] if isinstance(s, dict)]

    services: list[dict[str, Any]] = []
    for project in _as_list(payload):
        if not isinstance(project, dict):
            continue
        project_name = project.get("name") or project.get("projectName")
        nested = project.get("services")
        if isinstance(nested, list):
            for service in nested:
                if isinstance(service, dict):
                    item = dict(service)
                    item.setdefault("projectName", project_name)
                    services.append(item)
    if services:
        return services

    # Flat list of services
    return [s for s in _as_list(payload) if isinstance(s, dict) and "type" in s]


def extract_backups(payload: Any) -> list[dict[str, Any]]:
    return [b for b in _as_list(payload) if isinstance(b, dict) and b.get("id")]


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def digits_only(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def sanitize_whatsapp_param(text: str, max_len: int = 900) -> str:
    """Meta rejects newlines/tabs in many template body params; keep one line."""
    cleaned = " ".join(text.replace("\r", " ").replace("\n", " ").replace("\t", " ").split())
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3] + "..."
    return cleaned or "sem detalhes"


def send_whatsapp_alert(detail: str) -> None:
    """Send Meta WhatsApp Cloud API template `system_alert` with {{1}} = detail."""
    phone_number_id = os.getenv("WHATSAPP_SYSTEM_PHONE_NUMBER_ID", "").strip()
    access_token = os.getenv("WHATSAPP_SYSTEM_ACCESS_TOKEN", "").strip()
    to_number = digits_only(os.getenv("WHATSAPP_NUMBER_TO", ""))
    template_name = os.getenv("WHATSAPP_TEMPLATE_NAME", "system_alert").strip() or "system_alert"
    language = os.getenv("WHATSAPP_TEMPLATE_LANG", "pt_BR").strip() or "pt_BR"
    api_version = os.getenv("WHATSAPP_API_VERSION", "v21.0").strip() or "v21.0"

    if not phone_number_id or not access_token or not to_number:
        log.warning(
            "WhatsApp alert skipped (set WHATSAPP_SYSTEM_PHONE_NUMBER_ID, "
            "WHATSAPP_SYSTEM_ACCESS_TOKEN, WHATSAPP_NUMBER_TO)"
        )
        return

    body_text = sanitize_whatsapp_param(detail)
    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": body_text}],
                }
            ],
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            log.info("WhatsApp alert sent to %s | response=%s", to_number, raw[:300])
    except urllib.error.HTTPError as exc:
        detail_body = exc.read().decode("utf-8", errors="replace")
        log.error("WhatsApp alert failed HTTP %s: %s", exc.code, detail_body)
    except Exception as exc:
        log.error("WhatsApp alert failed: %s", exc)


def notify_failures(errors: list[str]) -> None:
    if not errors:
        return
    summary = f"Easypanel backups: {len(errors)} falha(s). " + " | ".join(errors)
    log.info("sending WhatsApp failure notification...")
    send_whatsapp_alert(summary)


def run() -> int:
    errors: list[str] = []
    now = datetime.now()
    minute_key = now.strftime("%Y%m%d%H%M")
    cleanup_state()

    base_url = os.getenv("EASYPANEL_URL", "").strip()
    token = os.getenv("EASYPANEL_TOKEN", "").strip()
    if not base_url or not token:
        msg = "EASYPANEL_URL and EASYPANEL_TOKEN are required"
        log.error(msg)
        notify_failures([msg])
        return 1

    project_filter = _csv_set(os.getenv("EASYPANEL_PROJECTS"))
    service_filter = _csv_set(os.getenv("EASYPANEL_SERVICES"))
    only_enabled = env_bool("ONLY_ENABLED", True)
    dry_run = env_bool("DRY_RUN", False)
    respect_backup_cron = env_bool("RESPECT_BACKUP_CRON", True)
    # RUN_ON_START sets FORCE_BACKUP_RUN=1 once so the first pass ignores schedules.
    force_run = env_bool("FORCE_BACKUP_RUN", False)
    verbose_poll = env_bool("VERBOSE_POLL", False)

    client = EasyPanelClient(base_url, token)

    # On force/verbose, log network steps — otherwise a slow panel looks hung
    # after entrypoint's "running backups once on start". Quiet polls stay silent.
    if force_run or verbose_poll:
        log.info(
            "connecting | url=%s | force=%s | respect_cron=%s | dry_run=%s",
            client.base_url,
            force_run,
            respect_backup_cron,
            dry_run,
        )
    try:
        client.get_session()
        if force_run or verbose_poll:
            log.info("auth ok")
    except Exception as exc:
        msg = f"auth/session failed: {exc}"
        log.error(msg)
        notify_failures([msg])
        return 1

    if force_run or verbose_poll:
        log.info("discovering projects/services...")
    try:
        projects_payload = client.list_projects_and_services()
    except Exception as exc:
        msg = f"listProjectsAndServices failed: {exc}"
        log.error(msg)
        notify_failures([msg])
        return 1

    services = extract_services(projects_payload)
    db_services = [
        s
        for s in services
        if str(s.get("type", "")).lower() in DATABASE_TYPES
    ]

    if project_filter:
        db_services = [
            s for s in db_services if s.get("projectName") in project_filter
        ]
    if service_filter:
        db_services = [s for s in db_services if s.get("name") in service_filter]

    if not db_services:
        if verbose_poll or force_run:
            log.warning("no database services found matching filters")
        return 0

    triggered = 0
    skipped = 0
    failed = 0
    due_found = False

    for service in db_services:
        project_name = service.get("projectName")
        service_name = service.get("name")
        service_type = service.get("type")
        if not project_name or not service_name:
            skipped += 1
            continue

        try:
            backups_payload = client.list_database_backups(
                str(project_name), str(service_name)
            )
        except Exception as exc:
            msg = f"listDatabaseBackups {project_name}/{service_name}: {exc}"
            log.error(msg)
            errors.append(msg)
            failed += 1
            continue

        backups = extract_backups(backups_payload)
        if not backups:
            continue

        for backup in backups:
            backup_id = str(backup["id"])
            database_name = backup.get("databaseName") or "?"
            enabled = backup.get("enabled", True)
            destination = (
                backup.get("storageProviderPath")
                or backup.get("destination")
                or backup.get("storageProviderId")
                or "?"
            )
            cron_expr = backup_cron_expr(backup)

            if only_enabled and enabled is False:
                skipped += 1
                if verbose_poll or force_run:
                    log.info(
                        "SKIP disabled | %s/%s | id=%s | db=%s",
                        project_name,
                        service_name,
                        backup_id,
                        database_name,
                    )
                continue

            if respect_backup_cron and not force_run:
                if not cron_expr:
                    skipped += 1
                    log.warning(
                        "SKIP no cron on backup config | %s/%s | id=%s | db=%s",
                        project_name,
                        service_name,
                        backup_id,
                        database_name,
                    )
                    continue
                try:
                    is_due = cron_matches(cron_expr, now)
                except ValueError as exc:
                    msg = (
                        f"invalid cron {cron_expr!r} on {project_name}/{service_name} "
                        f"id={backup_id}: {exc}"
                    )
                    log.error(msg)
                    errors.append(msg)
                    failed += 1
                    continue
                if not is_due:
                    skipped += 1
                    if verbose_poll:
                        log.info(
                            "SKIP not due | %s/%s | cron=%s | id=%s | db=%s",
                            project_name,
                            service_name,
                            cron_expr,
                            backup_id,
                            database_name,
                        )
                    continue

            if not claim_fire_slot(backup_id, minute_key):
                skipped += 1
                log.info(
                    "SKIP already claimed this minute | id=%s | db=%s",
                    backup_id,
                    database_name,
                )
                continue

            if not due_found:
                due_found = True
                banner("BACKUP RUN START")
                log.info(
                    "now=%s tz=%s respect_cron=%s force=%s dry_run=%s",
                    now.strftime("%Y-%m-%d %H:%M:%S"),
                    os.getenv("TZ", "container-local"),
                    respect_backup_cron,
                    force_run,
                    dry_run,
                )
                log.info(
                    "filters projects=%s services=%s only_enabled=%s",
                    sorted(project_filter) if project_filter else "ALL",
                    sorted(service_filter) if service_filter else "ALL",
                    only_enabled,
                )

            log.info(
                "--- %s/%s (%s) ---",
                project_name,
                service_name,
                service_type,
            )

            if dry_run:
                log.info(
                    "DRY_RUN | id=%s | db=%s | cron=%s | dest=%s",
                    backup_id,
                    database_name,
                    cron_expr or "-",
                    destination,
                )
                triggered += 1
                continue

            log.info(
                "RUN | id=%s | db=%s | cron=%s | dest=%s",
                backup_id,
                database_name,
                cron_expr or "-",
                destination,
            )
            try:
                client.run_database_backup(backup_id)
                triggered += 1
                log.info("OK | id=%s | db=%s", backup_id, database_name)
            except Exception as exc:
                failed += 1
                msg = (
                    f"runDatabaseBackup {project_name}/{service_name} "
                    f"db={database_name} dest={destination} id={backup_id}: {exc}"
                )
                log.error("FAIL | %s", msg)
                errors.append(msg)

    if due_found or failed:
        banner(
            f"BACKUP RUN END | triggered={triggered} skipped={skipped} failed={failed}"
        )
    elif verbose_poll or force_run:
        log.info(
            "poll | now=%s | due=0 | skipped=%s | failed=%s",
            now.strftime("%H:%M"),
            skipped,
            failed,
        )

    notify_failures(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
