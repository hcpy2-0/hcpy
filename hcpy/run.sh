#!/usr/bin/with-contenv bashio
# HomeConnect2MQTT run script
# Supports both HA Addon mode and standalone mode

CONFIG_PATH=/data/options.json

# --- Helper functions ---
log_info() {
    if command -v bashio::log.info &>/dev/null; then
        bashio::log.info "$1"
    else
        echo "[INFO] $1"
    fi
}

log_warning() {
    if command -v bashio::log.warning &>/dev/null; then
        bashio::log.warning "$1"
    else
        echo "[WARNING] $1"
    fi
}

log_error() {
    if command -v bashio::log.error &>/dev/null; then
        bashio::log.error "$1"
    else
        echo "[ERROR] $1"
    fi
}

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
set -o allexport

HCPY_DEVICES_FILE="$(bashio::config 'HCPY_DEVICES_FILE')"
HCPY_DISCOVERY_FILE="$(bashio::config 'HCPY_DISCOVERY_FILE')"
HCPY_MQTT_PREFIX="$(bashio::config 'HCPY_MQTT_PREFIX')"
HCPY_MQTT_SSL="$(bashio::config 'HCPY_MQTT_SSL')"
HCPY_MQTT_CAFILE="$(bashio::config 'HCPY_MQTT_CAFILE')"
HCPY_MQTT_CERTFILE="$(bashio::config 'HCPY_MQTT_CERTFILE')"
HCPY_MQTT_KEYFILE="$(bashio::config 'HCPY_MQTT_KEYFILE')"
HCPY_MQTT_CLIENTNAME="$(bashio::config 'HCPY_MQTT_CLIENTNAME')"
HCPY_HA_DISCOVERY="$(bashio::config 'HCPY_HA_DISCOVERY')"
HCPY_DOMAIN_SUFFIX="$(bashio::config 'HCPY_DOMAIN_SUFFIX')"
HCPY_DEBUG="$(bashio::config 'HCPY_DEBUG')"
HCPY_EVENTS_AS_SENSORS="$(bashio::config 'HCPY_EVENTS_AS_SENSORS')"
HCPY_AUTO_RESOLVE_HOSTS="$(bashio::config 'HCPY_AUTO_RESOLVE_HOSTS')"

# Config dir for Web-UI
HCPY_CONFIG_DIR="/config"
INGRESS_PORT="${INGRESS_PORT:-8099}"

set +o allexport

# 2. MQTT Auto-Discovery
HCPY_MQTT_HOST="$(bashio::config 'HCPY_MQTT_HOST' 2>/dev/null || true)"
HCPY_MQTT_PORT="$(bashio::config 'HCPY_MQTT_PORT' 2>/dev/null || true)"
HCPY_MQTT_USERNAME="$(bashio::config 'HCPY_MQTT_USERNAME' 2>/dev/null || true)"
HCPY_MQTT_PASSWORD="$(bashio::config 'HCPY_MQTT_PASSWORD' 2>/dev/null || true)"
HCPY_MQTT_AUTO="false"

mqtt_configured="false"

# Check if manually configured
if [ -n "$HCPY_MQTT_HOST" ] && [ "$HCPY_MQTT_HOST" != "null" ] && [ "$HCPY_MQTT_HOST" != "" ]; then
    if [ -n "$HCPY_MQTT_PORT" ] && [ "$HCPY_MQTT_PORT" != "null" ] && [ "$HCPY_MQTT_PORT" -gt 0 ] 2>/dev/null; then
        log_info "MQTT: Manuell konfiguriert ($HCPY_MQTT_HOST:$HCPY_MQTT_PORT)"
        mqtt_configured="true"
    fi
fi

# Try bashio services discovery
if [ "$mqtt_configured" = "false" ]; then
    if bashio::services "mqtt" 2>/dev/null; then
        HCPY_MQTT_HOST="$(bashio::services mqtt "host" 2>/dev/null || true)"
        HCPY_MQTT_PORT="$(bashio::services mqtt "port" 2>/dev/null || true)"
        HCPY_MQTT_USERNAME="$(bashio::services mqtt "username" 2>/dev/null || true)"
        HCPY_MQTT_PASSWORD="$(bashio::services mqtt "password" 2>/dev/null || true)"
        if [ -n "$HCPY_MQTT_HOST" ] && [ "$HCPY_MQTT_HOST" != "null" ]; then
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
export HCPY_CONFIG_DIR INGRESS_PORT

# 3. Start Web-UI as background process
log_info "Starte Web-UI auf Port $INGRESS_PORT..."
python3 /app/web-ui/app.py &
WEBUI_PID=$!

# 4. Wait for devices.json
if [ ! -f "${HCPY_DEVICES_FILE}" ]; then
    log_warning "devices.json nicht gefunden (${HCPY_DEVICES_FILE})"
    log_info "Bitte über die Web-UI anmelden um Geräte zu konfigurieren."
    # Wait loop — check every 10 seconds for devices.json
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
