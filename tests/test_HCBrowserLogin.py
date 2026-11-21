import pytest

import HCBrowserLogin
from HCBrowserLogin import code_and_state, find_browser, hcauth_from_event

REDIRECT = "hcauth://auth/prod?code=eyJabc%3D&grant_type=authorization_code&state=c1pfc2tW"


def test_code_and_state_keeps_code_encoded():
    code, state = code_and_state(REDIRECT)
    assert code == "eyJabc%3D"
    assert state == "c1pfc2tW"


def test_code_and_state_rejects_redirect_without_code():
    with pytest.raises(ValueError):
        code_and_state("hcauth://auth/prod?error=access_denied&state=c1pfc2tW")


def test_hcauth_from_request_event():
    message = {"method": "Network.requestWillBeSent", "params": {"request": {"url": REDIRECT}}}
    assert hcauth_from_event(message) == REDIRECT


def test_hcauth_from_redirect_location():
    message = {
        "method": "Network.requestWillBeSent",
        "params": {
            "request": {"url": "hcauth://ignored-if-not-first"},
            "redirectResponse": {"headers": {"location": REDIRECT}},
        },
    }
    assert hcauth_from_event(message).startswith("hcauth://")


def test_hcauth_from_navigation_event():
    message = {"method": "Page.frameRequestedNavigation", "params": {"url": REDIRECT}}
    assert hcauth_from_event(message) == REDIRECT


def test_hcauth_ignores_other_events():
    message = {
        "method": "Network.requestWillBeSent",
        "params": {"request": {"url": "https://singlekey-id.com/auth/login"}},
    }
    assert hcauth_from_event(message) is None
    assert hcauth_from_event({"id": 1, "result": {}}) is None


def test_find_browser_uses_explicit_path():
    assert find_browser("/opt/chrome/chrome") == "/opt/chrome/chrome"


def test_find_browser_searches_path(monkeypatch):
    monkeypatch.setattr(
        HCBrowserLogin.shutil,
        "which",
        lambda name: "/usr/bin/chromium" if name == "chromium" else None,
    )
    assert find_browser("auto") == "/usr/bin/chromium"


def test_find_browser_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(HCBrowserLogin.shutil, "which", lambda name: None)
    monkeypatch.setattr(HCBrowserLogin.platform, "system", lambda: "Linux")
    assert find_browser() is None
