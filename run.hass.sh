#!/usr/bin/env bashio
CONFIG_PATH=/data/options.json
if [ -f ${CONFIG_PATH} ]; then

        set -o allexport
        HCPY_DEVICES_FILE="$(bashio::config 'HCPY_DEVICES_FILE')"
        HCPY_DISCOVERY_FILE="$(bashio::config 'HCPY_DISCOVERY_FILE')"
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
	HCPY_EVENTS_AS_SENSORS="$(bashio::config 'HCPY_EVENTS_AS_SENSORS')"

        set +o allexport
        
        if [ ! -f "${HCPY_DEVICES_FILE}" ]; then
                echo "File not found ${HCPY_DEVICES_FILE}"
                echo "Please supply a suitable devices file using hc-login.py"
                exit 1
        fi

        if [ ! -f "${HCPY_DISCOVERY_FILE}" ]; then
                echo "File not found ${HCPY_DISCOVERY_FILE} copying default file"
		cp discovery.yaml "${HCPY_DISCOVERY_FILE}"
        fi
        exec python3 hc2mqtt.py
fi
exec python3 hc2mqtt.py --config ./config/config.ini
