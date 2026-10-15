#!/usr/bin/env python3
"""Trigger Easypanel database backups via the public API.

Replaces the panel's built-in scheduler when the license does not run cron jobs.
Docs: https://easypanel.io/docs/api
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DATABASE_TYPES = frozenset({"postgres", "mysql", "mariadb", "mongo"})

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
    banner("BACKUP RUN START")
    errors: list[str] = []

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

    log.info(
        "filters projects=%s services=%s only_enabled=%s dry_run=%s",
        sorted(project_filter) if project_filter else "ALL",
        sorted(service_filter) if service_filter else "ALL",
        only_enabled,
        dry_run,
    )

    client = EasyPanelClient(base_url, token)

    log.info("auth check -> %s", client.base_url)
    try:
        client.get_session()
        log.info("auth ok")
    except Exception as exc:
        msg = f"auth/session failed: {exc}"
        log.error(msg)
        notify_failures([msg])
        return 1

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
        log.warning("no database services found matching filters")
        banner("BACKUP RUN END (nothing to do)")
        return 0

    log.info("found %d database service(s):", len(db_services))
    for service in db_services:
        log.info(
            "  - %s/%s (%s)",
            service.get("projectName"),
            service.get("name"),
            service.get("type"),
        )

    triggered = 0
    skipped = 0
    failed = 0

    for service in db_services:
        project_name = service.get("projectName")
        service_name = service.get("name")
        service_type = service.get("type")
        if not project_name or not service_name:
            skipped += 1
            continue

        log.info("--- %s/%s (%s) ---", project_name, service_name, service_type)
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
            log.info("no backup configs on this service")
            continue

        log.info("found %d backup config(s)", len(backups))

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

            if only_enabled and enabled is False:
                log.info(
                    "SKIP disabled | id=%s | db=%s | dest=%s",
                    backup_id,
                    database_name,
                    destination,
                )
                skipped += 1
                continue

            if dry_run:
                log.info(
                    "DRY_RUN | id=%s | db=%s | dest=%s",
                    backup_id,
                    database_name,
                    destination,
                )
                triggered += 1
                continue

            log.info(
                "MANUAL RUN | id=%s | db=%s | dest=%s",
                backup_id,
                database_name,
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

    banner(
        f"BACKUP RUN END | triggered={triggered} skipped={skipped} failed={failed}"
    )
    notify_failures(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
