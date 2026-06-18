"""Programmatic login for YourAI QA (login → ya_premfa → verify-mfa → ya_access)."""

from __future__ import annotations

import base64
import json
import logging
import time
from urllib.parse import urlparse

import requests

from yourai_chat.exceptions import YourAIAuthError
from yourai_pwa.config import PWAConfig
from yourai_pwa.cookie_store import load_cached_cookies, persist_session_cookies

log = logging.getLogger(__name__)

_AUTH_COOKIE_NAMES = frozenset({"ya_access", "ya_refresh", "ya_premfa"})
_TRANSIENT_HTTP = frozenset({408, 502, 503, 504})


def _cookie_value(session: requests.Session, name: str) -> str | None:
    for cookie in session.cookies:
        if cookie.name == name and cookie.value:
            return cookie.value
    return None


def apply_env_cookies(session: requests.Session, config: PWAConfig) -> None:
    """Seed session from .env when ya_access / ya_refresh are prefilled."""
    if not config.has_cookies:
        return
    host = urlparse(config.base_url).hostname or ""
    for name, value in (
        ("ya_access", config.ya_access),
        ("ya_refresh", config.ya_refresh),
    ):
        if value:
            session.cookies.set(name, value, domain=host)


def clear_auth_cookies(session: requests.Session) -> None:
    """Remove PWA auth cookies so a stale session can re-login."""
    for cookie in list(session.cookies):
        if cookie.name in _AUTH_COOKIE_NAMES:
            session.cookies.clear(cookie.domain, cookie.path, cookie.name)


def is_authenticated(session: requests.Session) -> bool:
    return _access_token_valid(session)


def _jwt_exp(token: str) -> float | None:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        exp = data.get("exp")
        return float(exp) if exp is not None else None
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def _access_token_valid(session: requests.Session, *, skew_seconds: int = 60) -> bool:
    token = _cookie_value(session, "ya_access")
    if not token:
        return False
    exp = _jwt_exp(token)
    if exp is None:
        return True
    return time.time() < exp - skew_seconds


def login_with_credentials(session: requests.Session, config: PWAConfig) -> None:
    """
    QA auth flow (app-qa.yourai.com):

      1. POST /auth/login {email, password}  → Set-Cookie: ya_premfa
      2. POST /auth/verify-mfa {code}        → Set-Cookie: ya_access, ya_refresh
    """
    if not config.has_credentials:
        raise YourAIAuthError(
            "No login credentials in .env "
            "(YOURAI_PWA_LOGIN_EMAIL, YOURAI_PWA_LOGIN_PASSWORD, YOURAI_PWA_OTP_BYPASS)."
        )

    root = config.api_root
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    log.info("Logging in as %s …", config.login_email)
    login_resp = session.post(
        f"{root}/auth/login",
        json={"email": config.login_email, "password": config.login_password},
        headers=headers,
        timeout=config.timeout_seconds,
    )
    if login_resp.status_code not in (200, 201):
        hint = ""
        if login_resp.status_code == 401 and "not registered" in login_resp.text.lower():
            hint = (
                " Set YOURAI_PWA_BASE_URL=https://app-qa.yourai.com in .env "
                "to match the QA browser at app-qa.yourai.com."
            )
        raise YourAIAuthError(
            f"login failed HTTP {login_resp.status_code}: {login_resp.text[:200]}{hint}"
        )

    if is_authenticated(session):
        persist_session_cookies(session, config.base_url)
        log.info("Login succeeded without MFA step.")
        return

    if not _cookie_value(session, "ya_premfa"):
        raise YourAIAuthError(
            "login did not set ya_premfa cookie and did not return ya_access. "
            "Check credentials or MFA policy on QA."
        )

    log.info("Verifying MFA …")
    mfa_resp = session.post(
        f"{root}/auth/verify-mfa",
        json={"code": config.login_otp},
        headers=headers,
        timeout=config.timeout_seconds,
    )
    if mfa_resp.status_code not in (200, 201):
        raise YourAIAuthError(
            f"verify-mfa failed HTTP {mfa_resp.status_code}: {mfa_resp.text[:200]}"
        )

    if not is_authenticated(session):
        raise YourAIAuthError(
            "verify-mfa succeeded but ya_access cookie was not set."
        )

    persist_session_cookies(session, config.base_url)
    log.info("Authenticated — ya_access and ya_refresh cookies obtained.")


def refresh_access_token(session: requests.Session, config: PWAConfig) -> bool:
    """POST /auth/refresh using ya_refresh cookie. Returns True if ya_access present."""
    if not _cookie_value(session, "ya_refresh"):
        return False

    root = config.api_root
    resp = session.post(
        f"{root}/auth/refresh",
        headers={"accept": "application/json"},
        timeout=config.timeout_seconds,
    )
    if resp.status_code not in (200, 201):
        log.warning("refresh failed HTTP %s", resp.status_code)
        return False
    if is_authenticated(session):
        persist_session_cookies(session, config.base_url)
    return is_authenticated(session)


def _apply_cached_cookies(session: requests.Session, config: PWAConfig) -> None:
    cached = load_cached_cookies(config.base_url)
    if not cached:
        return
    host = urlparse(config.base_url).hostname or ""
    for name in ("ya_access", "ya_refresh"):
        value = cached.get(name)
        if value:
            session.cookies.set(name, value, domain=host)


def _try_refresh_or_clear(session: requests.Session, config: PWAConfig) -> bool:
    """Refresh when ya_refresh is present; clear stale cookies on failure."""
    if not _cookie_value(session, "ya_refresh"):
        return False
    if refresh_access_token(session, config):
        return True
    clear_auth_cookies(session)
    return False


def ensure_authenticated(session: requests.Session, config: PWAConfig) -> None:
    """Use env/cache cookies, refresh when access expired, or full login."""
    apply_env_cookies(session, config)
    _apply_cached_cookies(session, config)

    if _access_token_valid(session):
        return

    if _try_refresh_or_clear(session, config):
        return

    if config.has_credentials:
        login_with_credentials(session, config)
        return

    raise YourAIAuthError(
        "Not authenticated. Set YOURAI_PWA_LOGIN_* credentials in .env "
        "or paste ya_access / ya_refresh cookies."
    )
