#!/usr/bin/env python3
# This directly follows the OAuth login flow that is opaquely described
# https://github.com/openid/AppAuth-Android
# A really nice walk through of how it works is:
# https://auth0.com/docs/get-started/authentication-and-authorization-flow/call-your-api-using-the-authorization-code-flow-with-pkce
import io
import json
import os
import re
import sys
import time as _time
from base64 import urlsafe_b64encode as base64url_encode
from urllib.parse import unquote, urlencode
from zipfile import ZipFile

import requests
from Crypto.Hash import SHA256
from Crypto.Random import get_random_bytes

try:
    from HCxml2json import xml2json
except ModuleNotFoundError:
    import importlib.util

    _module_path = os.path.join(os.path.dirname(__file__), "HCxml2json.py")
    _spec = importlib.util.spec_from_file_location("HCxml2json", _module_path)
    if _spec is None or _spec.loader is None:
        raise
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    xml2json = _mod.xml2json


def debug(*args):
    print(*args, file=sys.stderr)


TOKEN_FILE = os.environ.get("HCPY_TOKEN_FILE", "/data/tokens.json")

# The app_id and scope are hardcoded in the application
app_id = "9B75AC9EC512F36C84256AC47D813E2C1DD0D6520DF774B020E1E6E2EB29B1F3"
scope = ["ReadOrigApi"]

base_url = "https://api.home-connect.com/security/oauth/"
asset_urls = [
    "https://prod.reu.rest.homeconnectegw.com/",  # EU
    "https://prod.rna.rest.homeconnectegw.com/",  # US
]


def b64(b):
    return re.sub(r"=", "", base64url_encode(b).decode("UTF-8"))


def b64random(num):
    return b64(base64url_encode(get_random_bytes(num)))


def try_token_refresh():
    """
    Versucht einen gespeicherten refresh_token zu nutzen.
    Gibt den access_token zurück oder None falls kein gültiger Token vorhanden.
    """
    if not os.path.exists(TOKEN_FILE):
        return None

    try:
        with open(TOKEN_FILE, "r") as f:
            stored = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

    refresh_token = stored.get("refresh_token", "")
    if not refresh_token:
        return None

    debug("Versuche Token-Refresh mit gespeichertem refresh_token...")

    token_url = base_url + "token"
    refresh_fields = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    try:
        r = requests.post(token_url, data=refresh_fields, allow_redirects=False, timeout=30)
        if r.status_code == requests.codes.ok:
            token_response = json.loads(r.text)
            new_token = token_response["access_token"]

            # Neuen Token speichern
            token_data = {
                "access_token": new_token,
                "refresh_token": token_response.get("refresh_token", refresh_token),
                "expires_at": int(_time.time()) + token_response.get("expires_in", 86400),
                "saved_at": int(_time.time()),
            }
            with open(TOKEN_FILE, "w") as tf:
                json.dump(token_data, tf, indent=2)

            debug(f"Token-Refresh erfolgreich! Neuer Token gültig bis {token_data['expires_at']}")
            return new_token
        else:
            debug(f"Token-Refresh fehlgeschlagen (HTTP {r.status_code}), Browser-Login nötig")
            return None
    except Exception as e:
        debug(f"Token-Refresh Fehler: {e}")
        return None


def save_token(token_response):
    """Speichert den Token-Response für spätere Nutzung."""
    token_data = {
        "access_token": token_response["access_token"],
        "refresh_token": token_response.get("refresh_token", ""),
        "expires_at": int(_time.time()) + token_response.get("expires_in", 86400),
        "saved_at": int(_time.time()),
    }
    try:
        with open(TOKEN_FILE, "w") as tf:
            json.dump(token_data, tf, indent=2)
        debug(f"Token gespeichert in {TOKEN_FILE}")
    except Exception as e:
        debug(f"Warnung: Token konnte nicht gespeichert werden: {e}")


def merge_devices(existing_file, new_devices):
    """
    Merged neue Geräte in die bestehende devices.json.
    - Neue Geräte werden hinzugefügt
    - Bestehende Geräte: keys/features werden aktualisiert, host bleibt erhalten
    - Entfernte Geräte werden NICHT gelöscht (könnten offline sein)
    """
    existing = []
    if os.path.exists(existing_file):
        try:
            with open(existing_file, "r") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            existing = []

    # Index bestehender Geräte nach Name
    existing_by_name = {d["name"]: d for d in existing}

    merged = []
    new_count = 0
    updated_count = 0

    for new_dev in new_devices:
        name = new_dev["name"]
        if name in existing_by_name:
            # Gerät existiert: Keys aktualisieren, Host beibehalten
            old_dev = existing_by_name[name]
            old_host = old_dev.get("host", "")
            new_dev_merged = {**new_dev}

            # Host nur überschreiben wenn der alte ein Kurzname war
            # und der neue identisch ist (keine manuelle Änderung)
            if old_host and old_host != new_dev.get("host", ""):
                # User hat Host manuell geändert (IP, FQDN) -> beibehalten
                new_dev_merged["host"] = old_host

            merged.append(new_dev_merged)
            updated_count += 1
            debug(f"Aktualisiert: {name} (Host: {new_dev_merged['host']})")
        else:
            # Neues Gerät
            merged.append(new_dev)
            new_count += 1
            debug(f"Neu hinzugefügt: {name}")

    # Geräte die in existing aber nicht in new_devices sind: beibehalten
    new_names = {d["name"] for d in new_devices}
    for old_dev in existing:
        if old_dev["name"] not in new_names:
            merged.append(old_dev)
            debug(f"Beibehalten (nicht im Account): {old_dev['name']}")

    print(f"Geräte-Update: {new_count} neu, {updated_count} aktualisiert, {len(merged)} gesamt")
    return merged


