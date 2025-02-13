import json

import yaml

from HCSocket import now

config = {}
try:
    with open("discovery.yaml", "r") as yaml_config:
        config = yaml.safe_load(yaml_config)
except Exception:
    print(now(), "HADiscovery - No discovery configuration file found.")

HA_DISCOVERY_PREFIX = config.get("HA_DISCOVERY_PREFIX", "homeassistant")
MAGIC_OVERRIDES = config.get("MAGIC_OVERRIDES", {})
EXPAND_NAME = config.get("EXPAND_NAME", {})
SKIP_ENTITIES = config.get("SKIP_ENTITIES", [])
DISABLED_ENTITIES = config.get("DISABLED_ENTITIES", [])
DISABLED_EXCEPTIONS = config.get("DISABLED_EXCEPTIONS", [])
ADDITIONAL_FEATURES = config.get("ADDITIONAL_FEATURES", [])


def publish_ha_discovery(device, client, mqtt_topic):
    print(f"{now()} Publishing HA discovery for {device['name']}")

    device_ident = device["name"]
    device_description = device.get("description", {})

    base_topic = mqtt_topic.split("/")[0]

    version_parts = filter(
        lambda d: d is not None,
        [device_description.get("version"), device_description.get("revision")],
    )

    device_info = {
        "identifiers": [device_ident],
        "name": device_ident,
        "manufacturer": device_description.get("brand"),
        "model": device_description.get("model"),
        "sw_version": ".".join(version_parts),
    }

    for feature in ADDITIONAL_FEATURES + list(device["features"].values()):
        if "name" not in feature:
            continue  # TODO we could display things based on UID?

        name = feature["name"]
        extra_payload_values = {}

        skip = False
        # Skip Programs without state
        for skip_entity in SKIP_ENTITIES:
            if name.startswith(skip_entity):
                skip = True

        if skip:
            continue

        disabled = False
        # Disable Refrigeration Status that isn't populated
        for disabled_entity in DISABLED_ENTITIES:
            if name.startswith(disabled_entity):
                disabled = True
                for disabled_exception in DISABLED_EXCEPTIONS:
                    if disabled_exception in name:
                        disabled = False

        if disabled:
            extra_payload_values["enabled_by_default"] = False

        friendly_name = name.split(".")[-1]

        # Use expand name if partial name is a known duplicate
        for key, value in EXPAND_NAME.items():
            if name.startswith(key):
                try:
                    parts = name.split(".")
                    friendly_name = ".".join(parts[value:])
                except Exception:
                    friendly_name = name
                break

        feature_id = name.lower().replace(".", "_")
        refCID = feature.get("refCID", None)
        refDID = feature.get("refDID", None)
        handling = feature.get("handling", None)
        access = feature.get("access", "").lower()
        available = feature.get("available", False)
        initValue = feature.get("initValue", None)
        values = feature.get("values", None)
        # fmt: off
        value_template = feature.get("template", (
            "{% if '" + name + "' in value_json %}\n"
            + "{{ value_json['" + name + "']|default }}\n"
            + "{% endif %}"
        ))
        # fmt: off
        state_topic = f"{mqtt_topic}/state"

        if (
            handling
            or refCID is None
            or (available and (access == "read" or access == "readwrite"))
        ):
            if refCID == "01" and refDID == "00":
                component_type = "binary_sensor"
                extra_payload_values["payload_on"] = True
                extra_payload_values["payload_on"] = False
            elif handling is not None:
                component_type = "event"
                extra_payload_values["event_types"] = list(values.values())
                extra_payload_values["platform"] = "event"
                # fmt: off
                value_template = (
                    "{ {% if '" + name + "' in value_json %}\n"
                    + '"event_type":"{{ value_json[\'' + name + "'] }}\"\n"
                    + "{% endif %} }"
                )
                # fmt: on
                state_topic = f"{mqtt_topic}/event"
            else:
                component_type = "sensor"
                if refCID == "03" and refDID == "80":
                    extra_payload_values = extra_payload_values | {
                        "device_class": "enum",
                        "options": list(values.values()),
                    }

            defaultValue = None
            if initValue is not None:
                if values is not None and initValue in values:
                    defaultValue = values[initValue]
                elif component_type == "binary_sensor":
                    if initValue.lower() == "true" or initValue.lower() == "false":
                        defaultValue = bool(initValue)
                    else:
                        defaultValue = initValue == "1"
                else:
                    defaultValue = initValue

            if component_type != "event" and defaultValue is not None:
                # fmt: off
                value_template = (
                    "{% if '" + name + "' in value_json %}\n"
                    + "{{ value_json['" + name + "']|default('" + str(defaultValue) + "') }}\n"
                    + "{% else %}\n"
                    + str(defaultValue) + "\n"
                    + "{% endif %}"
                )
                # fmt: on

            # Temperature Sensor (assuming C?)
            if refCID == "07" and refDID == "A4":
                extra_payload_values = extra_payload_values | {
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                }
            # Duration sensor e.g. Time Remaining
            elif refCID == "10" and refDID == "82":
                extra_payload_values = extra_payload_values | {
                    "unit_of_measurement": "s",
                    "device_class": "duration",
                }

            discovery_topic = (
                f"{HA_DISCOVERY_PREFIX}/{component_type}/hcpy/{device_ident}_{feature_id}/config"
            )

            discovery_payload = {
                "name": friendly_name,
                "device": device_info,
                "state_topic": state_topic,
                "availability_mode": "all",
                "availability": [{"topic": f"{base_topic}/LWT"}, {"topic": f"{mqtt_topic}/LWT"}],
                "value_template": value_template,
                "object_id": f"{device_ident}_{feature_id}",
                "unique_id": f"{device_ident}_{feature_id}",
                **extra_payload_values,
            }

            overrides = MAGIC_OVERRIDES.get(name)
            if overrides:
                payload_values = overrides.get("payload_values", {})
                # Overwrite keys with override values
                discovery_payload = discovery_payload | payload_values

            client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)
