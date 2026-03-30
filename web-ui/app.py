#!/usr/bin/env python3
"""Flask Web-UI for HomeConnect2MQTT addon setup."""
import json
import os
import subprocess
import sys
from urllib.parse import parse_qs, urlparse

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Configuration from environment
CONFIG_DIR = os.environ.get("HCPY_CONFIG_DIR", "/config")
DEVICES_FILE = os.environ.get("HCPY_DEVICES_FILE", os.path.join(CONFIG_DIR, "devices.json"))
INGRESS_PORT = int(os.environ.get("INGRESS_PORT", 8099))
INGRESS_PATH = os.environ.get("INGRESS_PATH", "")
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")


def parse_hcauth_url(raw):
    """
    Parse the hcauth:// URL or query string from the user.
    Accepts:
      - Full hcauth:// URL (hcauth://auth/prod?code=X&state=Y)
      - Query string (code=X&state=Y)
      - Just the code value as fallback
    Returns (code, state) tuple.
    """
    raw = raw.strip()
    if not raw:
        return None, None

    # Full hcauth:// URL
    if raw.startswith("hcauth://"):
        parsed = urlparse(raw)
        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        return code, state

    # Query string format
    if "code=" in raw:
        params = parse_qs(raw.split("?")[-1] if "?" in raw else raw)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        return code, state

    # Fallback: assume it's just the code
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


@app.route("/")
def index():
    return render_template(
        "index.html",
        status=get_status(),
        ingress=INGRESS_PATH,
    )


@app.route("/api/status")
def api_status():
    return jsonify(get_status())


@app.route("/api/token-status")
def token_status():
    """Prüft ob ein gültiger refresh_token gespeichert ist."""
    import time as _time
    token_file = "/data/tokens.json"
    if not os.path.exists(token_file):
        return jsonify({"has_token": False})
    try:
        with open(token_file) as f:
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
    """Generate OAuth URL with PKCE."""
    try:
        result = subprocess.run(
            [sys.executable, "/app/hc-login.py", DEVICES_FILE],
            capture_output=True, text=True, timeout=30,
            input=""  # Don't provide code/state yet
        )
        # The login URL is printed to stdout
        output = result.stdout + result.stderr
        for line in output.split("\n"):
            if "https://api.home-connect.com" in line:
                return jsonify({"success": True, "url": line.strip()})

        return jsonify({"success": False, "error": "Konnte Login-URL nicht generieren"}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Timeout"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/complete-login", methods=["POST"])
def complete_login():
    """Complete OAuth login with hcauth:// URL from user."""
    data = request.get_json()
    raw_url = data.get("url", "")

    code, state = parse_hcauth_url(raw_url)
    if not code:
        return jsonify({"success": False, "error": "Kein Code in der URL gefunden"}), 400

    try:
        # Pass code and state via stdin to hc-login.py
        stdin_data = f"{code}\n{state or ''}\n"
        result = subprocess.run(
            [sys.executable, "/app/hc-login.py", DEVICES_FILE],
            capture_output=True, text=True, timeout=60,
            input=stdin_data,
        )

        if result.returncode == 0 and os.path.exists(DEVICES_FILE):
            # Success — optionally run host resolution
            if os.environ.get("HCPY_AUTO_RESOLVE_HOSTS", "true").lower() == "true":
                try:
                    subprocess.run(
                        [sys.executable, "/app/scripts/resolve_hosts.py",
                         DEVICES_FILE, os.environ.get("HCPY_DOMAIN_SUFFIX", "")],
                        timeout=30, capture_output=True,
                    )
                except Exception:
                    pass

            with open(DEVICES_FILE) as f:
                n = len(json.load(f))

            return jsonify({
                "success": True,
                "message": f"{n} Gerät(e) erfolgreich konfiguriert!",
            })
        else:
            error_text = result.stderr or result.stdout
            return jsonify({
                "success": False,
                "error": error_text[-500:] if error_text else "Unbekannter Fehler",
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Timeout beim Login"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/refresh-devices", methods=["POST"])
def refresh_devices():
    """Aktualisiert die Geräteliste mit gespeichertem Token."""
    try:
        result = subprocess.run(
            [sys.executable, "/app/hc-login.py", DEVICES_FILE],
            capture_output=True, text=True, timeout=60,
            input="\n\n"  # Leere Eingaben — hc-login.py nutzt den gespeicherten Token
        )

        if result.returncode == 0 and os.path.exists(DEVICES_FILE):
            with open(DEVICES_FILE) as f:
                n = len(json.load(f))

            # Optional: Hosts auflösen
            if os.environ.get("HCPY_AUTO_RESOLVE_HOSTS", "true").lower() == "true":
                try:
                    subprocess.run(
                        [sys.executable, "/app/scripts/resolve_hosts.py",
                         DEVICES_FILE, os.environ.get("HCPY_DOMAIN_SUFFIX", "")],
                        timeout=30, capture_output=True,
                    )
                except Exception:
                    pass

            return jsonify({
                "success": True,
                "message": f"{n} Gerät(e) aktualisiert — kein Login nötig!",
                "login_required": False,
            })
        else:
            error_text = result.stderr or result.stdout
            if "Browser-Login" in (error_text or "") or result.returncode != 0:
                return jsonify({
                    "success": False,
                    "login_required": True,
                    "message": "Token abgelaufen — bitte erneut anmelden.",
                })
            return jsonify({"success": False, "error": (error_text or "")[-300:]}), 500

    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Timeout"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/restart-addon", methods=["POST"])
def restart_addon():
    """Restart the addon via Supervisor API."""
    if not SUPERVISOR_TOKEN:
        return jsonify({"success": False, "error": "Kein SUPERVISOR_TOKEN verfügbar"}), 500

    try:
        import requests as req
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
