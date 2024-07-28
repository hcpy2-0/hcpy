import json
import re

from HCSocket import now


def decamelcase(str):
    split = re.findall(r'[A-Z](?:[a-z]+|[A-Z]*(?=[A-Z]|$))', str)
    return f"{split[0]} {' '.join(split[1:]).lower()}".strip()


HA_DISCOVERY_PREFIX = "homeassistant"


def publish_ha_states(state, client, mqtt_topic):
    for key, value in state.items():
        state_topic = f"{mqtt_topic}/{key}"
        print(f"{now()} Publishing state for {key} at {state_topic}")
        client.publish(state_topic, json.dumps(value))


def publish_ha_discovery(device, client, mqtt_topic):
    print(f"{now()} Publishing HA discovery for {device}")

    device_ident = device["host"]
    device_name = device["name"]
    device_description = device.get("description", {})

    version_parts = filter(
        lambda d : d is not None,
        [
            device_description.get("version"),
            device_description.get("revision")
        ]
    )

    device_info = {
        "identifiers": [device_ident],
        "name": device_name,
        "manufacturer": device_description.get("brand"),
        "model": device_description.get("model"),
        "sw_version": ".".join(version_parts)
    }

    for feature in device["features"].values():
        name_parts = feature["name"].split(".")
        name = name_parts[-1]
        feature_type = name_parts[-2]
        access = feature.get("access", "none")
        available = feature.get("available", False)

        if (feature_type == "Setting" and available and (access == "read" or access == "readWrite")) or \
            feature_type == "Event" or \
            feature_type == "Option":

            component_type = "sensor" # TODO use appropriate types

            discovery_topic = f"{HA_DISCOVERY_PREFIX}/{component_type}/hcpy/{device_ident}_{name}/config"
            state_topic = f"{mqtt_topic}/{name}"
            # print(discovery_topic, state_topic)

            discovery_payload = json.dumps({
                "name": decamelcase(name),
                "device": device_info,
                "state_topic": state_topic,
                "object_id": f"{device_ident}_{name}",
                "unique_id": f"{device_ident}_{name}",
            })
            print(discovery_topic)
            # print(discovery_payload)

            client.publish(discovery_topic, discovery_payload, retain=True)
