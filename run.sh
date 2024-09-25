#!/usr/bin/env bashio
CONFIG_PATH=/data/options.json
if [ -f ${CONFIG_PATH} ]; then

        set -o allexport
        HCPY_DEVICES_FILE="$(bashio::config 'HCPY_DEVICES_FILE')"
        HCPY_MQTT_HOST="$(bashio::config 'HCPY_MQTT_HOST')"
        HCPY_MQTT_PORT="$(bashio::config 'HCPY_MQTT_PORT')"
        HCPY_MQTT_PREFIX="$(bashio::config 'HCPY_MQTT_PREFIX')"
        HCPY_MQTT_USERNAME="$(bashio::config 'HCPY_MQTT_USERNAME')"
        HCPY_MQTT_PASSWORD="$(bashio::config 'HCPY_MQTT_PASSWORD')"
        HCPY_MQTT_SSL="$(bashio::config 'HCPY_MQTT_SSL')"
        HCPY_MQTT_CAFILE="$(bashio::config 'HCPY_MQTT_CAFILE')"
        HCPY_MQTT_CERTFILE="$(bashio::config 'HCPY_MQTT_CERTFILE')"
        HCPY_MQTT_KEYFILE="$(bashio::config 'HCPY_MQTT_KEYFILE')"
        HCPY_MQTT_CLIENTNAME="$(bashio::config 'HCPY_MQTT_CLIENTNAME')"
        HCPY_HA_DISCOVERY="$(bashio::config 'HCPY_HA_DISCOVERY')"
        HCPY_DOMAIN_SUFFIX="$(bashio::config 'HCPY_DOMAIN_SUFFIX')"
        HCPY_DEBUG="$(bashio::config 'HCPY_DEBUG')"
        HCPY_HOMECONNECT_EMAIL="$(bashio::config 'HCPY_HOMECONNECT_EMAIL')"
        HCPY_HOMECONNECT_PASSWORD="$(bashio::config 'HCPY_HOMECONNECT_PASSWORD')"
        set +o allexport
        
        if [ ! -f "${HCPY_DEVICES_FILE}" ]; then
                echo "File not found ${HCPY_DEVICES_FILE}"
                echo "Trying to retrieve devices.json"
                exec python3 hc-login.py $HCPY_HOMECONNECT_EMAIL $HCPY_HOMECONNECT_PASSWORD ${HCPY_DEVICES_FILE}
        fi
        exec python3 hc2mqtt.py
fi
exec python3 hc2mqtt.py --config ./config/config.ini
