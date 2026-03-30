#!/bin/bash
# HomeConnect2MQTT run script
# Supports both HA Addon mode and standalone mode

CONFIG_PATH=/data/options.json

# --- Helper: read config value from options.json ---
cfg() {
    local key="$1"
    local default="$2"
    if [ -f "$CONFIG_PATH" ]; then
        val=$(jq -r ".${key} // empty" "$CONFIG_PATH" 2>/dev/null)
        if [ -n "$val" ] && [ "$val" != "null" ]; then
            echo "$val"
            return
        fi
    fi
    echo "$default"
}

# --- Logging ---
log_info()    { echo "[INFO] $1"; }
log_warning() { echo "[WARNING] $1"; }
log_error()   { echo "[ERROR] $1"; }

# --- Cleanup / Graceful Shutdown ---
WEBUI_PID=""
HCMQTT_PID=""

cleanup() {
    log_info "Shutting down..."
    [ -n "$WEBUI_PID" ] && kill "$WEBUI_PID" 2>/dev/null
    [ -n "$HCMQTT_PID" ] && kill "$HCMQTT_PID" 2>/dev/null
    wait 2>/dev/null
    log_info "Shutdown complete."
    exit 0
}

trap cleanup SIGTERM SIGINT

# --- Standalone mode (no HA Addon) ---
if [ ! -f "${CONFIG_PATH}" ]; then
    log_info "Standalone mode — no /data/options.json found"
    exec python3 hc2mqtt.py --config ./config/config.ini
fi

# --- HA Addon mode ---
log_info "HomeConnect2MQTT starting (HA Addon mode)..."

# 1. Load configuration
export HCPY_DEVICES_FILE="$(cfg HCPY_DEVICES_FILE '/config/devices.json')"
export HCPY_DISCOVERY_FILE="$(cfg HCPY_DISCOVERY_FILE '/config/discovery.yaml')"
export HCPY_MQTT_PREFIX="$(cfg HCPY_MQTT_PREFIX 'homeconnect/')"
export HCPY_MQTT_SSL="$(cfg HCPY_MQTT_SSL 'false')"
export HCPY_MQTT_CAFILE="$(cfg HCPY_MQTT_CAFILE '')"
export HCPY_MQTT_CERTFILE="$(cfg HCPY_MQTT_CERTFILE '')"
export HCPY_MQTT_KEYFILE="$(cfg HCPY_MQTT_KEYFILE '')"
export HCPY_MQTT_CLIENTNAME="$(cfg HCPY_MQTT_CLIENTNAME 'hcpy')"
export HCPY_HA_DISCOVERY="$(cfg HCPY_HA_DISCOVERY 'true')"
export HCPY_DOMAIN_SUFFIX="$(cfg HCPY_DOMAIN_SUFFIX '')"
export HCPY_DEBUG="$(cfg HCPY_DEBUG 'false')"
export HCPY_EVENTS_AS_SENSORS="$(cfg HCPY_EVENTS_AS_SENSORS 'false')"
export HCPY_AUTO_RESOLVE_HOSTS="$(cfg HCPY_AUTO_RESOLVE_HOSTS 'true')"

# Config dir for Web-UI
export HCPY_CONFIG_DIR="/config"
export INGRESS_PORT="${INGRESS_PORT:-8099}"

# 2. MQTT Auto-Discovery
HCPY_MQTT_HOST="$(cfg HCPY_MQTT_HOST '')"
HCPY_MQTT_PORT="$(cfg HCPY_MQTT_PORT '')"
HCPY_MQTT_USERNAME="$(cfg HCPY_MQTT_USERNAME '')"
HCPY_MQTT_PASSWORD="$(cfg HCPY_MQTT_PASSWORD '')"
HCPY_MQTT_AUTO="false"

mqtt_configured="false"

# Check if manually configured
if [ -n "$HCPY_MQTT_HOST" ] && [ "$HCPY_MQTT_HOST" != "" ]; then
    if [ -n "$HCPY_MQTT_PORT" ] && [ "$HCPY_MQTT_PORT" -gt 0 ] 2>/dev/null; then
        log_info "MQTT: Manuell konfiguriert ($HCPY_MQTT_HOST:$HCPY_MQTT_PORT)"
        mqtt_configured="true"
    fi
