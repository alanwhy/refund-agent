import re
from typing import Any

from sqlalchemy.orm import Session

from refund_agent.models import AuditEvent

SENSITIVE_KEYS = {"password", "token", "authorization", "api_key", "secret"}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"Bearer\s+[A-Za-z0-9._-]+", "Bearer [REDACTED]", value)
    return value


def append_audit(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    ticket_id: str | None = None,
    actor_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ticket_id=ticket_id,
        actor_id=actor_id,
        details=redact(details or {}),
    )
    db.add(event)
    return event