def fetch_devices(token, devicefile):
    """Ruft die Geräteliste ab und schreibt sie in die devices.json."""
    headers = {
        "Authorization": "Bearer " + token,
    }

    # Try to request account details from all geos
    r = None
    asset_url = None
    for url in asset_urls:
        r = requests.get(url + "account/details", headers=headers)
        if r.status_code == requests.codes.ok:
            asset_url = url
            break

    if r is None or r.status_code != requests.codes.ok:
        print("unable to fetch account details", file=sys.stderr)
        if r is not None:
            print(r.headers, r.text)
        return False

    account = json.loads(r.text)
    configs = []

    # Redacted account info for logging
    debug(f"Account geladen: {len(account.get('data', {}).get('homeAppliances', []))} Geräte gefunden")

    for app in account["data"]["homeAppliances"]:
        app_brand = app["brand"]
        app_type = app["type"]
        app_identifier = app["identifier"]

        config = {
            "name": app_type.lower(),
        }

        configs.append(config)

        if "tls" in app:
            config["host"] = app_brand + "-" + app_type + "-" + app_identifier
            config["key"] = app["tls"]["key"]
        else:
            config["host"] = app_identifier
            config["key"] = app["aes"]["key"]
            config["iv"] = app["aes"]["iv"]

        # Fetch the XML zip file for this device
        app_url = asset_url + "api/iddf/v1/iddf/" + app_identifier
        debug(f"fetching {app_url}")
        r = requests.get(app_url, headers=headers)
        if r.status_code != requests.codes.ok:
            print(app_identifier, ": unable to fetch machine description?")
            continue

        content = r.content
        debug(f"{app_url}: {app_identifier}.zip")
        with open(app_identifier + ".zip", "wb") as f:
            f.write(content)
        z = ZipFile(io.BytesIO(content))
        features = z.open(app_identifier + "_FeatureMapping.xml").read()
        description = z.open(app_identifier + "_DeviceDescription.xml").read()

        machine = xml2json(features, description)
        config["description"] = machine["description"]
        config["features"] = machine["features"]
        print("Discovered device: " + config["name"] + " - Device hostname: " + config["host"])

    # Merge mit bestehender devices.json
    configs_merged = merge_devices(devicefile, configs)
    with open(devicefile, "w") as f:
        json.dump(configs_merged, f, ensure_ascii=True, indent=4)

    print(
        "Success. You can now edit "
        + devicefile
        + ", if needed, and run hc2mqtt.py or start Home Assistant addon again"
    )
    return True


# --- Main ---
if __name__ == "__main__" or not hasattr(sys, '_called_from_test'):
    devicefile = sys.argv[1] if len(sys.argv) > 1 else "config/devices.json"

    # Versuche zuerst Token-Refresh (kein Browser nötig)
    refreshed_token = try_token_refresh()

    if refreshed_token:
        print("Gespeicherter Token gültig — kein Browser-Login nötig!")
        token = refreshed_token
    else:
        # Normaler OAuth-Browser-Flow
        print("Kein gültiger Token gespeichert, Browser-Login erforderlich...")

        session = requests.Session()

        verifier = b64(get_random_bytes(32))

        login_query = {
            "response_type": "code",
            "prompt": "login",
            "code_challenge": b64(SHA256.new(verifier.encode("UTF-8")).digest()),
            "code_challenge_method": "S256",
            "client_id": app_id,
            "scope": " ".join(scope),
            "nonce": b64random(16),
            "state": b64random(16),
            "redirect_uri": "hcauth://auth/prod",
        }

        loginpage_url = base_url + "authorize?" + urlencode(login_query)
        token_url = base_url + "token"

        print(
            "Visit the following URL in Chrome, use the F12 developer tools "
            "to monitor the network responses, and look for the request starting "
            "hcauth://auth for the relevant authentication tokens:"
        )
        print(loginpage_url)

        code = unquote(input("Input code:"))
        state = input("Input state:")
        grant_type = "authorization_code"

        debug(f"{code=} {grant_type=} {state=}")

        token_url = base_url + "token"

        token_fields = {
            "grant_type": grant_type,
            "client_id": app_id,
            "code_verifier": verifier,
            "code": code,
            "redirect_uri": login_query["redirect_uri"],
        }

        debug(f"{token_url=} {token_fields=}")

        r = requests.post(token_url, data=token_fields, allow_redirects=False)
        if r.status_code != requests.codes.ok:
            print("Bad code?", file=sys.stderr)
            print(r.headers, r.text)
            exit(1)

        debug("--------- got token page ----------")

        token_response = json.loads(r.text)
        token = token_response["access_token"]
        debug(f"Received access token (length={len(token)})")

        # Token speichern für spätere Nutzung
        save_token(token_response)

    # Geräte abrufen und speichern
    fetch_devices(token, devicefile)
