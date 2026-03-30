#!/usr/bin/env python3
"""Flask Web-UI for HomeConnect2MQTT addon setup."""
import json
import os
import re
import subprocess
import sys
import time as _time
from base64 import urlsafe_b64encode as base64url_encode
from urllib.parse import parse_qs, urlencode, urlparse

import requests as req
from Crypto.Hash import SHA256
from Crypto.Random import get_random_bytes
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

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
    """Parse hcauth:// URL, query string, or raw code from user."""
    raw = raw.strip()
    if not raw:
        return None, None

    if raw.startswith("hcauth://"):
        parsed = urlparse(raw)
        params = parse_qs(parsed.query)
        return params.get("code", [None])[0], params.get("state", [None])[0]

    if "code=" in raw:
        params = parse_qs(raw.split("?")[-1] if "?" in raw else raw)
        return params.get("code", [None])[0], params.get("state", [None])[0]

    return raw, None


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
    # Import from hc-login.py
    sys.path.insert(0, "/app")
    from HCxml2json import xml2json
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
        return False, "Keine Geräte im Account gefunden"

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


@app.route("/api/start-login", methods=["POST"])
def start_login():
    """Generate OAuth URL with PKCE — no subprocess, direct generation."""
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
        return jsonify({"success": False, "error": "Kein Code in der URL gefunden"}), 400

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
        return jsonify({"success": True, "message": f"{result} Gerät(e) erfolgreich konfiguriert!"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/refresh-devices", methods=["POST"])
def refresh_devices():
    """Refresh devices using stored token — no browser login needed."""
    if not os.path.exists(TOKEN_FILE):
        return jsonify({"success": False, "login_required": True, "message": "Kein Token gespeichert — bitte anmelden."})

    try:
        with open(TOKEN_FILE) as f:
            stored = json.load(f)
    except (json.JSONDecodeError, IOError):
        return jsonify({"success": False, "login_required": True, "message": "Token-Datei beschädigt — bitte erneut anmelden."})

    refresh_token = stored.get("refresh_token", "")
    if not refresh_token:
        return jsonify({"success": False, "login_required": True, "message": "Kein Refresh-Token — bitte erneut anmelden."})

    try:
        # Try token refresh
        r = req.post(BASE_URL + "token", data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }, allow_redirects=False, timeout=30)

        if r.status_code != 200:
            return jsonify({"success": False, "login_required": True, "message": "Token abgelaufen — bitte erneut anmelden."})

        token_response = r.json()
        token = token_response["access_token"]

        # Save new token
        token_data = {
            "access_token": token,
            "refresh_token": token_response.get("refresh_token", refresh_token),
            "expires_at": int(_time.time()) + token_response.get("expires_in", 86400),
            "saved_at": int(_time.time()),
        }
        with open(TOKEN_FILE, "w") as tf:
            json.dump(token_data, tf, indent=2)

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

        return jsonify({"success": True, "message": f"{result} Gerät(e) aktualisiert — kein Login nötig!", "login_required": False})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/restart-addon", methods=["POST"])
def restart_addon():
    if not SUPERVISOR_TOKEN:
        return jsonify({"success": False, "error": "Kein SUPERVISOR_TOKEN verfügbar"}), 500
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
