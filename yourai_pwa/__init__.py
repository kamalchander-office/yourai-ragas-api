"""YourAI PWA (QA) API client — cookie auth, vault upload, scoped chat."""

from yourai_pwa.auth import ensure_authenticated, login_with_credentials
from yourai_pwa.bootstrap import bootstrap_qa_session
from yourai_pwa.client import YourAIPWAClient
from yourai_pwa.config import PWAConfig, load_pwa_config

__all__ = [
    "PWAConfig",
    "YourAIPWAClient",
    "bootstrap_qa_session",
    "ensure_authenticated",
    "load_pwa_config",
    "login_with_credentials",
]
