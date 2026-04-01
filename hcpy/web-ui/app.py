#!/usr/bin/env python3
"""Flask Web-UI for HomeConnect2MQTT addon setup."""
import json
import importlib.util
import logging
import os
import re
import subprocess
import sys
import time as _time
from base64 import urlsafe_b64encode as base64url_encode
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import requests as req
from Crypto.Hash import SHA256
from Crypto.Random import get_random_bytes
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# Configuration from environment
CONFIG_DIR = os.environ.get("HCPY_CONFIG_DIR", "/config")
DEVICES_FILE = os.environ.get("HCPY_DEVICES_FILE", os.path.join(CONFIG_DIR, "devices.json"))
INGRESS_PORT = int(os.environ.get("INGRESS_PORT", 8099))
INGRESS_PATH = os.environ.get("INGRESS_PATH", "")
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

# OAuth constants (same as hc-login.py)
APP_ID = "9B75AC9EC512F36C84256AC47D813E2C1DD0D6520DF774B020E1E6E2EB29B1F3"
BASE_URL = "https://api.home-connect.com/security/oauth/"
ASSET_URLS = [
    "https://prod.reu.rest.homeconnectegw.com/",
    "https://prod.rna.rest.homeconnectegw.com/",
]
TOKEN_FILE = "/data/tokens.json"

# Store active login session (verifier needed for token exchange)
_login_session = {}


def b64(b):
    return re.sub(r"=", "", base64url_encode(b).decode("UTF-8"))


def parse_hcauth_url(raw):
    """Parse hcauth URL, redirect_target URL, nested returnUrl, query string, or raw code."""

    def _extract(candidate):
        candidate = (candidate or "").strip()
        if not candidate:
            return None, None

        # Direct query string or URL with query params.
        if "code=" in candidate or "state=" in candidate:
            params = parse_qs(candidate.split("?", 1)[-1] if "?" in candidate else candidate)
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]
            if code:
                return code, state

        # SingleKey-style wrapper: ...?returnUrl=<encoded-url-or-path>
        try:
            parsed = urlparse(candidate)
            params = parse_qs(parsed.query)
            if "returnUrl" in params:
                nested = unquote(params["returnUrl"][0])
                code, state = _extract(nested)
                if code:
                    return code, state
        except Exception:
            pass

        # Last-resort: URL-decoded text may expose code=...
        decoded = unquote(candidate)
        if decoded != candidate:
            return _extract(decoded)

        return None, None

    raw = raw.strip()
    if not raw:
        return None, None

    code, state = _extract(raw)
    if code:
        return code, state
    return None, None


def get_status():
    """Get current addon status."""
    status = {
        "devices_configured": False,
        "devices_count": 0,
        "devices": [],
        "mqtt_host": os.environ.get("HCPY_MQTT_HOST", ""),
        "mqtt_port": os.environ.get("HCPY_MQTT_PORT", ""),
        "mqtt_auto": os.environ.get("HCPY_MQTT_AUTO", "false") == "true",
    }

    if os.path.exists(DEVICES_FILE):
        try:
            with open(DEVICES_FILE) as f:
                devices = json.load(f)
            if devices:
                status["devices_configured"] = True
                status["devices_count"] = len(devices)
                status["devices"] = [
                    {"name": d.get("name", "?"), "host": d.get("host", "?")}
                    for d in devices
                ]
        except (json.JSONDecodeError, IOError):
            pass

    return status


