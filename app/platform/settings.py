import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AuthSettings:
    cookie_name: str
    cookie_secure: bool
    cookie_samesite: str
    cookie_domain: str | None
    session_ttl_hours: int
    password_min_length: int


def get_auth_settings() -> AuthSettings:
    same_site = os.getenv("MPT_AUTH_COOKIE_SAMESITE", "lax").lower()
    if same_site not in {"lax", "strict", "none"}:
        same_site = "lax"
    return AuthSettings(
        cookie_name=os.getenv("MPT_AUTH_COOKIE_NAME", "mpt_session"),
        cookie_secure=_as_bool(os.getenv("MPT_AUTH_COOKIE_SECURE"), False),
        cookie_samesite=same_site,
        cookie_domain=os.getenv("MPT_AUTH_COOKIE_DOMAIN") or None,
        session_ttl_hours=max(
            1, int(os.getenv("MPT_AUTH_SESSION_TTL_HOURS", "168"))
        ),
        password_min_length=max(
            10, int(os.getenv("MPT_AUTH_PASSWORD_MIN_LENGTH", "12"))
        ),
    )
