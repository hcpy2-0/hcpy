#!/usr/bin/bash
# HomeConnect2MQTT run script
# Supports HA Add-on mode and standalone mode with bashio fallback

set -u

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

WEBUI_PID=""
HCMQTT_PID=""

cleanup() {
    log_info "Shutting down..."
    [ -n "$WEBUI_PID" ] && kill "$WEBUI_PID" 2>/dev/null || true
    [ -n "$HCMQTT_PID" ] && kill "$HCMQTT_PID" 2>/dev/null || true
    wait 2>/dev/null || true
    log_info "Shutdown complete."
    exit 0
}

trap cleanup SIGTERM SIGINT

if [ ! -f "/data/options.json" ] && [ "$USE_BASHIO" = false ]; then
    log_info "Standalone mode - no /data/options.json found"
    exec python3 /app/hc2mqtt.py --config /app/config/config.ini
fi

log_info "HomeConnect2MQTT starting (HA Add-on mode)..."

export HCPY_DEVICES_FILE="$(read_config HCPY_DEVICES_FILE '/config/devices.json')"
export HCPY_DISCOVERY_FILE="$(read_config HCPY_DISCOVERY_FILE '/config/discovery.yaml')"
export HCPY_MQTT_PREFIX="$(read_config HCPY_MQTT_PREFIX 'homeconnect/')"
export HCPY_MQTT_SSL="$(read_config HCPY_MQTT_SSL 'false')"
export HCPY_MQTT_CAFILE="$(read_config HCPY_MQTT_CAFILE '')"
export HCPY_MQTT_CERTFILE="$(read_config HCPY_MQTT_CERTFILE '')"
export HCPY_MQTT_KEYFILE="$(read_config HCPY_MQTT_KEYFILE '')"
export HCPY_MQTT_CLIENTNAME="$(read_config HCPY_MQTT_CLIENTNAME 'hcpy')"
export HCPY_HA_DISCOVERY="$(read_config HCPY_HA_DISCOVERY 'true')"
export HCPY_DOMAIN_SUFFIX="$(read_config HCPY_DOMAIN_SUFFIX '')"
export HCPY_DEBUG="$(read_config HCPY_DEBUG 'false')"
export HCPY_EVENTS_AS_SENSORS="$(read_config HCPY_EVENTS_AS_SENSORS 'false')"
export HCPY_AUTO_RESOLVE_HOSTS="$(read_config HCPY_AUTO_RESOLVE_HOSTS 'true')"

export HCPY_CONFIG_DIR="/config"
export INGRESS_PORT="${INGRESS_PORT:-8099}"

HCPY_MQTT_HOST="$(read_config HCPY_MQTT_HOST '')"
HCPY_MQTT_PORT="$(read_config HCPY_MQTT_PORT '')"
HCPY_MQTT_USERNAME="$(read_config HCPY_MQTT_USERNAME '')"
HCPY_MQTT_PASSWORD="$(read_config HCPY_MQTT_PASSWORD '')"
HCPY_MQTT_AUTO="false"
mqtt_configured="false"

if [ -n "$HCPY_MQTT_HOST" ] && [ -n "$HCPY_MQTT_PORT" ] && [ "$HCPY_MQTT_PORT" != "0" ]; then
    log_info "MQTT: Manuell konfiguriert (${HCPY_MQTT_HOST}:${HCPY_MQTT_PORT})"
    mqtt_configured="true"
fi

if [ "$mqtt_configured" = "false" ] && [ "$USE_BASHIO" = true ]; then
    if bashio::services.available mqtt; then
        HCPY_MQTT_HOST="$(bashio::services mqtt "host")"
        HCPY_MQTT_PORT="$(bashio::services mqtt "port")"
        HCPY_MQTT_USERNAME="$(bashio::services mqtt "username")"
        HCPY_MQTT_PASSWORD="$(bashio::services mqtt "password")"
        if [ -n "$HCPY_MQTT_HOST" ]; then
            log_info "MQTT: Auto-Discovery über bashio::services (${HCPY_MQTT_HOST}:${HCPY_MQTT_PORT})"
            HCPY_MQTT_AUTO="true"
            mqtt_configured="true"
        fi
    fi
fi

if [ "$mqtt_configured" = "false" ]; then
    for try_host in core-mosquitto localhost 127.0.0.1; do
        if timeout 2 bash -c "echo > /dev/tcp/${try_host}/1883" 2>/dev/null; then
            HCPY_MQTT_HOST="$try_host"
            HCPY_MQTT_PORT="1883"
            log_info "MQTT: Netzwerk-Probe erfolgreich (${try_host}:1883)"
            HCPY_MQTT_AUTO="true"
            mqtt_configured="true"
            break
        fi
    done
fi

if [ "$mqtt_configured" = "false" ]; then
    log_warn "MQTT: Kein Broker gefunden. Web-UI läuft trotzdem."
fi

export HCPY_MQTT_HOST HCPY_MQTT_PORT HCPY_MQTT_USERNAME HCPY_MQTT_PASSWORD HCPY_MQTT_AUTO

log_info "Starte Web-UI auf Port ${INGRESS_PORT}..."
python3 /app/web-ui/app.py &
WEBUI_PID=$!

DEVICES="${HCPY_DEVICES_FILE}"

if [ ! -f "$DEVICES" ]; then
    log_warn "devices.json nicht gefunden (${DEVICES})"
    log_info "Bitte über die Web-UI anmelden um Geräte zu konfigurieren."
    while [ ! -f "$DEVICES" ]; do
        sleep 10
    done
    log_info "devices.json gefunden!"
fi

if [ -f "/data/tokens.json" ] && [ -f "$DEVICES" ]; then
    log_info "Auto-Sync: Prüfe auf neue Geräte..."
    sync_output=$(python3 /app/hc-login.py "$DEVICES" 2>&1 <<< $'\n\n') || true
    if echo "$sync_output" | grep -q "Geräte-Update"; then
        log_info "Auto-Sync: ${sync_output##*Geräte-Update: }"
    elif echo "$sync_output" | grep -q "Browser-Login"; then
        log_info "Auto-Sync: Token abgelaufen, überspringe"
    else
        log_info "Auto-Sync: Keine Änderungen"
    fi
fi

if [ "${HCPY_AUTO_RESOLVE_HOSTS}" = "true" ]; then
    log_info "Starte Host-Auflösung..."
    python3 /app/scripts/resolve_hosts.py "$DEVICES" "${HCPY_DOMAIN_SUFFIX}" || \
        log_warn "Host-Auflösung fehlgeschlagen (nicht kritisch)"
fi

if [ ! -f "${HCPY_DISCOVERY_FILE}" ]; then
    log_info "discovery.yaml nicht gefunden, kopiere Default..."
    cp /app/discovery.yaml "${HCPY_DISCOVERY_FILE}"
fi

if [ "$mqtt_configured" = "true" ]; then
    log_info "Starte hc2mqtt.py..."
    python3 /app/hc2mqtt.py &
    HCMQTT_PID=$!
else
    log_warn "hc2mqtt.py nicht gestartet - kein MQTT-Broker konfiguriert"
fi

wait
