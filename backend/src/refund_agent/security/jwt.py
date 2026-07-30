from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from refund_agent.config import get_settings


def create_access_token(user_id: str, role: str) -> str:
    settings = get_settings()
    expires = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    return str(
        jwt.encode(
            {"sub": user_id, "role": role, "exp": expires},
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
    )


def decode_access_token(token: str) -> dict[str, str]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc
    if not payload.get("sub") or not payload.get("role"):
        raise ValueError("Token is missing identity claims")
    return {"sub": str(payload["sub"]), "role": str(payload["role"])}
