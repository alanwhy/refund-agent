from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from refund_agent.api.routes import approvals, audit, auth, health, tickets
from refund_agent.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_settings().require_model_config()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
    trace_id = request.headers.get("x-trace-id", str(uuid4()))
    try:
        response = await call_next(request)
    except Exception:
        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_ERROR",
                "message": "服务暂时不可用，请稍后重试。",
                "trace_id": trace_id,
            },
        )
    response.headers["x-trace-id"] = trace_id
    return response


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(approvals.router)
app.include_router(audit.router)
