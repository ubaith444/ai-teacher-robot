"""
app/core/security.py
────────────────────
Authentication helpers for Zoro Robot Attendance System:

  • bcrypt password hashing via passlib
  • JWT creation + verification via python-jose
  • FastAPI dependency for protected routes (Bearer token)
  • Optional X-API-Key middleware for robot clients
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

log = structlog.get_logger(__name__)

# ── Password hashing ──────────────────────────────────────────────────────────
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return bcrypt hash of *plain*. Use when storing a new password."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*."""
    return _pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────
_BEARER = HTTPBearer(auto_error=True)


def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[dict] = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        subject:      The user identifier (username / UUID) to embed as 'sub'.
        expires_delta: Custom lifetime; defaults to ACCESS_TOKEN_EXPIRE_MINUTES.
        extra_claims: Additional claims to merge into the payload.

    Returns:
        Encoded JWT string.
    """
    expire = datetime.now(tz=timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(tz=timezone.utc),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> str:
    """
    Decode and validate a JWT token.

    Returns:
        The `sub` claim (user identifier).

    Raises:
        HTTPException 401 if the token is invalid or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        sub: str | None = payload.get("sub")
        if sub is None:
            raise credentials_exception
        return sub
    except JWTError as exc:
        log.warning("security.jwt_decode_failed", error=str(exc))
        raise credentials_exception from exc


# ── FastAPI dependencies ───────────────────────────────────────────────────────
# Authentication is DISABLED — all routes are open.
# Replace the bodies below to re-enable auth.


async def get_current_user() -> str:
    """No-op auth dependency — always returns 'anonymous'."""
    return "anonymous"


# ── Optional static API-key (robot clients) ───────────────────────────────────
_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def check_api_key(
    api_key: Optional[str] = Security(_API_KEY_HEADER),
) -> None:
    """No-op — API-key enforcement disabled."""
    return


def require_role(allowed_roles: list[str]):
    """No-op — role enforcement disabled."""

    async def _check() -> str:
        return "anonymous"

    return _check


"""
Zoro AI Robot - Security utilities
Optional API key guard for REST endpoints.
"""

from fastapi import Security
from fastapi.security.api_key import APIKeyHeader

api_key_header = APIKeyHeader(name=settings.API_KEY_HEADER, auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Validate the API key if one is configured.
    If API_KEY is empty string, auth is disabled (dev mode).
    """
    if not settings.API_KEY:
        return "dev"
    if api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key.",
        )
    return api_key

