"""Persist PWA auth cookies between runs (qa/.pwa_auth.json)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

AUTH_CACHE_FILE = Path(__file__).resolve().parent.parent / "qa" / ".pwa_auth.json"


def load_cached_cookies(base_url: str) -> dict[str, str] | None:
    """Return ya_access/ya_refresh when cache exists for the same base_url."""
    if not AUTH_CACHE_FILE.is_file():
        return None
    try:
        payload = json.loads(AUTH_CACHE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    if (payload.get("base_url") or "").rstrip("/") != base_url.rstrip("/"):
        return None

    ya_access = (payload.get("ya_access") or "").strip()
    ya_refresh = (payload.get("ya_refresh") or "").strip()
    if not ya_access or not ya_refresh:
        return None
    return {"ya_access": ya_access, "ya_refresh": ya_refresh}


def save_cached_cookies(base_url: str, ya_access: str, ya_refresh: str) -> Path:
    payload = {
        "base_url": base_url.rstrip("/"),
        "ya_access": ya_access,
        "ya_refresh": ya_refresh,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    AUTH_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_CACHE_FILE.write_text(json.dumps(payload, indent=2))
    return AUTH_CACHE_FILE


def persist_session_cookies(session, base_url: str) -> None:
    """Write ya_access/ya_refresh from a requests session to the cache file."""
    cookies = {c.name: c.value for c in session.cookies if c.value}
    ya_access = cookies.get("ya_access", "").strip()
    ya_refresh = cookies.get("ya_refresh", "").strip()
    if ya_access and ya_refresh:
        save_cached_cookies(base_url, ya_access, ya_refresh)
