import json
import re

from HCSocket import now


def decamelcase(str):
    split = re.findall(r"[A-Z](?:[a-z]+|[A-Z]*(?=[A-Z]|$))", str)
    return f"{split[0]} {' '.join(split[1:]).lower()}".strip()


HA_DISCOVERY_PREFIX = "homeassistant"

# These "magic overrides" provide HA MQTT autodiscovery data.
MAGIC_OVERRIDES = {
    'BSH.Common.Option.ProgramProgress': {
        "payload_values": {"unit_of_measurement": "%"}
    }, 
    'BSH.Common.Option.RemainingProgramTime': { 
        "payload_values": {"unit_of_measurement": "s", "device_class": "duration"}
    },
    'BSH.Common.Option.StartInRelative': {
        "payload_values": {"unit_of_measurement": "s", "device_class": "duration"}
    },
}


def augment_device_features(features):
    for id, feature in features.items():
        if id in MAGIC_OVERRIDES:
            feature["discovery"] = MAGIC_OVERRIDES[id]
        # else:
        #     print(f"No discovery information for: {id} => {feature['name']}", file=sys.stderr)
    return features


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

    for feature in device["features"].values():
        if "name" not in feature:
            continue # TODO we could display things based on UID
        
        name_parts = feature["name"].split(".")
        name = feature["name"]
        extra_payload_values = {}

        # Skip Dishwasher Programs
        if ("Dishcare.Dishwasher.Program." in name or
            "BSH.Common.Root." in name):
            continue

        # Disable Refrigeration Status that isn't populated
        if "Refrigeration.Common.Status." in name:
            if not "Refrigeration.Common.Status.Door." in name:
                extra_payload_values["enabled_by_default"] = False

        feature_id = name.lower().replace(".", "_")
        refCID = feature.get("refCID", None)
        refDID = feature.get("refDID", None)
        handling = feature.get("handling", None)
        access = feature.get("access", "").lower()
        available = feature.get("available", False)
        initValue = feature.get("initValue", None)
        values = feature.get("values", None)
        event_types = None
        value_template = "{% if '" + name + "' in value_json %}\n{{ value_json['" + name + "']|default }}\n{% endif %}"
        state_topic = f"{mqtt_topic}/state"


        if handling or refCID is None or (available and (access == "read" or access == "readwrite")): 
            if refCID == "01" and refDID == "00":
                component_type = "binary_sensor"
                extra_payload_values["payload_on"] = True
                extra_payload_values["payload_on"] = False
            elif handling is not None:
                component_type = "event"
                extra_payload_values["event_types"] = list(values.values())
                extra_payload_values["platform"] = "event"
                value_template = "{ {% if '" + name + "' in value_json %}\n\"event_type\":\"{{ value_json['" + name + "'] }}\"\n{% endif %} }"
                state_topic = f"{mqtt_topic}/event"
            else:
                component_type = "sensor"


            defaultValue = None
            if initValue is not None:
                if values is not None and initValue in values:
                    defaultValue = values[initValue]
                elif component_type == "binary_sensor":
                    defaultValue = initValue == "1"

            if component_type is not "event" and defaultValue is not None:
                value_template = "{% if '" + name + "' in value_json %}\n{{ value_json['" + name + "']|default('" + str(defaultValue) + "') }}\n{% endif %}"

            # Temperature Sensor (assuming C?)
            if refCID == "07" and refDID == "A4":
                extra_payload_values = extra_payload_values | {"unit_of_measurement": "°C", "device_class": "temperature"}
            elif refCID == "10" and refDID == "82":
                extra_payload_values = extra_payload_values | {"unit_of_measurement": "s", "device_class": "duration"}

#            component_type = overrides.get("component_type", default_component_type)

            discovery_topic = (
                f"{HA_DISCOVERY_PREFIX}/{component_type}/hcpy/{device_ident}_{feature_id}/config"
            )

            discovery_payload = {
                "name": name,
                "device": device_info,
                "state_topic": state_topic,
                "availability_mode": "all",
                "availability": [{"topic":f"{base_topic}/LWT"}, {"topic":f"{mqtt_topic}/LWT"}],
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
