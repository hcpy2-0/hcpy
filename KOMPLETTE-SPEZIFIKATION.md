# hcpy-friendly: Vollständige Umbau-Spezifikation (FINAL)

## Kontext

Dieses Dokument beschreibt ALLE Änderungen am Repository https://github.com/hcpy2-0/hcpy (Tag v0.4.8). Es dient als Anweisung für Claude Code, der die Änderungen auf einem geklonten Repo durchführen soll.

Das Repo ist ein Python-Tool das Bosch/Siemens Home Connect Geräte lokal über WebSocket anspricht und deren Status/Steuerung über MQTT bereitstellt. Es existiert auch als Home Assistant Addon.

**Ziel:** Kein User soll mehr SSH, Docker-Befehle oder Browser-Dev-Tools brauchen um das Addon einzurichten.

**WICHTIG — Erkenntnisse aus dem realen Test:**
- Das AppArmor-Profil darf `/dev/null` NICHT blockieren (bash braucht es für Redirects)
- Python liegt je nach Base-Image unter `/usr/local/bin/python3`, nicht `/usr/bin/python3`
- `init: false` in config.yaml verursacht Crash — Zeile weglassen (Default `true`)
- Der Shebang in run.sh muss `#!/usr/bin/with-contenv bashio` sein, nicht `#!/usr/bin/env bashio`
- Das Dockerfile MUSS `$BUILD_FROM` (HA Base-Image) nutzen, sonst fehlt bashio
- run.sh braucht einen Fallback falls bashio trotzdem nicht verfügbar ist

---

## Übersicht der Änderungen

1. **Neue Dateien erstellen** (Web-UI, Scripts, Security, Translations)
2. **Bestehende Dateien ersetzen** (run.sh, Dockerfile, config.yaml, repository.yaml, README.md)
3. **Bestehende Dateien patchen** (hc2mqtt.py, hc-login.py, HADiscovery.py)
4. **Bestehende Dateien löschen** (compose.yaml, .github/, .vscode/, Linting-Configs)
5. **Bestehende Dateien NICHT ändern** (HCDevice.py, HCSocket.py, HCxml2json.py, discovery.yaml, requirements.txt, LICENSE)

---

# TEIL A: NEUE DATEIEN

---

## A1. web-ui/app.py

Flask-basierte Web-UI die über HA Ingress erreichbar ist.

**Endpunkte:**
- `GET /` — Hauptseite mit Status (Geräte, MQTT, Token)
- `GET /api/status` — JSON-Status
- `GET /api/token-status` — Prüft ob gültiger refresh_token in /data/tokens.json liegt
- `GET /api/logs` — Gibt die letzten N Zeilen des Addon-Logs zurück
- `POST /api/start-login` — Generiert OAuth-URL mit PKCE, gibt URL zurück
- `POST /api/complete-login` — Empfängt hcauth:// URL, parst code/state, ruft hc-login.py auf
- `POST /api/refresh-devices` — Aktualisiert Geräteliste mit gespeichertem Token (kein Browser nötig)
- `POST /api/restart-addon` — Ruft `http://supervisor/addons/self/restart` auf

**URL-Parsing-Logik:**
Der User kopiert die GESAMTE URL aus der Adressleiste in EIN Textfeld. `parse_hcauth_url()` akzeptiert:
- Volle hcauth:// URL → parst code und state per urlparse/parse_qs
- Query-String ohne Prefix (code=X&state=Y) → parst per parse_qs
- Nur den Code-Wert als Fallback → gibt code zurück, state leer

**Umgebungsvariablen:**
- `HCPY_CONFIG_DIR`, `HCPY_DEVICES_FILE`, `INGRESS_PORT`, `INGRESS_PATH`
- `SUPERVISOR_TOKEN`, `HCPY_AUTO_RESOLVE_HOSTS`, `HCPY_DOMAIN_SUFFIX`

**Flask-Server Warnung unterdrücken:**
```python
import logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)
```

### A1a. Log-Endpunkt

```python
@app.route("/api/logs")
def api_logs():
    n = request.args.get("n", 100, type=int)
    n = min(n, 500)
    log_lines = []
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if token:
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://supervisor/addons/self/logs",
                headers={"Authorization": f"Bearer {token}"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                log_lines = raw.strip().split("\n")[-n:]
        except Exception:
            pass
    if not log_lines:
        log_file = "/data/hcpy.log"
        if os.path.exists(log_file):
            try:
                with open(log_file, "r") as f:
                    log_lines = f.readlines()[-n:]
            except Exception:
                log_lines = ["Log nicht verfügbar"]
    return jsonify({"lines": log_lines, "count": len(log_lines)})
```

