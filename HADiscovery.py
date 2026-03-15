import json

import yaml

from HCSocket import now

CONTROL_COMPONENT_TYPES = ["switch", "number", "light", "button", "select"]


def publish_ha_discovery(
    discovery_yaml_path, device, device_state, client, mqtt_topic, events_as_sensors
):
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
    base_topic = mqtt_topic.split("/")[0]

    device_type = device_state.get("deviceType")
    vib = device_state.get("vib")
    brand = device_state.get("brand")

    if device_type and vib:
        model = f"{device_type} ({vib})"
    elif vib:
        model = vib
    else:
        model = None

    manufacturer = brand.title() if brand else None
    sw_version = str(device_state["swVersion"]) if device_state.get("swVersion") else None
    hw_version = str(device_state["hwVersion"]) if device_state.get("hwVersion") else None

    # Extract MAC from runtime state for HA device registry connections.
    connections = []
    if "mac" in device_state:
        mac = device_state["mac"]
        if mac:
            mac_normalized = mac.replace("-", ":").lower()
            connections.append(["mac", mac_normalized])

    device_info = {
        "identifiers": [device_ident],
        "name": device_ident,
        "suggested_area": "Kitchen",
    }

    if manufacturer:
        device_info["manufacturer"] = manufacturer
    if model:
        device_info["model"] = model
    if sw_version:
        device_info["sw_version"] = sw_version
    if hw_version:
        device_info["hw_version"] = hw_version

    if connections:
        device_info["connections"] = connections

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

        discovery_payload = {
            "name": friendly_name,
            "device": device_info,
            "state_topic": state_topic,
            "availability_mode": "all",
            "availability": [{"topic": f"{base_topic}/LWT"}, {"topic": f"{mqtt_topic}/LWT"}],
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
        elif refDID == "80" and (refCID in ("02", "03")) and values is not None:
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
            # Cooking.Oven.Setting.Cavity.001.AlarmClock doesnt set min/max
            # HA default of 1,100 is too small so warnings raised.
            # Duration often has a min value of 1 but will be set to 0 by device
            discovery_payload["min"] = float(0)
            discovery_payload["max"] = float(feature.get("max", 86400))

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
                and values is not None
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
            # 02/80 can be an enum e.g. Cooking.Oven.Option.Doneness
            elif refDID == "80" and (refCID in ("02", "03")) and values is not None:
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
                # 02/80 can be a number e.g. Cooking.Oven.Setting.DisplayBrightness
                or (refCID == "02" and refDID == "80")
                or (refCID == "81" and refDID == "60")
                or (refCID == "10" and refDID == "81")
                or (refCID == "10" and refDID == "82")
                or override_component_type == "number"
            ):
                component_type = "number"
                discovery_payload["command_topic"] = f"{mqtt_topic}/set"
                template = f'[{{"uid":{uid},"value":{{{{value}}}}}}]'
                discovery_payload["command_template"] = template

                # Min/Max may be already set for durations above
                minimum = feature.get("min", None)
                if discovery_payload.get("min") is None and minimum is not None:
                    discovery_payload["min"] = float(minimum)

                maximum = feature.get("max", None)
                if discovery_payload.get("max") is None and maximum is not None:
                    discovery_payload["max"] = float(maximum)

                step = feature.get("stepSize", None)
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

        discovery_payload["default_entity_id"] = (
            f"{component_type}.{discovery_payload['unique_id']}"
        )

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
