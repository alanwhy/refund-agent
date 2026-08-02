from collections.abc import Sequence
from pathlib import Path
from time import monotonic
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from refund_agent.audit.service import append_audit
from refund_agent.config import Settings, get_settings

PROMPT_VERSION = "refund-agent-v2.0"


def serialize_message(message: BaseMessage) -> dict[str, Any]:
    try:
        payload = message.model_dump(mode="json")
    except Exception as exc:
        return {
            "type": getattr(message, "type", type(message).__name__),
            "serialization_error": type(exc).__name__,
        }
    return dict(payload)


def build_chat_model(settings: Settings | None = None) -> BaseChatModel:
    current = settings or get_settings()
    base_url, api_key, model = current.require_model_config()
    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        timeout=current.llm_timeout_seconds,
        max_retries=current.llm_max_retries,
        temperature=0,
    )


def read_prompt(name: str) -> str:
    settings = get_settings()
    path = settings.prompts_dir / name
    if not path.exists():
        path = Path(__file__).resolve().parents[3] / "prompts" / name
    return path.read_text(encoding="utf-8")


def invoke_audited(
    model: BaseChatModel,
    messages: list[BaseMessage],
    *,
    db: Session,
    ticket_id: str,
    run_id: str,
    node_name: str,
    logical_step: int,
    tool_names: Sequence[str] = (),
) -> BaseMessage:
    settings = get_settings()
    event_prefix = f"{ticket_id}:refund-v2:{node_name}:{logical_step}"
    append_audit(
        db,
        action="model.requested",
        entity_type="model",
        ticket_id=ticket_id,
        details={
            "model": settings.llm_model,
            "prompt_version": PROMPT_VERSION,
            "logical_step": logical_step,
            "input": {
                "messages": [serialize_message(message) for message in messages],
                "tools": list(tool_names),
            },
        },
        event_key=f"{event_prefix}:requested",
        run_id=run_id,
        node_name=node_name,
    )
    started = monotonic()
    try:
        response = model.invoke(messages)
    except Exception as exc:
        append_audit(
            db,
            action="model.failed",
            entity_type="model",
            ticket_id=ticket_id,
            details={
                "model": settings.llm_model,
                "prompt_version": PROMPT_VERSION,
                "logical_step": logical_step,
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            },
            event_key=f"{event_prefix}:failed",
            run_id=run_id,
            node_name=node_name,
        )
        raise
    usage: dict[str, Any] = getattr(response, "usage_metadata", None) or {}
    append_audit(
        db,
        action="model.completed",
        entity_type="model",
        ticket_id=ticket_id,
        details={
            "model": settings.llm_model,
            "prompt_version": PROMPT_VERSION,
            "logical_step": logical_step,
            "output": serialize_message(response),
            "duration_ms": round((monotonic() - started) * 1000),
            "usage": usage,
            "tool_count": len(getattr(response, "tool_calls", []) or []),
        },
        event_key=f"{event_prefix}:completed",
        run_id=run_id,
        node_name=node_name,
    )
    return response