### A1b. Refresh-Devices-Endpunkt

```python
@app.route("/api/refresh-devices", methods=["POST"])
def refresh_devices():
    try:
        result = subprocess.run(
            [sys.executable, "/app/hc-login.py", DEVICES_FILE],
            capture_output=True, text=True, timeout=60, input="\n\n"
        )
        if result.returncode == 0 and os.path.exists(DEVICES_FILE):
            with open(DEVICES_FILE) as f:
                n = len(json.load(f))
            if os.environ.get("HCPY_AUTO_RESOLVE_HOSTS", "true").lower() == "true":
                try:
                    subprocess.run([sys.executable, "/app/scripts/resolve_hosts.py",
                        DEVICES_FILE, os.environ.get("HCPY_DOMAIN_SUFFIX", "")],
                        timeout=30, capture_output=True)
                except Exception:
                    pass
            return jsonify({"success": True, "message": f"{n} Gerät(e) aktualisiert!", "login_required": False})
        else:
            return jsonify({"success": False, "login_required": True, "message": "Token abgelaufen — bitte erneut anmelden."})
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Timeout"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
```

### A1c. Token-Status-Endpunkt

```python
@app.route("/api/token-status")
def token_status():
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
```

---

## A2. web-ui/templates/index.html

Jinja2-Template. Dark Theme, responsive. Vier Bereiche:

**Status-Karte:** MQTT-Verbindung, Geräteliste, "Geräte aktualisieren (ohne Login)"-Button

**Login-Karte mit 3 Phasen:** Start → URL-Paste → Ergebnis

**Log-Karte:** Scrollbarer Log-Container, Aktualisieren-Button

**JavaScript:** startLogin(), go(), restart(), reset(), refreshDevices(), loadLogs(), DOMContentLoaded→loadLogs

---

## A3. scripts/resolve_hosts.py

Automatische Host-Auflösung für devices.json.
Ablauf: IP-Check → FQDN-Check → DNS-Suffixe (fritz.box, speedport.ip, home, lan, local) → mDNS → Warnung.
Erstellt Backup vor Änderungen. Dependencies: zeroconf>=0.131.0 (optional).

---

## A4. home-assistant-addon/apparmor.txt

**ACHTUNG:** `/dev/null` und `/dev/urandom` MÜSSEN erlaubt sein! Python-Pfade unter BEIDEN `/usr/bin/` UND `/usr/local/bin/`.

```
#include <tunables/global>

profile hcpy flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>
  #include <abstractions/python>

  network inet stream,
  network inet dgram,
  network inet6 stream,
  network inet6 dgram,

  /dev/null rw,
  /dev/urandom r,
  /dev/random r,
  deny /dev/mem rw,
  deny /dev/kmem rw,
  deny /dev/port rw,

  /usr/bin/python3* rix,
  /usr/local/bin/python3* rix,
  /usr/lib/python3/** r,
  /usr/lib/python3/**/*.so mr,
  /usr/local/lib/python3/** r,
  /usr/local/lib/python3/**/*.so mr,

  /app/ r,
  /app/** r,
  /app/**/*.py rix,
  /app/**/*.sh rix,

  /config/ rw,
  /config/** rw,
  /data/ rw,
  /data/** rw,
  /tmp/ rw,
  /tmp/** rw,
  /run/ r,
  /run/** rw,

  @{PROC}/@{pid}/fd/ r,
  @{PROC}/@{pid}/mounts r,
  @{PROC}/sys/net/** r,

  /usr/bin/bash rix,
  /usr/bin/with-contenv rix,
  /usr/bin/bashio rix,
  /bin/sh rix,
  /bin/busybox rix,
  /usr/bin/curl rix,
  /usr/bin/timeout rix,
  /usr/bin/jq rix,

  /etc/ssl/** r,
  /usr/share/ca-certificates/** r,

  deny /sys/** w,
  deny @{PROC}/@{pid}/mem rw,
  deny /boot/** rw,
  deny /lib/modules/** rw,
}
```

---

## A5–A7. Translations, DOCS.md, build.yaml, requirements-extra.txt, etc.

