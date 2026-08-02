import json
import re
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from refund_agent.models import AuditEvent

SENSITIVE_KEYS = {
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
    "accesstoken",
    "refreshtoken",
    "idtoken",
    "cookie",
    "setcookie",
    "sessioncookie",
}


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _normalized_key(key) in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item) for item in value]
    if isinstance(value, Enum):
        return redact(value.value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                parsed = json.loads(stripped)
            except (TypeError, ValueError):
                pass
            else:
                return json.dumps(redact(parsed), ensure_ascii=False)
        sanitized = re.sub(
            r"Bearer\s+[A-Za-z0-9._~+/=-]+",
            "Bearer [REDACTED]",
            value,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", sanitized)
        return re.sub(
            r"\b(api[_ -]?key|password|authorization|secret|access[_ -]?token|"
            r"refresh[_ -]?token)\s*[:=]\s*[^\s,;]+",
            r"\1=[REDACTED]",
            sanitized,
            flags=re.IGNORECASE,
        )
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def append_audit(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    ticket_id: str | None = None,
    actor_id: str | None = None,
    details: dict[str, Any] | None = None,
    event_key: str | None = None,
    run_id: str | None = None,
    node_name: str | None = None,
) -> AuditEvent:
    if event_key:
        existing = db.scalar(select(AuditEvent).where(AuditEvent.event_key == event_key))
        if existing is not None:
            return existing
    event = AuditEvent(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ticket_id=ticket_id,
        actor_id=actor_id,
        details=redact(details or {}),
        event_key=event_key,
        run_id=run_id,
        node_name=node_name,
    )
    db.add(event)
    return event
