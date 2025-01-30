import json
import re

from HCSocket import now


def decamelcase(str):
    split = re.findall(r"[A-Z](?:[a-z]+|[A-Z]*(?=[A-Z]|$))", str)
    return f"{split[0]} {' '.join(split[1:]).lower()}".strip()


HA_DISCOVERY_PREFIX = "homeassistant"


# These "magic overrides" provide HA MQTT autodiscovery data that is injected
# into devices.json when `hc-login.py` is run; the data is then read from
# devices.json at runtime.
#
# Note: keys should be integer (not string) taken from a device's feature
# mapping.
MAGIC_OVERRIDES = {
    3: {  # BSH.Common.Setting.AllowBackendConnection
        "component_type": "binary_sensor",
        "payload_values": {"payload_on": True, "payload_off": False},
    },
    5: {  # BSH.Common.Status.BackendConnected
        "component_type": "binary_sensor",
        "payload_values": {
            "device_class": "connectivity",
            "payload_on": True,
            "payload_off": False,
        },
    },
    21: {  # BSH.Common.Event.SoftwareUpdateAvailable
        "component_type": "binary_sensor",
        "payload_values": {"device_class": "update", "payload_on": "Present"},
    },
    517: {  # BSH.Common.Status.RemoteControlStartAllowed
        "component_type": "binary_sensor",
        "payload_values": {"payload_on": True, "payload_off": False},
    },
    523: {  # BSH.Common.Status.RemoteControlActive
        "component_type": "binary_sensor",
        "payload_values": {"payload_on": True, "payload_off": False},
    },
    524: {  # BSH.Common.Setting.ChildLock
        "component_type": "binary_sensor",
        "payload_values": {
            "device_class": "lock",
            "payload_on": False,  # Lock "on" means "unlocked" to HA
            "payload_off": True,  # Lock "off" means "locked"
        },
    },
    525: {  # BSH.Common.Event.AquaStopOccured
        "component_type": "binary_sensor",
        "payload_values": {"device_class": "problem", "payload_on": "Present"},
    },
    527: {  # BSH.Common.Status.DoorState
        "component_type": "binary_sensor",
        "payload_values": {"device_class": "door", "payload_on": "Open", "payload_off": "Closed"},
    },
    539: {  # BSH.Common.Setting.PowerState
        "component_type": "binary_sensor",
        "payload_values": {"device_class": "power"},
    },
    542: {"payload_values": {"unit_of_measurement": "%"}},  # BSH.Common.Option.ProgramProgress
    543: {  # BSH.Common.Event.LowWaterPressure
        "component_type": "binary_sensor",
        "payload_values": {"device_class": "problem", "payload_on": "Present"},
    },
    544: {  # BSH.Common.Option.RemainingProgramTime
        "payload_values": {"unit_of_measurement": "s", "device_class": "duration"}
    },
    549: {  # BSH.Common.Option.RemainingProgramTimeIsEstimated
        "component_type": "binary_sensor",
        "payload_values": {"payload_on": True, "payload_off": False},
    },
    558: {  # BSH.Common.Option.StartInRelative
        "payload_values": {"unit_of_measurement": "s", "device_class": "duration"}
    },
    4101: {  # Dishcare.Dishwasher.Status.SilenceOnDemandRemainingTime
        "payload_values": {"unit_of_measurement": "s", "device_class": "duration"}
    },
    4103: {  # Dishcare.Dishwasher.Status.EcoDryActive
        "component_type": "binary_sensor",
        "payload_values": {"payload_on": True, "payload_off": False},
    },
    4382: {  # Dishcare.Dishwasher.Status.SilenceOnDemandDefaultTime
        "payload_values": {"unit_of_measurement": "s", "device_class": "duration"}
    },
    4384: {  # Dishcare.Dishwasher.Setting.SpeedOnDemand
        "component_type": "binary_sensor",
        "payload_values": {"payload_on": True, "payload_off": False},
    },
    4608: {  # Dishcare.Dishwasher.Event.InternalError
        "component_type": "binary_sensor",
        "payload_values": {"device_class": "problem", "payload_on": "Present"},
    },
    4609: {  # Dishcare.Dishwasher.Event.CheckFilterSystem
        "component_type": "binary_sensor",
        "payload_values": {"device_class": "problem", "payload_on": "Present"},
    },
    4610: {  # Dishcare.Dishwasher.Event.DrainingNotPossible
        "component_type": "binary_sensor",
        "payload_values": {"device_class": "problem", "payload_on": "Present"},
    },
    4611: {  # Dishcare.Dishwasher.Event.DrainPumpBlocked
        "component_type": "binary_sensor",
        "payload_values": {"device_class": "problem", "payload_on": "Present"},
    },
    4612: {  # Dishcare.Dishwasher.Event.WaterheaterCalcified
        "component_type": "binary_sensor",
        "payload_values": {"device_class": "problem", "payload_on": "Present"},
    },
    4613: {  # Dishcare.Dishwasher.Event.LowVoltage
        "component_type": "binary_sensor",
        "payload_values": {"device_class": "problem", "payload_on": "Present"},
    },
    4624: {  # Dishcare.Dishwasher.Event.SaltLack
        "component_type": "binary_sensor",
        "payload_values": {"device_class": "problem", "payload_on": "Present"},
    },
    4625: {  # Dishcare.Dishwasher.Event.RinseAidLack
        "component_type": "binary_sensor",
        "payload_values": {"device_class": "problem", "payload_on": "Present"},
    },
    4626: {  # Dishcare.Dishwasher.Event.SaltNearlyEmpty
        "component_type": "binary_sensor",
        "payload_values": {"device_class": "problem", "payload_on": "Present"},
    },
    4627: {  # Dishcare.Dishwasher.Event.RinseAidNearlyEmpty
        "component_type": "binary_sensor",
        "payload_values": {"device_class": "problem", "payload_on": "Present"},
    },
    5121: {  # Dishcare.Dishwasher.Option.ExtraDry
        "component_type": "binary_sensor",
        "payload_values": {"payload_on": True, "payload_off": False},
    },
    5124: {  # Dishcare.Dishwasher.Option.HalfLoad
        "component_type": "binary_sensor",
        "payload_values": {"payload_on": True, "payload_off": False},
    },
    5127: {  # Dishcare.Dishwasher.Option.VarioSpeedPlus
        "component_type": "binary_sensor",
        "payload_values": {"payload_on": True, "payload_off": False},
    },
    5136: {  # Dishcare.Dishwasher.Option.SilenceOnDemand
        "component_type": "binary_sensor",
        "payload_values": {"payload_on": True, "payload_off": False},
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
    print(f"{now()} Publishing HA discovery for {device}")

    device_ident = device["name"]
    device_description = device.get("description", {})

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
            continue
        name_parts = feature["name"].split(".")
        name = name_parts[-1]
        feature_type = name_parts[-2]
        access = feature.get("access", "none")
        available = feature.get("available", False)

        if (
            (
                feature_type == "Setting"
                and available
                and (access == "read" or access == "readWrite")
            )
            or (
                feature_type == "Status"
                and available
                and (access == "read" or access == "readWrite")
            )
            or feature_type == "Event"
            or feature_type == "Option"
        ):

            default_component_type = "binary_sensor" if feature_type == "Event" else "sensor"

            overrides = feature.get("discovery", {})

            component_type = overrides.get("component_type", default_component_type)

            extra_payload_values = overrides.get("payload_values", {})

            discovery_topic = (
                f"{HA_DISCOVERY_PREFIX}/{component_type}/hcpy/{device_ident}_{name}/config"
            )
            # print(discovery_topic, state_topic)

            discovery_payload = {
                "name": decamelcase(name),
                "device": device_info,
                "state_topic": f"{mqtt_topic}/state",
                # "availability_topic": f"{mqtt_topic}/LWT",
                # # I found the behaviour of `availability_topic` unsatisfactory -
                # # since it would set all device attributes to "unavailable"
                # # then back to their correct values on every disconnect/
                # # reconnect. This leaves a lot of noise in the HA history, so
                # # I felt things were better off without an `availability_topic`.
                "value_template": "{{value_json." + name + " | default('unavailable')}}",
                "object_id": f"{device_ident}_{name}",
                "unique_id": f"{device_ident}_{name}",
                **extra_payload_values,
            }

            if component_type == "binary_sensor":
                discovery_payload.setdefault("payload_on", "On")
                discovery_payload.setdefault("payload_off", "Off")

            # print(discovery_topic)
            # print(discovery_payload)

            client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)
