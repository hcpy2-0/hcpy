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
WRITEABLE_ENTITIES = []  # config.get("WRITEABLE_ENTITIES", [])


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

    for key, value in device["features"].items():
        value["uid"] = key

    for feature in ADDITIONAL_FEATURES + list(device["features"].values()):
        if "name" not in feature:
            continue  # TODO we could display things based on UID?

        name = feature["name"]

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

        uid = feature.get("uid", None)
        feature_id = name.lower().replace(".", "_")
        refCID = feature.get("refCID", None)
        refDID = feature.get("refDID", None)
        handling = feature.get("handling", None)
        access = feature.get("access", "").lower()
        # available = feature.get("available", False)
        initValue = feature.get("initValue", None)
        value = feature.get("value", None)
        values = feature.get("values", None)
        # fmt: off
        value_template = feature.get("template", (
            "{% if '" + name + "' in value_json %}\n"
            + "{{ value_json['" + name + "']|default }}\n"
            + "{% endif %}"
        ))
        # fmt: off
        state_topic = f"{mqtt_topic}/state"

        discovery_payload = {
            "name": friendly_name,
            "device": device_info,
            "state_topic": state_topic,
            "availability_mode": "all",
            "availability": [{"topic": f"{base_topic}/LWT"}, {"topic": f"{mqtt_topic}/LWT"}],
            "object_id": f"{device_ident}_{feature_id}",
            "unique_id": f"{device_ident}_{feature_id}",
            "value_template": value_template,
            "enabled_by_default": not disabled
        }

        if refCID == "01" and (refDID == "00" or refDID == "01"):
            component_type = "binary_sensor"
            discovery_payload["payload_on"] = True
            discovery_payload["payload_off"] = False
        elif handling is not None:
            component_type = "event"
            discovery_payload["event_types"] = list(values.values())
            discovery_payload["platform"] = "event"
            # fmt: off
            discovery_payload["value_template"] = (
                "{ {% if '" + name + "' in value_json %}\n"
                + '"event_type":"{{ value_json[\'' + name + "'] }}\"\n"
                + "{% endif %} }"
            )
            # fmt: on
            discovery_payload["state_topic"] = f"{mqtt_topic}/event"
        else:
            component_type = "sensor"

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
            discovery_payload["value_template"] = (
                "{% if '" + name + "' in value_json %}\n"
                + "{{ value_json['" + name + "']|default('" + str(defaultValue) + "') }}\n"
                + "{% else %}\n"
                + str(defaultValue) + "\n"
                + "{% endif %}"
            )
            # fmt: on

        # Temperature
        if refCID == "07" and refDID == "A4":
            discovery_payload["unit_of_measurement"] = "°C"
            discovery_payload["device_class"] = "temperature"
            discovery_payload["icon"] = "mdi:thermometer"
        elif refCID == "03" and refDID == "80":
            if component_type != "event":
                discovery_payload["device_class"] = "enum"
            discovery_payload["options"] = list(values.values())
        # Duration sensor e.g. Time Remaining
        elif (
                (refCID == "10" and refDID == "82")
                or name == 'BSH.Common.Option.ElapsedProgramTime'
                or name == 'BSH.Common.Option.Duration'
        ):
            discovery_payload["unit_of_measurement"] = "s"
            discovery_payload["device_class"] = "duration"
        elif name == 'rssi':
            discovery_payload["unit_of_measurement"] = "dBm"
            discovery_payload["icon"] = "mdi:wifi"

        # Setup Controllable options
        # Access can be read, readwrite, writeonly, none
        if (
                ((uid is not None) and (access == "writeonly" or access == "readwrite"))
                or name in WRITEABLE_ENTITIES
        ):
            # 01/00 is binary true/false
            # 01/01 is binary true/false only seen for Cooking.Common.Setting.ButtonTones
            # 15/81 is accept/reject event - maybe it needs the event ID rather than true/false?
            if (
                    (refCID == "01" and (refDID == "00" or refDID == "01"))
                    or (refCID == "15" and refDID == "81")
            ):
                if access == "writeonly":
                    component_type = "button"
                    discovery_payload["command_topic"] = f"{mqtt_topic}/set"
                    discovery_payload["payload_press"] = f"[{{\"uid\":{uid},\"value\":true}}]"
                    discovery_payload.pop('value_template', None)
                else:
                    component_type = "switch"
                    discovery_payload["command_topic"] = f"{mqtt_topic}/set"
                    discovery_payload["state_on"] = True
                    discovery_payload["state_off"] = False
                    discovery_payload["payload_on"] = f"[{{\"uid\":{uid},\"value\":true}}]"
                    discovery_payload["payload_off"] = f"[{{\"uid\":{uid},\"value\":false}}]"
            # 03/80 are enums
            elif (
                refCID == "03"
                and refDID == "80"
                and len(values.values()) == 2
                and "On" in values.values()
                and "Off" in values.values()
            ):
                component_type = "switch"
                discovery_payload["command_topic"] = f"{mqtt_topic}/set"
                discovery_payload["state_on"] = "On"
                discovery_payload["state_off"] = "Off"
                discovery_payload["payload_on"] = f"[{{\"uid\":{uid},\"value\":\"On\"}}]"
                discovery_payload["payload_off"] = f"[{{\"uid\":{uid},\"value\":\"Off\"}}]"
                discovery_payload["device_class"] = "switch"
            elif refCID == "03" and refDID == "80":
                component_type = "select"
                discovery_payload["command_topic"] = f"{mqtt_topic}/set"
                template = f"[{{\"uid\":{uid},\"value\":\"{{{{value}}}}\"}}]"
                discovery_payload["command_template"] = template
            # numbers
            elif (
                    (refCID == "07" and refDID == "A4")
                    or (refCID == "11" and refDID == "A0")
                    or (refCID == "02" and refDID == "80")
                    or (refCID == "81" and refDID == "60")
                    or (refCID == "10" and refDID == "81")
            ):
                component_type = "number"
                discovery_payload["command_topic"] = f"{mqtt_topic}/set"
                template = f"[{{\"uid\":{uid},\"value\":{{{{value}}}}}}]"
                discovery_payload["command_template"] = template

                minimum = feature.get("min", None)
                maximum = feature.get("max", None)
                step = feature.get("stepSize", None)
                if minimum is not None:
                    discovery_payload["min"] = minimum
                if maximum is not None:
                    discovery_payload["max"] = maximum
                if step is not None:
                    discovery_payload["step"] = step

        discovery_topic = (
            f"{HA_DISCOVERY_PREFIX}/{component_type}/hcpy/{device_ident}_{feature_id}/config"
        )

        overrides = MAGIC_OVERRIDES.get(name, None)
        if overrides:
            # Overwrite keys with override values
            discovery_payload = discovery_payload | overrides

        client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)
