#!/bin/bash
if [ -f /data/options.json ]; then
    set -o allexport
    eval "$(jq -r 'to_entries[]|"\(.key)=\"\(.value)\""' /data/options.json)"
    set +o allexport
    exec python3 hc2mqtt.py
fi
exec python3 hc2mqtt.py --config ./config/config.ini