- **translations/de.yaml + en.yaml:** Alle Schema-Felder, MQTT: "Leer lassen für automatische Erkennung"
- **DOCS.md:** Voraussetzungen, 3-Schritt-Einrichtung, MQTT, Hostnamen, Fehlerbehebung
- **build.yaml:** Multi-Arch `ghcr.io/home-assistant/*-base-python:3.13-alpine3.21`
- **requirements-extra.txt:** `flask>=3.0`, `zeroconf>=0.131.0`
- **config/config.ini.example:** Standalone-Config
- **repository.yaml:** `name: Home Connect Local`
- **CHANGELOG.md:** v0.5.0
- **.gitignore:** `__pycache__/`, `*.pyc`, `venv/`, `config/devices.json`, `*.zip`, `*.backup`

---

# TEIL B: BESTEHENDE DATEIEN ERSETZEN

---

## B1. run.sh (KOMPLETT ERSETZEN)

**Shebang:** `#!/usr/bin/with-contenv bashio` (NICHT `#!/usr/bin/env bashio`!)

**Bashio-Fallback am Anfang:**

```bash
#!/usr/bin/with-contenv bashio

USE_BASHIO=true
if ! command -v bashio &>/dev/null; then
    echo "[WARN] bashio nicht gefunden, nutze Fallback"
    USE_BASHIO=false
fi

read_config() {
    local key="$1" default="$2"
    if [ "$USE_BASHIO" = true ]; then
        local val
        val=$(bashio::config "$key" 2>/dev/null) || true
        [ -n "$val" ] && [ "$val" != "null" ] && echo "$val" && return
    fi
    if [ -f "/data/options.json" ]; then
        python3 -c "import json; print(json.load(open('/data/options.json')).get('$key','$default'))" 2>/dev/null && return
    fi
    echo "$default"
}

log_info()  { if [ "$USE_BASHIO" = true ]; then bashio::log.info "$1"; else echo "[INFO] $1"; fi; }
log_warn()  { if [ "$USE_BASHIO" = true ]; then bashio::log.warning "$1"; else echo "[WARNING] $1"; fi; }
log_error() { if [ "$USE_BASHIO" = true ]; then bashio::log.error "$1"; else echo "[ERROR] $1"; fi; }
```

**Ablauf:**
1. Bashio prüfen + Fallback
2. Config laden (read_config statt bashio::config)
3. MQTT Auto-Discovery (bashio::services → Netzwerk-Probe → Warnung)
4. Web-UI starten
5. Auf devices.json warten
6. Auto-Sync (Token-Refresh)
7. Host-Auflösung
8. hc2mqtt.py starten
9. Graceful Shutdown

### B1a. Auto-Sync beim Start

```bash
if [ -f "/data/tokens.json" ] && [ -f "${DEVICES}" ]; then
    log_info "Auto-Sync: Prüfe auf neue Geräte..."
    sync_output=$(python3 /app/hc-login.py "${DEVICES}" 2>&1 <<< $'\n\n') || true
    if echo "$sync_output" | grep -q "Geräte-Update"; then
        log_info "Auto-Sync: ${sync_output##*Geräte-Update: }"
    elif echo "$sync_output" | grep -q "Browser-Login"; then
        log_info "Auto-Sync: Token abgelaufen, überspringe"
    else
        log_info "Auto-Sync: Keine Änderungen"
    fi
fi
```

---

## B2. Dockerfile (KOMPLETT ERSETZEN)

**WICHTIG:** `$BUILD_FROM` MUSS HA Base-Image sein (enthält bashio, S6).

```dockerfile
ARG BUILD_FROM
FROM $BUILD_FROM

LABEL io.hass.version="VERSION" io.hass.type="addon" io.hass.arch="armhf|aarch64|i386|amd64"

RUN apk add --no-cache \
    python3 py3-pip py3-cryptography py3-cffi bash curl \
    openssl-dev gcc musl-dev python3-dev libffi-dev

WORKDIR /app
COPY requirements.txt /app/
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt
COPY requirements-extra.txt /app/
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements-extra.txt
RUN apk del gcc musl-dev python3-dev libffi-dev openssl-dev

COPY hc-login.py hc2mqtt.py HCDevice.py HCSocket.py HCxml2json.py HADiscovery.py /app/
COPY discovery.yaml /app/
COPY web-ui/ /app/web-ui/
COPY scripts/ /app/scripts/
COPY run.sh /app/run.sh
RUN chmod +x /app/run.sh /app/scripts/*.py

CMD [ "/app/run.sh" ]
```

---

## B3. home-assistant-addon/config.yaml (KOMPLETT ERSETZEN)

**WICHTIG:** KEINE `init: false` Zeile! Default `true`, S6-Overlay braucht `/init`.