def fetch_and_save_devices(token):
    """Fetch devices from HC cloud and save to devices.json (reuses hc-login.py logic)."""
    # Import robustly even if PYTHONPATH is not propagated as expected.
    try:
        from HCxml2json import xml2json
    except ModuleNotFoundError:
        module_path = "/app/HCxml2json.py"
        spec = importlib.util.spec_from_file_location("HCxml2json", module_path)
        if spec is None or spec.loader is None:
            raise
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        xml2json = mod.xml2json
    import io
    from zipfile import ZipFile

    headers = {"Authorization": "Bearer " + token}

    # Find working asset URL
    asset_url = None
    account = None
    for url in ASSET_URLS:
        r = req.get(url + "account/details", headers=headers)
        if r.status_code == 200:
            asset_url = url
            account = r.json()
            break

    if not account:
        return False, "Konnte Account-Details nicht abrufen"

    configs = []
    for appliance in account.get("data", {}).get("homeAppliances", []):
        config = {"name": appliance["type"].lower()}

        if "tls" in appliance:
            config["host"] = f"{appliance['brand']}-{appliance['type']}-{appliance['identifier']}"
            config["key"] = appliance["tls"]["key"]
        else:
            config["host"] = appliance["identifier"]
            config["key"] = appliance["aes"]["key"]
            config["iv"] = appliance["aes"]["iv"]

        # Fetch device XML
        app_url = f"{asset_url}api/iddf/v1/iddf/{appliance['identifier']}"
        r = req.get(app_url, headers=headers)
        if r.status_code == 200:
            z = ZipFile(io.BytesIO(r.content))
            aid = appliance["identifier"]
            features = z.open(f"{aid}_FeatureMapping.xml").read()
            description = z.open(f"{aid}_DeviceDescription.xml").read()
            machine = xml2json(features, description)
            config["description"] = machine["description"]
            config["features"] = machine["features"]

        configs.append(config)

    if not configs:
        return False, "Keine Geraete im Account gefunden"

    # Merge with existing devices.json
    existing = []
    if os.path.exists(DEVICES_FILE):
        try:
            with open(DEVICES_FILE) as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            existing = []

    existing_by_name = {d["name"]: d for d in existing}
    merged = []
    for new_dev in configs:
        name = new_dev["name"]
        if name in existing_by_name:
            old_host = existing_by_name[name].get("host", "")
            if old_host and old_host != new_dev.get("host", ""):
                new_dev["host"] = old_host
        merged.append(new_dev)

    # Keep devices not in new list
    new_names = {d["name"] for d in configs}
    for old_dev in existing:
        if old_dev["name"] not in new_names:
            merged.append(old_dev)

    with open(DEVICES_FILE, "w") as f:
        json.dump(merged, f, ensure_ascii=True, indent=4)

    return True, len(merged)


@app.route("/")
def index():
    return render_template("index.html", status=get_status(), ingress=INGRESS_PATH)


@app.route("/api/status")
def api_status():
    return jsonify(get_status())


@app.route("/api/token-status")
def token_status():
    if not os.path.exists(TOKEN_FILE):
        return jsonify({"has_token": False})
    try:
        with open(TOKEN_FILE) as f:
            data = json.load(f)
        return jsonify({
            "has_token": bool(data.get("refresh_token")),
            "saved_at": data.get("saved_at", 0),
            "expires_at": data.get("expires_at", 0),
            "expired": data.get("expires_at", 0) < int(_time.time()),
        })
    except Exception:
        return jsonify({"has_token": False})


@app.route("/api/logs")
def api_logs():
    n = request.args.get("n", 100, type=int)
    n = min(n, 500)
    log_lines = []
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if token:
        try:
            import urllib.request

            req_obj = urllib.request.Request(
                "http://supervisor/addons/self/logs",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req_obj, timeout=10) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                log_lines = raw.strip().split("\n")[-n:]
        except Exception:
            pass
    if not log_lines:
        log_file = "/data/hcpy.log"
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    log_lines = f.readlines()[-n:]
            except Exception:
                log_lines = ["Log nicht verfuegbar"]
    return jsonify({"lines": log_lines, "count": len(log_lines)})


@app.route("/api/start-login", methods=["POST"])
def start_login():
    """Generate OAuth URL with PKCE - no subprocess, direct generation."""
    global _login_session
    try:
        verifier = b64(get_random_bytes(32))
        challenge = b64(SHA256.new(verifier.encode("UTF-8")).digest())
        nonce = b64(base64url_encode(get_random_bytes(16)))
        state = b64(base64url_encode(get_random_bytes(16)))

        login_query = {
            "response_type": "code",
            "prompt": "login",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "client_id": APP_ID,
            "scope": "ReadOrigApi",
            "nonce": nonce,
            "state": state,
            "redirect_uri": "hcauth://auth/prod",
        }

        url = BASE_URL + "authorize?" + urlencode(login_query)

        # Store verifier for token exchange later
        _login_session = {
            "verifier": verifier,
            "redirect_uri": "hcauth://auth/prod",
        }

        return jsonify({"success": True, "url": url})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/complete-login", methods=["POST"])
