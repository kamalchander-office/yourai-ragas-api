from yourai_pwa.cookie_store import load_cached_cookies, save_cached_cookies


def test_cookie_cache_roundtrip(tmp_path, monkeypatch):
    import yourai_pwa.cookie_store as store

    monkeypatch.setattr(store, "AUTH_CACHE_FILE", tmp_path / ".pwa_auth.json")
    base = "https://app-qa.yourai.com"
    assert load_cached_cookies(base) is None

    save_cached_cookies(base, "access-token", "refresh-token")
    cached = load_cached_cookies(base)
    assert cached == {"ya_access": "access-token", "ya_refresh": "refresh-token"}

    assert load_cached_cookies("https://other.example.com") is None