| Eigenschaft | Alt | Neu | Grund |
|-------------|-----|-----|-------|
| ingress | — | true | Web-UI |
| ingress_port | — | 8099 | Flask |
| panel_icon | — | mdi:dishwasher | Seitenmenü |
| host_network | true | false | Security |
| map | — | addon_config (rw) | HA-konform |
| hassio_api | — | true | Restart + Logs |
| hassio_role | — | default | Minimale Rechte |
| services | mqtt:need | mqtt:want | Start ohne MQTT |
| apparmor | — | true | Security |
| watchdog | — | tcp://[HOST]:[PORT:8099] | Health-Check |
| stage | — | experimental | Beta |
| backup | — | hot | Kein Stopp |
| init | — | **NICHT SETZEN** | S6 braucht /init |
| MQTT-Felder | required | optional (str?, password?) | Auto-Discovery |

---

## B4. README.md (KOMPLETT ERSETZEN)

Feature-Vergleich, 3-Schritt-Einrichtung, MQTT, Host-Auflösung, Topics, Sicherheit, Standalone, Fehlerbehebung.

---

# TEIL C: BESTEHENDE DATEIEN PATCHEN

---

## C1. hc2mqtt.py — Watchdog + MQTT-Fallback + Secret-Redaction

### C1a. Watchdog (Issue #120)
Watchdog-Thread in client_connect(): last_message_time pro Gerät, 5-Min-Timeout → ws.close() → Reconnect. MQTT-Topic {mqtt_topic}/watchdog alle 60s.

### C1b. MQTT-Fallback (Issue #215)
Try-Except um client.connect() mit Fallback auf core-mosquitto falls localhost/127.0.0.1 refused.

### C1c. Secret-Redaction (Issue #108)
redact_device() maskiert key/iv in allen print/hcprint-Aufrufen.

---

## C2. HADiscovery.py — Secret-Redaction (Issue #108)

Dieselbe redact_device(). Alle Log-Stellen mit device → redact_device(device).

---

## C3. hc-login.py — Token-Speicher + Geräte-Merge

### C3a. try_token_refresh() vor OAuth-Flow
Liest /data/tokens.json, postet refresh_token, speichert neuen Token.

### C3b. Programmstruktur
Token-Refresh zuerst, bei Erfolg OAuth-Flow überspringen.

### C3c. Token speichern nach Browser-Login
access_token + refresh_token + expires_at → /data/tokens.json

### C3d. merge_devices() statt Überschreiben
Neue Geräte hinzufügen, bestehende Hosts beibehalten, entfernte Geräte behalten.

---

# TEIL D–E: LÖSCHEN / NICHT ÄNDERN

**Löschen:** compose.yaml, .github/, .vscode/, .pre-commit-config.yaml, .yamllint, .editorconfig

**Nicht ändern:** HCDevice.py, HCSocket.py, HCxml2json.py, discovery.yaml, requirements.txt, LICENSE, find-psk.frida, images/, tests/

---

# TEIL F: SICHERHEIT

1. AppArmor: /dev/null rw erlaubt, /dev/mem verboten, beide Python-Pfade
2. host_network: false
3. hassio_role: default
4. password Schema-Typ für MQTT
5. MQTT Auto-Discovery (kein Klartext-Passwort)
6. Token in /data (nicht user-sichtbar)
7. Secret-Redaction (key/iv nie in Logs)
8. Graceful Shutdown
9. Hot-Backup
10. addon_config Map
11. devices.json.backup
12. Keine docker_api/host_pid/privileged/full_access

---

# TEIL G: ISSUE-REFERENZEN

| Issue | Fix |
|-------|-----|
| #120 WebSocket stirbt | Watchdog-Thread (C1a) |
| #215 MQTT localhost | Auto-Discovery + Fallback (C1b) |
| #108 Secrets in Logs | redact_device() (C1c, C2) |
| #73 sslpsk | requirements.txt Conditional |
| #81 #116 Login | Web-UI + URL-Paste (A1, A2) |
| Wiederholter Login | Token-Refresh + Merge (C3) |
| Auto-Sync | run.sh Auto-Sync (B1a) |

---

# TEIL H: ERRATA AUS REALEM TEST (in obige Abschnitte eingearbeitet)

| Problem | Fix |
|---------|-----|
| /dev/null: Permission denied | A4: /dev/null rw explizit erlaubt |
| can't open '/init' | B3: init-Zeile entfernt (Default true) |
| bashio::config not found | B1: read_config() mit python3-Fallback |
| /usr/local/bin/python3: Permission denied | A4: beide Pfade erlaubt |
| Falscher Shebang | B1: #!/usr/bin/with-contenv bashio |
| Flask dev-server Warnung | A1: werkzeug Logger auf ERROR |
