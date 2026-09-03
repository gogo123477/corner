"""Bearer-token auth. Two modes:

- dev:  `Authorization: Bearer dev:<anything>` → user with auth_ref "dev:<anything>" (auto-created).
- jwt:  HS256 JWT from a managed auth provider (Supabase Auth by default) — `sub` is the auth_ref.

The API never handles passwords. Swap the JWT verification for JWKS if the provider uses RS256.
"""

from __future__ import annotations

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
    )


def resolve_auth_ref(token: str, settings: Settings) -> str:
    if settings.auth_mode == "dev":
        if not token.startswith("dev:") or len(token) < 5:
            raise _unauthorized("dev mode expects a token of the form dev:<user>")
        return token
    if not settings.jwt_secret:
        raise HTTPException(500, "CORNER_JWT_SECRET is not configured")
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized(f"invalid token: {exc}") from exc
    return str(claims["sub"])


def get_or_create_user(db: Session, auth_ref: str) -> User:
    user = db.scalar(select(User).where(User.auth_ref == auth_ref))
    if user is None:
        user = User(auth_ref=auth_ref)
        db.add(user)
        db.commit()
    return user


def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("missing bearer token")
    auth_ref = resolve_auth_ref(authorization.split(" ", 1)[1].strip(), settings)
    return get_or_create_user(db, auth_ref)
