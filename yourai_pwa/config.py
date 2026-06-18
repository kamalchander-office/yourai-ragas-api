"""Configuration for YourAI PWA QA environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

# QA PWA host (browser: https://app-qa.yourai.com/chat)
DEFAULT_QA_BASE_URL = "https://app-qa.yourai.com"


@dataclass(frozen=True)
class PWAConfig:
    base_url: str
    login_email: str
    login_password: str
    login_otp: str
    ya_access: str
    ya_refresh: str
    timeout_seconds: float
    poll_interval_seconds: float
    poll_max_attempts: int
    default_retrieval_mode: str

    @property
    def api_root(self) -> str:
        return f"{self.base_url.rstrip('/')}/api/v1"

    @property
    def has_credentials(self) -> bool:
        return bool(self.login_email and self.login_password and self.login_otp)

    @property
    def has_cookies(self) -> bool:
        return bool(self.ya_access and self.ya_refresh)


def load_pwa_config() -> PWAConfig:
    """
    Auth: either login credentials (recommended) or prefilled ya_access/ya_refresh cookies.
    """
    base_url = (os.getenv("YOURAI_PWA_BASE_URL") or DEFAULT_QA_BASE_URL).strip()
    login_email = (os.getenv("YOURAI_PWA_LOGIN_EMAIL") or "").strip()
    login_password = (os.getenv("YOURAI_PWA_LOGIN_PASSWORD") or "").strip()
    login_otp = (os.getenv("YOURAI_PWA_OTP_BYPASS") or os.getenv("YOURAI_PWA_LOGIN_OTP") or "").strip()
    ya_access = (os.getenv("YOURAI_PWA_YA_ACCESS") or "").strip()
    ya_refresh = (os.getenv("YOURAI_PWA_YA_REFRESH") or "").strip()

    cfg = PWAConfig(
        base_url=base_url,
        login_email=login_email,
        login_password=login_password,
        login_otp=login_otp,
        ya_access=ya_access,
        ya_refresh=ya_refresh,
        timeout_seconds=float(os.getenv("YOURAI_PWA_TIMEOUT_SECONDS", "120")),
        poll_interval_seconds=float(os.getenv("YOURAI_PWA_POLL_INTERVAL", "2")),
        poll_max_attempts=int(os.getenv("YOURAI_PWA_POLL_MAX_ATTEMPTS", "90")),
        default_retrieval_mode=os.getenv("DEFAULT_RETRIEVAL_MODE", "hybrid"),
    )

    if not cfg.has_credentials and not cfg.has_cookies:
        raise RuntimeError(
            "PWA auth not configured. Add to .env either:\n"
            "  YOURAI_PWA_LOGIN_EMAIL / YOURAI_PWA_LOGIN_PASSWORD / YOURAI_PWA_OTP_BYPASS\n"
            "or:\n"
            "  YOURAI_PWA_YA_ACCESS / YOURAI_PWA_YA_REFRESH (manual cookies)"
        )
    return cfg
