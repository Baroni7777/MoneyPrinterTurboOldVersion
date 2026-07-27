import hashlib
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database.models import (
    AuditLog,
    User,
    UserSession,
    Workspace,
    WorkspaceMembership,
)
from app.platform.settings import get_auth_settings

_password_hasher = PasswordHasher()
_dummy_password_hash = _password_hasher.hash(secrets.token_urlsafe(32))


def normalize_email(email: str) -> str:
    normalized = (email or "").strip().casefold()
    if (
        len(normalized) > 320
        or normalized.count("@") != 1
        or normalized.startswith("@")
        or normalized.endswith("@")
    ):
        raise ValueError("invalid email")
    return normalized


def validate_password(password: str) -> None:
    settings = get_auth_settings()
    if len(password or "") < settings.password_min_length:
        raise ValueError(
            f"password must have at least {settings.password_min_length} characters"
        )
    if len(password) > 1024:
        raise ValueError("password is too long")


def hash_password(password: str) -> str:
    validate_password(password)
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return bool(_password_hasher.verify(password_hash, password))
    except (VerificationError, InvalidHashError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode(
        "ascii", "ignore"
    ).decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")
    return slug[:120] or "workspace"


def create_user_with_workspace(
    db: Session,
    *,
    email: str,
    password: str,
    display_name: str,
    system_role: str = "user",
    status: str = "active",
) -> User:
    normalized_email = normalize_email(email)
    if db.scalar(select(User.id).where(User.email == normalized_email)):
        raise ValueError("email already registered")
    if system_role not in {"admin", "user"}:
        raise ValueError("invalid system role")

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        system_role=system_role,
        status=status,
    )
    suffix = secrets.token_hex(3)
    workspace = Workspace(
        name=f"{display_name.strip()} workspace",
        slug=f"{_slugify(display_name)}-{suffix}",
    )
    db.add(
        WorkspaceMembership(user=user, workspace=workspace, role="owner")
    )
    db.flush()
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    try:
        normalized_email = normalize_email(email)
    except ValueError:
        verify_password(_dummy_password_hash, password)
        return None
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None:
        verify_password(_dummy_password_hash, password)
        return None
    if not verify_password(user.password_hash, password) or user.status != "active":
        return None
    if _password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = _password_hasher.hash(password)
    user.last_login_at = datetime.now(timezone.utc)
    return user


def create_user_session(
    db: Session, user: User, ip_address: str | None, user_agent: str | None
) -> tuple[str, UserSession]:
    settings = get_auth_settings()
    raw_token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    user_session = UserSession(
        user_id=user.id,
        token_hash=token_hash(raw_token),
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        last_seen_at=now,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:512] or None,
    )
    db.add(user_session)
    return raw_token, user_session


def resolve_session(db: Session, raw_token: str | None) -> User | None:
    if not raw_token:
        return None
    user_session = db.scalar(
        select(UserSession).where(UserSession.token_hash == token_hash(raw_token))
    )
    if user_session is None or user_session.revoked_at is not None:
        return None
    now = datetime.now(timezone.utc)
    expires_at = user_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now or user_session.user.status != "active":
        return None
    user_session.last_seen_at = now
    return user_session.user


def revoke_session(db: Session, raw_token: str | None) -> None:
    if raw_token:
        db.execute(
            update(UserSession)
            .where(
                UserSession.token_hash == token_hash(raw_token),
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )


def revoke_all_user_sessions(db: Session, user_id: str) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )


def audit(
    db: Session,
    action: str,
    resource_type: str,
    resource_id: str | None,
    actor_user_id: str | None,
    workspace_id: str | None = None,
) -> None:
    db.add(
        AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
        )
    )
