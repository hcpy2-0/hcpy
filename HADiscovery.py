import json

import yaml

from HCSocket import now

CONTROL_COMPONENT_TYPES = ["switch", "number", "light", "button", "select"]


def publish_ha_discovery(discovery_yaml_path, device, client, mqtt_topic, events_as_sensors):
    config = None
    try:
        with open(discovery_yaml_path, "r") as yaml_config:
            config = yaml.safe_load(yaml_config)
    except Exception as e:
        print(now(), f"HADiscovery - unable to load {discovery_yaml_path}")
        print("\t", e)

    if config is None:
        print(now(), "HADiscovery - loading fallback discovery.yaml file")
        try:
            with open("discovery.yaml", "r") as yaml_config:
                config = yaml.safe_load(yaml_config)
        except Exception as e:
            print(now(), "HADiscovery - unable to load fallback discovery.yaml")
            print("\t", e)

    if config is None:
        print(now(), "HADiscovery - unable to load discovery config, aborting...")
        return

    HA_DISCOVERY_PREFIX = config.get("HA_DISCOVERY_PREFIX", "homeassistant")
    MAGIC_OVERRIDES = config.get("MAGIC_OVERRIDES", {})
    EXPAND_NAME = config.get("EXPAND_NAME", {})
    SKIP_ENTITIES = config.get("SKIP_ENTITIES", [])
    DISABLED_ENTITIES = config.get("DISABLED_ENTITIES", [])
    DISABLED_EXCEPTIONS = config.get("DISABLED_EXCEPTIONS", [])
    ADDITIONAL_FEATURES = config.get("ADDITIONAL_FEATURES", [])

    print(now(), f"HADiscovery - publishing MQTT discovery for {device['name']}")

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
        "suggested_area": "Kitchen",
    }

    local_control_lockout = False
    for key, value in device["features"].items():
        value["uid"] = key
        name = value.get("name", None)
        if name is not None and name == "BSH.Common.Status.LocalControlActive":
            print(now(), "HADiscovery - adding LocalControlActive availability topic")
            local_control_lockout = True

    for feature in ADDITIONAL_FEATURES + list(device["features"].values()):
        if "name" not in feature:
            continue  # TODO we could display things based on UID?

        name = feature["name"]

        skip = False
        # Skip Programs without state
        for skip_entity in SKIP_ENTITIES:
            if name.startswith(skip_entity):
                skip = True
            if (
                name == "BSH.Common.Root.ActiveProgram"
                or name == "BSH.Common.Root.SelectedProgram"
            ):
                skip = False

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
        value = feature.get("value", None)
        values = feature.get("values", None)
        state_topic = f"{mqtt_topic}/state/{feature_id}"
        step = feature.get("stepSize", None)

        discovery_payload = {
            "name": friendly_name,
            "device": device_info,
            "state_topic": state_topic,
            "availability_mode": "all",
            "availability": [{"topic": f"{base_topic}/LWT"}, {"topic": f"{mqtt_topic}/LWT"}],
            "object_id": f"{device_ident}_{feature_id}",
            "unique_id": f"{device_ident}_{feature_id}",
            "enabled_by_default": not disabled,
        }

        value_template = feature.get("value_template", None)
        if value_template:
            discovery_payload["value_template"] = value_template

        entity_category = feature.get("entity_category", None)
        if entity_category is not None:
            discovery_payload["entity_category"] = entity_category

        overrides = MAGIC_OVERRIDES.get(name, None)
        override_component_type = None
        if overrides:
            override_component_type = overrides.get("component_type", None)

        if (
            refCID == "01" and (refDID == "00" or refDID == "01")
        ) or override_component_type == "binary_sensor":
            component_type = "binary_sensor"
            discovery_payload["payload_on"] = True
            discovery_payload["payload_off"] = False
        elif handling is not None or override_component_type == "event":
            if events_as_sensors:
                component_type = "sensor"
                discovery_payload["value_template"] = "{{ value_json.event_type }}"
            else:
                component_type = "event"
                discovery_payload["event_types"] = list(values.values())
                discovery_payload["platform"] = "event"
                discovery_payload.pop("value_template", None)
                discovery_payload.pop("options", None)
            discovery_payload["state_topic"] = f"{mqtt_topic}/event/{feature_id}"
        else:
            component_type = "sensor"

        # Temperature
        if refCID == "07" and (refDID == "A4" or refDID == "A1"):
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
            or name == "BSH.Common.Option.ElapsedProgramTime"
            or name == "BSH.Common.Option.Duration"
        ):
            discovery_payload["unit_of_measurement"] = "s"
            discovery_payload["device_class"] = "duration"

        if name == "BSH.Common.Status.ProgramSessionSummary.Latest":
            value_template = "{{ value_json.counter }}"
            discovery_payload["force_update"] = True
            discovery_payload["value_template"] = value_template
            discovery_payload["json_attributes_topic"] = state_topic

        # Setup Controllable options
        # Access can be read, readwrite, writeonly, none
        if (
            (uid is not None) and (access == "writeonly" or access == "readwrite")
        ) or override_component_type in CONTROL_COMPONENT_TYPES:
            # 01/00 is binary true/false
            # 01/01 is binary true/false only seen for Cooking.Common.Setting.ButtonTones
            # 15/81 is accept/reject event - maybe it needs the event ID rather than true/false?
            if (
                (refCID == "01" and (refDID == "00" or refDID == "01"))
                or (refCID == "15" and refDID == "81")
                or override_component_type in ["button", "switch", "light"]
            ):
                if override_component_type == "light":
                    component_type = "light"
                elif access == "writeonly" or override_component_type == "button":
                    component_type = "button"
                    discovery_payload["command_topic"] = f"{mqtt_topic}/set"
                    discovery_payload["payload_press"] = f'[{{"uid":{uid},"value":true}}]'
                    discovery_payload.pop("value_template", None)
                else:
                    component_type = "switch"
                    discovery_payload["command_topic"] = f"{mqtt_topic}/set"
                    discovery_payload["state_on"] = True
                    discovery_payload["state_off"] = False
                    discovery_payload["payload_on"] = f'[{{"uid":{uid},"value":true}}]'
                    discovery_payload["payload_off"] = f'[{{"uid":{uid},"value":false}}]'
            # 03/80 are enums
            elif (
                refCID == "03"
                and refDID == "80"
                and len(values.values()) == 2
                and "On" in values.values()
                and "Off" in values.values()
            ):
                # some enums are just on/off so can be a binary_switch
                component_type = "switch"
                discovery_payload["command_topic"] = f"{mqtt_topic}/set"
                discovery_payload["state_on"] = "On"
                discovery_payload["state_off"] = "Off"
                discovery_payload["payload_on"] = f'[{{"uid":{uid},"value":"On"}}]'
                discovery_payload["payload_off"] = f'[{{"uid":{uid},"value":"Off"}}]'
                discovery_payload["device_class"] = "switch"
            elif refCID == "03" and refDID == "80":
                component_type = "select"
                discovery_payload["command_topic"] = f"{mqtt_topic}/set"
                template = f'[{{"uid":{uid},"value":"{{{{value}}}}"}}]'
                discovery_payload["command_template"] = template
            # numbers
            elif (
                (refCID == "07" and refDID == "A1")
                or (refCID == "07" and refDID == "A4")
                or (refCID == "11" and refDID == "A0")
                or (refCID == "11" and refDID == "80")
                or (refCID == "14" and refDID == "80")
                or (refCID == "02" and refDID == "80")
                or (refCID == "81" and refDID == "60")
                or (refCID == "10" and refDID == "81")
                or (refCID == "10" and refDID == "82" and access == "readWrite")
            ):
                component_type = "number"
                discovery_payload["command_topic"] = f"{mqtt_topic}/set"
                template = f'[{{"uid":{uid},"value":{{{{value}}}}}}]'
                discovery_payload["command_template"] = template

                minimum = feature.get("min", None)
                maximum = feature.get("max", None)
                if minimum is not None:
                    discovery_payload["min"] = minimum
                if maximum is not None:
                    discovery_payload["max"] = maximum
                if step is not None:
                    discovery_payload["step"] = float(step)

        if (
            name == "BSH.Common.Root.ActiveProgram"
            or name == "BSH.Common.Root.SelectedProgram"
            or name == "BSH.Common.Option.BaseProgram"
        ):
            component_type = "select"
            options = []
            for k, v in device["features"].items():
                if "name" in v and (
                    "Dishcare.Dishwasher.Program." in v["name"]
                    or "Cooking.Common.Program.Hood." in v["name"]
                    or "ConsumerProducts.CoffeeMaker.Program." in v["name"]
                    or "ConsumerProducts.CleaningRobot.Program." in v["name"]
                    or "LaundryCare.Dryer.Program." in v["name"]
                    or "LaundryCare.Washer.Program." in v["name"]
                    or "LaundryCare.WasherDryer.Program." in v["name"]
                    or "Cooking.Oven.Program." in v["name"]
                    or "BSH.Common.Program.Favorite." in v["name"]
                ):
                    options.append(v["name"].split(".")[-1])

            if len(options) < 1:
                continue

            discovery_payload["options"] = options
            discovery_payload["command_template"] = '[{"program":"{{value}}","options":[]}]'
            if name == "BSH.Common.Root.ActiveProgram":
                discovery_payload["command_topic"] = f"{mqtt_topic}/activeProgram"
            elif name == "BSH.Common.Root.SelectedProgram":
                discovery_payload["command_topic"] = f"{mqtt_topic}/selectedProgram"
            elif name == "BSH.Common.Option.BaseProgram":
                discovery_payload["command_template"] = (
                    f'[{{"uid":{uid},"value":"{{{{value}}}}"}}]'
                )
                discovery_payload["command_topic"] = f"{mqtt_topic}/set"

        if component_type in CONTROL_COMPONENT_TYPES:
            if local_control_lockout:
                discovery_payload["availability"] = discovery_payload["availability"] + [
                    {
                        "topic": f"{mqtt_topic}/state/bsh_common_status_localcontrolactive",
                        "payload_available": "False",
                        "payload_not_available": "True",
                    }
                ]

        discovery_topic = (
            f"{HA_DISCOVERY_PREFIX}/{component_type}/hcpy/{device_ident}_{feature_id}/config"
        )

        if overrides:
            # Overwrite keys with override values
            for k, v in overrides.items():
                if isinstance(v, str):
                    overrides[k] = v.replace("DEVICE_NAME", device_ident)
            discovery_payload = discovery_payload | overrides

        client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)
