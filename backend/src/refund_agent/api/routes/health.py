from fastapi import APIRouter, Response
from redis import Redis
from sqlalchemy import text

from refund_agent.config import get_settings
from refund_agent.infrastructure.database import SessionLocal

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(response: Response) -> dict[str, object]:
    settings = get_settings()
    checks: dict[str, bool] = {
        "database": False,
        "redis": False,
        "model_config": bool(
            settings.llm_base_url and settings.llm_api_key and settings.llm_model
        ),
    }
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass
    try:
        checks["redis"] = bool(Redis.from_url(settings.redis_url).ping())
    except Exception:
        pass
    ok = all(checks.values())
    if not ok:
        response.status_code = 503
    return {"status": "ready" if ok else "not_ready", "checks": checks}
