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

    def parse_values(self, values):
        if not self.features:
            return values

        result = {}

        for msg in values:
            uid = str(msg["uid"])
            value = msg["value"]
            value_str = str(value)

            name = uid
            status = None
            with self.features_lock:
                if uid in self.features:
                    status = self.features[uid]

            if status:
                if "name" in status:
                    name = status["name"]
                if "values" in status and value_str in status["values"]:
                    value = status["values"][value_str]

            # trim everything off the name except the last part
            name = re.sub(r"^.*\.", "", name)
            result[name] = value

        return result

    # Based on PR submitted https://github.com/Skons/hcpy/pull/1
    def test_program_data(self, data_array):
        for data in data_array:
            if "program" not in data:
                raise TypeError("Message data invalid, no program specified.")

            if isinstance(data["program"], int) is False:
                raise TypeError("Message data invalid, UID in 'program' must be an integer.")

            # devices.json stores UID as string
            uid = str(data["program"])
            with self.features_lock:
                if uid not in self.features:
                    raise ValueError(
                        f"Unable to configure appliance. Program UID {uid} is not valid"
                        " for this device."
                    )

                feature = self.features[uid]
                # Diswasher is Dishcare.Dishwasher.Program.{name}
                # Hood is Cooking.Common.Program.{name}
                # May also be in the format BSH.Common.Program.Favorite.001
                if "name" in feature:
                    if ".Program." not in feature["name"]:
                        raise ValueError(
                            f"Unable to configure appliance. Program UID {uid} is not a valid"
                            f" program - {feature['name']}."
                        )
                else:
                    self.print(f"Unknown Program UID {uid}")

                if "options" in data:
                    for option in data["options"]:
                        option_uid = option["uid"]
                        if str(option_uid) not in self.features:
                            raise ValueError(
                                f"Unable to configure appliance. Option UID {option_uid} is not"
                                " valid for this device."
                            )

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
                    raise Exception(
                        "Unable to configure appliance. "
                        f"Feature {feature['name']} with uid {uid} does not have access."
                    )

                access = feature["access"].lower()
                if access != "readwrite" and access != "writeonly":
                    raise Exception(
                        "Unable to configure appliance. "
                        f"Feature {feature['name']} with uid {uid} "
                        f"has got access {feature['access']}."
                    )

                # check if selected list with values is allowed
                if "values" in feature:
                    if isinstance(data["value"], int) is False:
                        raise Exception(
                            f"Unable to configure appliance. The value {data['value']} must "
                            f"be an integer. Allowed values are {feature['values']}."
                        )

                    value = str(data["value"])
                    # values are strings in the feature list,
                    # but always seem to be an integer. An integer must be provided
                    if value not in feature["values"]:
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
    def get(self, resource, version=1, action="GET", data=None):
        if self.services_initialized:
            resource_parts = resource.split("/")
            if len(resource_parts) > 1:
                service = resource.split("/")[1]
                if service in self.services.keys():
                    version = self.services[service]["version"]
                else:
                    self.print("ERROR service not known")

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

            if action == "POST" and self.debug is False:
                if resource == "/ro/values":
                    # Raises exceptions on failure
                    self.test_feature(data)
                elif resource == "/ro/activeProgram":
                    # Raises exception on failure
                    self.test_program_data(data)

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
        self.get("/ci/services")
        while True:
            time.sleep(1)
            if self.services_initialized:
                break

        # We override the version based on the registered services received above

        # the clothes washer wants this, the token doesn't matter,
        # although they do not handle padding characters
        # they send a response, not sure how to interpet it
        self.token = base64url_encode(get_random_bytes(32)).decode("UTF-8")
        self.token = re.sub(r"=", "", self.token)
        self.get("/ci/authentication", version=2, data={"nonce": self.token})

        self.get("/ci/info")  # clothes washer
        self.get("/iz/info")  # dish washer

        # Retrieves registered clients like phone/hcpy itself
        # self.get("/ci/registeredDevices")

        # tzInfo all returns empty?
        # self.get("/ci/tzInfo")

        # We need to send deviceReady for some devices or /ni/ will come back as 403 unauth
        self.get("/ei/deviceReady", version=2, action="NOTIFY")
        self.get("/ni/info")
        # self.get("/ni/config", data={"interfaceID": 0})

        # self.get("/ro/allDescriptionChanges")
        self.get("/ro/allMandatoryValues")
        self.get("/ro/values")
        self.get("/ro/allDescriptionChanges")

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
                    with self.features_lock:
                        for change in msg["data"]:
                            uid = str(change["uid"])
                            if uid in self.features:
                                if "access" in change:
                                    access = change["access"]
                                    self.features[uid]["access"] = access
                                    self.print(f"Access change for {uid} to {access}")
                                if "available" in change:
                                    self.features[uid]["available"] = change["available"]
                                if "min" in change:
                                    self.features[uid]["min"] = change["min"]
                                if "max" in change:
                                    self.features[uid]["max"] = change["max"]
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
                pass

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
