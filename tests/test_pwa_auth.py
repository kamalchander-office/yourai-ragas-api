import time

from yourai_pwa.auth import _access_token_valid, _jwt_exp


def test_jwt_exp_decodes():
    # exp in year 2030
    payload = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0IiwiZXhwIjoxOTAwMDAwMDAwfQ.sig"
    assert _jwt_exp(payload) == 1900000000.0


def test_access_token_valid_when_not_expired():
    import requests

    session = requests.Session()
    payload = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0IiwiZXhwIjoxOTAwMDAwMDAwfQ.sig"
    session.cookies.set("ya_access", payload, domain="example.com")
    assert _access_token_valid(session) is True


def test_access_token_invalid_when_expired():
    import requests

    session = requests.Session()
    payload = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0IiwiZXhwIjoxfQ.sig"
    session.cookies.set("ya_access", payload, domain="example.com")
    assert _access_token_valid(session) is False
