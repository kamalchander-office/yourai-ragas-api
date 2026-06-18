"""
Test PWA API login (no browser).

  python qa/pwa_login.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from yourai_pwa.client import YourAIPWAClient
from yourai_pwa.cookie_store import AUTH_CACHE_FILE
from yourai_pwa.config import load_pwa_config


def main() -> None:
    cfg = load_pwa_config()
    client = YourAIPWAClient(cfg)
    me = client.auth_me()
    print("✓ Login OK")
    print(f"  base_url : {client.config.base_url}")
    if AUTH_CACHE_FILE.is_file():
        print(f"  cookies  : cached → {AUTH_CACHE_FILE.resolve()}")
    print(f"  user     : {me.get('email') or me.get('id')}")
    print(f"  org      : {me.get('organizationId') or me.get('orgId') or me.get('org')}")
    print(f"  role     : {me.get('role')}")


if __name__ == "__main__":
    main()
