"""
app/api/endpoints/auth.py
─────────────────────────
Authentication routes for Zoro Robot System.

Exposes:
  POST /auth/token  — OAuth2 compatible token endpoint.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.security import create_access_token, verify_password
from app.core.database import get_db
from app.models.models import User
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/token", summary="Login to get access token.")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db)
):
    """
    Standard OAuth2 /token endpoint.
    Checks username/password against the 'users' table.
    Returns a JWT access token.
    """
    # 1. Fetch user
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()

    # 2. Verify (simple check for demo if users table is empty or specific logic needed)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Create token
    access_token = create_access_token(subject=user.username, extra_claims={"role": user.role})
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