fi

# Try HA Supervisor services API for MQTT
if [ "$mqtt_configured" = "false" ] && [ -n "$SUPERVISOR_TOKEN" ]; then
    mqtt_json=$(curl -s -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/services/mqtt 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$mqtt_json" ]; then
        mqtt_host_api=$(echo "$mqtt_json" | jq -r '.data.host // empty' 2>/dev/null)
        mqtt_port_api=$(echo "$mqtt_json" | jq -r '.data.port // empty' 2>/dev/null)
        mqtt_user_api=$(echo "$mqtt_json" | jq -r '.data.username // empty' 2>/dev/null)
        mqtt_pass_api=$(echo "$mqtt_json" | jq -r '.data.password // empty' 2>/dev/null)
        if [ -n "$mqtt_host_api" ] && [ "$mqtt_host_api" != "null" ]; then
            HCPY_MQTT_HOST="$mqtt_host_api"
            HCPY_MQTT_PORT="${mqtt_port_api:-1883}"
            HCPY_MQTT_USERNAME="${mqtt_user_api}"
            HCPY_MQTT_PASSWORD="${mqtt_pass_api}"
            log_info "MQTT: Auto-Discovery über HA Services ($HCPY_MQTT_HOST:$HCPY_MQTT_PORT)"
            HCPY_MQTT_AUTO="true"
            mqtt_configured="true"
        fi
    fi
fi

# Fallback: Try common broker hosts
if [ "$mqtt_configured" = "false" ]; then
    for try_host in core-mosquitto localhost 127.0.0.1; do
        if timeout 2 bash -c "echo > /dev/tcp/$try_host/1883" 2>/dev/null; then
            HCPY_MQTT_HOST="$try_host"
            HCPY_MQTT_PORT="1883"
            log_info "MQTT: Netzwerk-Probe erfolgreich ($try_host:1883)"
            HCPY_MQTT_AUTO="true"
            mqtt_configured="true"
            break
        fi
    done
fi

if [ "$mqtt_configured" = "false" ]; then
    log_warning "MQTT: Kein Broker gefunden. Web-UI läuft trotzdem."
fi

export HCPY_MQTT_HOST HCPY_MQTT_PORT HCPY_MQTT_USERNAME HCPY_MQTT_PASSWORD HCPY_MQTT_AUTO

# 3. Start Web-UI as background process
log_info "Starte Web-UI auf Port $INGRESS_PORT..."
python3 /app/web-ui/app.py &
WEBUI_PID=$!

# 4. Wait for devices.json
if [ ! -f "${HCPY_DEVICES_FILE}" ]; then
    log_warning "devices.json nicht gefunden (${HCPY_DEVICES_FILE})"
    log_info "Bitte über die Web-UI anmelden um Geräte zu konfigurieren."
    while [ ! -f "${HCPY_DEVICES_FILE}" ]; do
        sleep 10
    done
    log_info "devices.json gefunden!"
fi

# 5. Host resolution (if enabled)
if [ "${HCPY_AUTO_RESOLVE_HOSTS}" = "true" ]; then
    log_info "Starte Host-Auflösung..."
    python3 /app/scripts/resolve_hosts.py "${HCPY_DEVICES_FILE}" "${HCPY_DOMAIN_SUFFIX}" || \
        log_warning "Host-Auflösung fehlgeschlagen (nicht kritisch)"
fi

# 6. Copy discovery.yaml if not present
if [ ! -f "${HCPY_DISCOVERY_FILE}" ]; then
    log_info "discovery.yaml nicht gefunden, kopiere Default..."
    cp /app/discovery.yaml "${HCPY_DISCOVERY_FILE}"
fi

# 7. Start hc2mqtt.py (if MQTT is configured)
if [ "$mqtt_configured" = "true" ]; then
    log_info "Starte hc2mqtt.py..."
    python3 /app/hc2mqtt.py &
    HCMQTT_PID=$!
else
    log_warning "hc2mqtt.py nicht gestartet — kein MQTT-Broker konfiguriert"
fi

# 8. Wait for processes
wait
