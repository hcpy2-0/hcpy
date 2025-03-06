#!/usr/bin/env python3
# Parse messages from a Home Connect websocket (HCSocket)
# and keep the connection alive
#
# Possible resources to fetch from the devices:
#
# /ro/values
# /ro/descriptionChange
# /ro/allMandatoryValues
# /ro/allDescriptionChanges
# /ro/activeProgram
# /ro/selectedProgram
#
# /ei/initialValues
# /ei/deviceReady
#
# /ci/services
# /ci/registeredDevices
# /ci/pairableDevices
# /ci/delregistration
# /ci/networkDetails
# /ci/networkDetails2
# /ci/wifiNetworks
# /ci/wifiSetting
# /ci/wifiSetting2
# /ci/tzInfo
# /ci/authentication
# /ci/register
# /ci/deregister
#
# /ce/serverDeviceType
# /ce/serverCredential
# /ce/clientCredential
# /ce/hubInformation
# /ce/hubConnected
# /ce/status
#
# /ni/config
# /ni/info
#
# /iz/services

import json
import re
import sys
import threading
import time
import traceback
from base64 import urlsafe_b64encode as base64url_encode
from datetime import datetime

from Crypto.Random import get_random_bytes


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")


class HCDevice:
    def __init__(self, ws, device, debug=False):
        self.ws = ws
        self.features_lock = threading.Lock()
        self.features = device.get("features")
        self.name = device.get("name")
        self.session_id = None
        self.tx_msg_id = None
        self.device_name = "hcpy"
        self.device_id = "0badcafe"
        self.debug = debug
        self.services_initialized = False
        self.services = {}
        self.token = None
        self.connected = False
        self.state_lock = threading.Lock()
        self.state = {}
        self.set_init_feature_values()

    def set_init_feature_values(self):
        with self.features_lock:
            for uid, feature in self.features.items():
                name = feature.get("name")
                if name is None:
                    continue

                initValue = feature.get("initValue", None)
                values = feature.get("values", None)
                refCID = feature.get("refCID", None)
                refDID = feature.get("refDID", None)

                with self.state_lock:
                    if initValue is not None and values is not None:
                        self.state[name] = values.get(initValue, None)
                    elif initValue is not None and refCID == "00" and refDID == "01":
                        if initValue.lower() == "true" or initValue.lower() == "false":
                            self.state[name] = initValue
                        elif initValue == "1":
                            self.state[name] = "True"
                        elif initValue == "0":
                            self.state[name] = "False"

    def get_feature_uid(self, name):
        uid = None
        with self.features_lock:
            for k, v in self.features.items():
                if "name" in v and name in v["name"]:
                    uid = k
                    break

        return uid

    def get_feature_name(self, uid):
        name = None
        uid = str(uid)
        with self.features_lock:
            if uid in self.features:
                feature = self.features.get(uid, None)
                if feature is not None:
                    name = feature.get("name", None)

        return name

    def parse_values(self, values):
        if not self.features:
            return values

        result = {}

        for msg in values:
            uid = str(msg["uid"])
            value = msg.get("value", None)

            if value is None:
                continue

            value_str = str(value)

            name = uid
            feature = None
            with self.features_lock:
                if uid in self.features:
                    feature = self.features[uid]

            if feature:
                if "name" in feature:
                    name = feature["name"]

                if "values" in feature:
                    # Convert index values to their named equivalent
                    value = feature["values"].get(value_str, None)

                refCID = feature.get("refCID", None)
                refDID = feature.get("refDID", None)

                if refCID == "01" and refDID == "00":
                    value = value_str.lower() in ("1", "true", "on")

                if (
                    name == "BSH.Common.Root.SelectedProgram"
                    or name == "BSH.Common.Root.ActiveProgram"
                ):
                    # Convert the returned value to a program name
                    value = self.get_feature_name(value_str)

            result[name] = value

        return result

    # Based on PR submitted https://github.com/Skons/hcpy/pull/1
    def test_program_data(self, data_array):
        for data in data_array:
            if "program" not in data:
                raise TypeError("Message data invalid, no program specified.")
            else:
                program = data["program"]

            if isinstance(program, int) or program.isdigit():
                # devices.json stores UID as string
                name = self.get_feature_name(program)
                if name is None:
                    raise ValueError(
                        f"Unable to configure appliance. Program UID {program} is not valid"
                        " for this device."
                    )
                else:
                    if ".Program." not in name:
                        raise ValueError(
                            f"Unable to configure appliance. Program UID {program} is not a valid"
                            f" program - {name}."
                        )
            else:
                uid = self.get_feature_uid(program)

                if uid is not None:
                    data["program"] = int(uid)
                else:
                    raise ValueError(
                        f"Unable to configure appliance. Program {program} is an unknown program."
                    )

            if "options" in data:
                for option in data["options"]:
                    option_uid = option["uid"]
                    if str(option_uid) not in self.features:
                        raise ValueError(
                            f"Unable to configure appliance. Option UID {option_uid} is not"
                            " valid for this device."
                        )
        return data_array

    # Test the feature of an appliance agains a data object
    def test_feature(self, data_array):
        for data in data_array:
            if "uid" not in data:
                raise Exception("Unable to configure appliance. UID is required.")

            if isinstance(data["uid"], int) is False:
                raise Exception("Unable to configure appliance. UID must be an integer.")

            if "value" not in data:
                raise Exception("Unable to configure appliance. Value is required.")

            # Check if the uid is present for this appliance
            uid = str(data["uid"])
            with self.features_lock:
                if uid not in self.features:
                    raise Exception(f"Unable to configure appliance. UID {uid} is not valid.")

                feature = self.features[uid]

                # check the access level of the feature
                self.print(f"Processing feature {feature['name']} with uid {uid}")
                if "access" not in feature:
                    self.print(
                        f"Feature {feature['name']} with uid {uid} does not have access."
                        "Attempting to send instruction anyway."
                    )
                else:
                    access = feature["access"].lower()
                    if access != "readwrite" and access != "writeonly":
                        self.print(
                            f"Feature {feature['name']} with uid {uid} "
                            f"has got access {feature['access']}."
                            "Attempting to send instruction anyway."
                        )

                # check if selected list with values is allowed
                if "values" in feature:
                    if (
                        isinstance(data["value"], int) is False
                        and data["value"].isdigit() is False
                    ):
                        try:
                            key = next(
                                key
                                for key, value in feature["values"].items()
                                if value == data["value"]
                            )
                            data["value"] = int(key)
                        except StopIteration:
                            raise Exception(
                                f"Unable to configure appliance. The value {data['value']} must "
                                f"be in the allowed values {feature['values']}."
                            )
                    elif isinstance(data["value"], int) is False and data["value"].isdigit():
                        data["value"] = int(data["value"])

                    # values are strings in the feature list,
                    # but always seem to be an integer. An integer must be provided
                    if str(data["value"]) not in feature["values"]:
                        raise Exception(
                            "Unable to configure appliance. "
                            f"Value {data['value']} is not a valid value. "
                            f"Allowed values are {feature['values']}. "
                        )

                if "min" in feature:
                    min = int(feature["min"])
                    max = int(feature["max"])
                    if (
                        isinstance(data["value"], int) is False
                        or data["value"] < min
                        or data["value"] > max
                    ):
                        raise Exception(
                            "Unable to configure appliance. "
                            f"Value {data['value']} is not a valid value. "
                            f"The value must be an integer in the range {min} and {max}."
                        )

        return data_array

    def recv(self):
        try:
            buf = self.ws.recv()
            if buf is None:
                return None
        except Exception as e:
            raise e

        try:
            return self.handle_message(buf)
        except Exception as e:
            self.print("error handling msg", e, buf, traceback.format_exc())
            return None

    # reply to a POST or GET message with new data
    def reply(self, msg, reply):
        self.ws.send(
            {
                "sID": msg["sID"],
                "msgID": msg["msgID"],  # same one they sent to us
                "resource": msg["resource"],
                "version": msg["version"],
                "action": "RESPONSE",
                "data": [reply],
            }
        )

    # send a message to the device
    def get(self, resource, version=None, action="GET", data=None):
        if self.services_initialized:
            resource_parts = resource.split("/")
            if len(resource_parts) > 1:
                service = resource.split("/")[1]
                if version is None and service in self.services.keys():
                    version = self.services[service]["version"]

        if version is None:
            version = 1

        msg = {
            "sID": self.session_id,
            "msgID": self.tx_msg_id,
            "resource": resource,
            "version": version,
            "action": action,
        }

        if data is not None:
            if isinstance(data, list) is False:
                data = [data]

            if action == "POST":
                if resource == "/ro/values":
                    # Raises exceptions on failure
                    # Replace named values with integers if possible
                    data = self.test_feature(data)
                elif resource == "/ro/activeProgram":
                    # Raises exception on failure
                    data = self.test_program_data(data)
                elif resource == "/ro/selectedProgram":
                    # Raises exception on failure
                    data = self.test_program_data(data)

            msg["data"] = data

        try:
            if self.debug:
                self.print(f"TX: {msg}")
            self.ws.send(msg)
        except Exception as e:
            print(self.name, "Failed to send", e, msg, traceback.format_exc())
        self.tx_msg_id += 1

    def reconnect(self):
        # Receive initialization message /ei/initialValues
        # Automatically responds in the handle_message function

        # ask the device which services it supports
        # registered devices gets pushed down too hence the loop
        self.get("/ci/services", version=1)
        while True:
            time.sleep(1)
            if self.services_initialized:
                break

        # We override the version based on the registered services received above

        # the clothes washer wants this, the token doesn't matter,
        # although they do not handle padding characters
        # they send a response, not sure how to interpet it
        if self.services["ci"]["version"] == 2:
            self.token = base64url_encode(get_random_bytes(32)).decode("UTF-8")
            self.token = re.sub(r"=", "", self.token)
            self.get("/ci/authentication", data={"nonce": self.token})
            # Get device info on older models
            self.get("/ci/info")

        if self.services.get("iz", None):
            # Retrieve device info on newer models
            self.get("/iz/info")
            # Retrieve detailed service info
            # self.get("/iz/services")
            # Retrieve hash - unclear what it is used for
            # self.get("/iz/hashOfCredential")

        # Retrieves registered clients like phone/hcpy itself
        # self.get("/ci/registeredDevices")

        # We need to send deviceReady to establish the connection
        if self.services.get("ei", None):
            self.get("/ei/deviceReady", action="NOTIFY")

        if self.services.get("ce", None):
            self.get("/ce/status")

        if self.services.get("ni", None):
            self.get("/ni/info")
            # Shows if DHCP enabled and SSID name
            # self.get("/ni/config", data={"interfaceID": 0})

        if self.services.get("ro", None):
            self.get("/ro/allMandatoryValues")
            self.get("/ro/allDescriptionChanges")
            # this gets NOTIFYied by the device
            # self.get("/ro/values")

    def handle_message(self, buf):
        msg = json.loads(buf)
        if self.debug:
            self.print("RX:", msg)
        sys.stdout.flush()

        resource = msg["resource"]
        action = msg["action"]

        values = {}

        if "code" in msg:
            values = {
                "error": msg["code"],
                "resource": msg.get("resource", ""),
            }
        elif action == "POST":
            if resource == "/ei/initialValues":
                # this is the first message they send to us and
                # establishes our session plus message ids
                self.session_id = msg["sID"]
                self.tx_msg_id = msg["data"][0]["edMsgID"]

                self.reply(
                    msg,
                    {
                        "deviceType": "Application",
                        "deviceName": self.device_name,
                        "deviceID": self.device_id,
                    },
                )

                threading.Thread(target=self.reconnect).start()
            else:
                self.print("Unknown resource", resource, file=sys.stderr)

        elif action == "RESPONSE" or action == "NOTIFY":
            if resource == "/iz/info" or resource == "/ci/info":
                if "data" in msg and len(msg["data"]) > 0:
                    # Return Device Information such as Serial Number, SW Versions, MAC Address
                    values = msg["data"][0]

            elif resource == "/ro/descriptionChange" or resource == "/ro/allDescriptionChanges":
                if "data" in msg and len(msg["data"]) > 0:
                    # Retrieve any value changes
                    values = self.parse_values(msg["data"])

                    for change in msg["data"]:
                        uid = str(change["uid"])
                        with self.features_lock:
                            if uid in self.features:
                                if "access" in change:
                                    access = change["access"]
                                    self.features[uid]["access"] = access
                                if "available" in change:
                                    self.features[uid]["available"] = change["available"]
                                if "min" in change:
                                    self.features[uid]["min"] = change["min"]
                                if "max" in change:
                                    self.features[uid]["max"] = change["max"]
                                # if "value" in change:
                                #    name = self.features[str(uid)]["name"]
                                #    values | self.parse_values(change)
                                if "default" in change:
                                    self.features[str(uid)]["default"] = change["default"]

                                if self.debug:
                                    self.print(
                                        f"Access change {self.features[uid]['name']} - {change}"
                                    )

                            else:
                                # We wont have name for this item, so have to be careful
                                # when resolving elsewhere
                                self.features[uid] = change

            elif resource == "/ni/info":
                if "data" in msg and len(msg["data"]) > 0:
                    # Return Network Information/IP Address etc
                    values = msg["data"][0]

            elif resource == "/ni/config":
                # Returns some data about network interfaces e.g.
                # [{'interfaceID': 0, 'automaticIPv4': True, 'automaticIPv6': True}]
                if self.debug:
                    self.print(f"/ni/config {msg}")

            elif resource == "/ro/allMandatoryValues" or resource == "/ro/values":
                if "data" in msg:
                    values = self.parse_values(msg["data"])
                else:
                    self.print(f"received {msg}")

            elif resource == "/ci/registeredDevices":
                # This contains details of Phone/HCPY registered as clients to the device
                pass

            elif resource == "/ci/tzInfo":
                pass

            elif resource == "/ci/authentication":
                if "data" in msg and len(msg["data"]) > 0:
                    # Grab authentication token - unsure if this is for us to use
                    # or to authenticate the server. Doesn't appear to be needed
                    self.token = msg["data"][0]["response"]

            elif resource == "/ci/services":
                for service in msg["data"]:
                    self.services[service["service"]] = {
                        "version": service["version"],
                    }
                self.services_initialized = True

            else:
                self.print("Unknown response or notify:", msg)

        else:
            self.print("Unknown message", msg)

        # return whatever we've parsed out of it
        return values

    def run_forever(self, on_message, on_open, on_close):
        def _on_message(ws, message):
            values = self.handle_message(message)
            on_message(values)

        def _on_open(ws):
            self.connected = True
            on_open(ws)

        def _on_close(ws, code, message):
            self.connected = False
            on_close(ws, code, message)

        def on_error(ws, message):
            self.print("Websocket error:", message)

        self.ws.run_forever(
            on_message=_on_message, on_open=_on_open, on_close=_on_close, on_error=on_error
        )

    def print(self, *args):
        print(now(), self.name, *args)
