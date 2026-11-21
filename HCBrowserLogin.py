"""Capture the hcauth:// redirect of the Home Connect login in a local browser.

The SingleKey ID login only redirects to hcauth://auth/prod, which a normal browser
cannot open, so the code and state used to be copied out of the developer tools by
hand. Here a Chromium-based browser is started with its DevTools protocol enabled
and the redirect is read from its network events instead. The user still signs in
(and solves the CAPTCHA) on the real login page in their own browser.
"""

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from urllib.parse import parse_qs, urlparse

BROWSER_NAMES = [
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
    "brave-browser",
]

MAC_BROWSERS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
]

WINDOWS_BROWSERS = [
    r"Google\Chrome\Application\chrome.exe",
    r"Microsoft\Edge\Application\msedge.exe",
    r"Chromium\Application\chrome.exe",
]


def find_browser(explicit=None):
    """Return the path of a Chromium-based browser, or None if none is found."""
    if explicit and explicit != "auto":
        return explicit
    for name in BROWSER_NAMES:
        path = shutil.which(name)
        if path:
            return path
    if platform.system() == "Darwin":
        for path in MAC_BROWSERS:
            if os.path.exists(path):
                return path
    if platform.system() == "Windows":
        roots = [os.environ.get(v) for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        for root in filter(None, roots):
            for rel in WINDOWS_BROWSERS:
                path = os.path.join(root, rel)
                if os.path.exists(path):
                    return path
    return None


def hcauth_from_event(message):
    """Return the hcauth:// URL from a DevTools protocol event, if it carries one."""
    params = message.get("params", {})
    headers = params.get("redirectResponse", {}).get("headers", {})
    candidates = [
        params.get("request", {}).get("url", ""),
        params.get("url", ""),
        headers.get("location", ""),
        headers.get("Location", ""),
    ]
    for url in candidates:
        if url.startswith("hcauth://"):
            return url
    return None


def code_and_state(hcauth_url):
    """Split an hcauth:// redirect into its code and state.

    The code is returned exactly as it appears in the URL (still percent-encoded),
    which is what hc-login.py expects from manual input.
    """
    code = re.search(r"[?&]code=([^&]*)", hcauth_url)
    state = parse_qs(urlparse(hcauth_url).query).get("state", [""])[0]
    if not code or not state:
        raise ValueError("No code or state in redirect: " + hcauth_url)
    return code.group(1), state


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def capture_hcauth(login_url, browser=None, timeout=600):
    """Open login_url in a fresh browser profile and wait for the hcauth:// redirect.

    Returns the redirect URL. Raises RuntimeError when no browser is found, the
    browser cannot be reached, or the login is not completed within timeout seconds.
    """
    import websocket  # websocket-client, already a dependency of hcpy

    path = find_browser(browser)
    if not path:
        raise RuntimeError(
            "No Chrome, Chromium, Edge or Brave found. Pass its path with --browser PATH."
        )

    port = _free_port()
    profile = tempfile.mkdtemp(prefix="hc-login-")
    proc = subprocess.Popen(
        [
            path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            login_url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        target = None
        for _ in range(60):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json") as r:
                    pages = json.load(r)
                target = next((p for p in pages if p.get("type") == "page"), None)
            except OSError:
                continue
            if target:
                break
        if not target:
            raise RuntimeError("Could not connect to the browser's DevTools port")

        # suppress_origin: newer Chrome rejects DevTools connections that send an Origin.
        ws = websocket.create_connection(target["webSocketDebuggerUrl"], suppress_origin=True)
        try:
            ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
            ws.send(json.dumps({"id": 2, "method": "Page.enable"}))
            deadline = time.time() + timeout
            while time.time() < deadline:
                ws.settimeout(5)
                try:
                    message = json.loads(ws.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                url = hcauth_from_event(message)
                if url:
                    return url
        finally:
            ws.close()
        raise RuntimeError(f"Login was not completed within {timeout} seconds")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)
