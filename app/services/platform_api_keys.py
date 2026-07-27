import hashlib
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ApiKey, User

ALLOWED_SCOPES = {"projects:read", "presets:read", "generations:create", "generations:read", "assets:read"}
_rate_limit_lock = threading.Lock()
_rate_limit_records: dict[str, deque[float]] = defaultdict(deque)


@dataclass(frozen=True)
class ApiKeyActor:
    key: ApiKey
    user: User


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def create_key(db: Session, *, workspace_id: str, project_id: str | None, name: str, scopes: list[str], created_by: str) -> tuple[str, ApiKey]:
    invalid_scopes = set(scopes) - ALLOWED_SCOPES
    if invalid_scopes or not scopes:
        raise ValueError("invalid API key scopes")
    raw_key = f"mpt_{secrets.token_urlsafe(32)}"
    key = ApiKey(
        workspace_id=workspace_id, project_id=project_id, name=name.strip(),
        key_prefix=raw_key[:12], key_hash=hash_key(raw_key), scopes=scopes,
        created_by=created_by,
    )
    db.add(key)
    return raw_key, key


def get_api_key_actor(request: Request, db: Session) -> ApiKeyActor:
    provided = request.headers.get("x-api-key", "").strip()
    if not provided:
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            provided = authorization[7:].strip()
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_key(provided))) if provided else None
    now = datetime.now(timezone.utc)
    expires_at = key.expires_at if key else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if key is None or key.revoked_at is not None or (expires_at and expires_at <= now):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
    user = db.get(User, key.created_by)
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
    key.last_used_at = now
    return ApiKeyActor(key=key, user=user)


def require_scope(actor: ApiKeyActor, scope: str) -> None:
    if scope not in actor.key.scopes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key scope denied")


def enforce_rate_limit(actor: ApiKeyActor) -> None:
    """Apply a per-key burst limit before accepting automation work."""

    limit = max(1, int(os.getenv("MPT_API_KEY_RATE_LIMIT_PER_MINUTE", "60")))
    now = time.monotonic()
    with _rate_limit_lock:
        records = _rate_limit_records[actor.key.id]
        while records and records[0] <= now - 60:
            records.popleft()
        if len(records) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="API key rate limit exceeded",
            )
        records.append(now)