def complete_login():
    """Exchange code for token, fetch devices."""
    global _login_session
    data = request.get_json()
    raw_url = data.get("url", "")

    code, state = parse_hcauth_url(raw_url)
    if not code:
        return jsonify(
            {
                "success": False,
                "error": (
                    "Kein authorization code gefunden. Bitte den finalen Redirect nach dem Login "
                    "kopieren (URL muss 'code=' enthalten, z.B. .../redirect_target?code=...)."
                ),
            }
        ), 400

    if not _login_session.get("verifier"):
        return jsonify({"success": False, "error": "Keine aktive Login-Session. Bitte erneut starten."}), 400

    try:
        # Exchange code for token
        token_fields = {
            "grant_type": "authorization_code",
            "client_id": APP_ID,
            "code_verifier": _login_session["verifier"],
            "code": code,
            "redirect_uri": _login_session["redirect_uri"],
        }

        r = req.post(BASE_URL + "token", data=token_fields, allow_redirects=False, timeout=30)
        if r.status_code != 200:
            return jsonify({"success": False, "error": f"Token-Exchange fehlgeschlagen (HTTP {r.status_code}): {r.text[:300]}"}), 500

        token_response = r.json()
        token = token_response["access_token"]

        # Save token for future refresh
        token_data = {
            "access_token": token,
            "refresh_token": token_response.get("refresh_token", ""),
            "expires_at": int(_time.time()) + token_response.get("expires_in", 86400),
            "saved_at": int(_time.time()),
        }
        try:
            with open(TOKEN_FILE, "w") as tf:
                json.dump(token_data, tf, indent=2)
        except Exception:
            pass

        # Fetch devices
        success, result = fetch_and_save_devices(token)
        if not success:
            return jsonify({"success": False, "error": result}), 500

        # Run host resolution
        if os.environ.get("HCPY_AUTO_RESOLVE_HOSTS", "true").lower() == "true":
            try:
                subprocess.run(
                    [sys.executable, "/app/scripts/resolve_hosts.py",
                     DEVICES_FILE, os.environ.get("HCPY_DOMAIN_SUFFIX", "")],
                    timeout=30, capture_output=True,
                )
            except Exception:
                pass

        _login_session = {}
        return jsonify({"success": True, "message": f"{result} Geraet(e) erfolgreich konfiguriert!"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/refresh-devices", methods=["POST"])
def refresh_devices():
    try:
        result = subprocess.run(
            [sys.executable, "/app/hc-login.py", DEVICES_FILE],
            capture_output=True,
            text=True,
            timeout=60,
            input="\n\n",
        )
        if result.returncode == 0 and os.path.exists(DEVICES_FILE):
            with open(DEVICES_FILE) as f:
                n = len(json.load(f))
            if os.environ.get("HCPY_AUTO_RESOLVE_HOSTS", "true").lower() == "true":
                try:
                    subprocess.run(
                        [
                            sys.executable,
                            "/app/scripts/resolve_hosts.py",
                            DEVICES_FILE,
                            os.environ.get("HCPY_DOMAIN_SUFFIX", ""),
                        ],
                        timeout=30,
                        capture_output=True,
                    )
                except Exception:
                    pass
            return jsonify(
                {
                    "success": True,
                    "message": f"{n} Geraet(e) aktualisiert!",
                    "login_required": False,
                }
            )
        return jsonify(
            {
                "success": False,
                "login_required": True,
                "message": "Token abgelaufen - bitte erneut anmelden.",
            }
        )
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Timeout"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/restart-addon", methods=["POST"])
def restart_addon():
    if not SUPERVISOR_TOKEN:
        return jsonify({"success": False, "error": "Kein SUPERVISOR_TOKEN verfuegbar"}), 500
    try:
        r = req.post(
            "http://supervisor/addons/self/restart",
            headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
            timeout=10,
        )
        return jsonify({"success": r.status_code == 200})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=INGRESS_PORT, debug=False)
