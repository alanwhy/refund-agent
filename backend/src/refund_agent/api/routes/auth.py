from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from refund_agent.api.dependencies import DbSession
from refund_agent.api.schemas import LoginRequest, LoginResponse, UserView
from refund_agent.models import User
from refund_agent.security.jwt import create_access_token
from refund_agent.security.passwords import verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: DbSession) -> LoginResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    return LoginResponse(
        access_token=create_access_token(user.id, user.role),
        user=UserView.model_validate(user),
    )
