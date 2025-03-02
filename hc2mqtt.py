#!/usr/bin/env python3
# Contact Bosh-Siemens Home Connect devices
# and connect their messages to the mqtt server
import json
import ssl
import sys
import time
from threading import Thread

import click
import click_config_file
import paho.mqtt.client as mqtt

from HADiscovery import publish_ha_discovery
from HCDevice import HCDevice
from HCSocket import HCSocket, now


def hcprint(*args):
    print(now(), *args, flush=True)


@click.command()
@click.option("-d", "--devices_file", default="config/devices.json")
@click.option("-h", "--mqtt_host", default="localhost")
@click.option("-p", "--mqtt_prefix", default="homeconnect/")
@click.option("--mqtt_port", default=1883, type=int)
@click.option("--mqtt_username")
@click.option("--mqtt_password")
@click.option("--mqtt_ssl", is_flag=True)
@click.option("--mqtt_cafile")
@click.option("--mqtt_certfile")
@click.option("--mqtt_keyfile")
@click.option("--mqtt_clientname", default="hcpy1")
@click.option("--domain_suffix", default="")
@click.option("--debug/--no-debug", default=False)
@click.option("--ha-discovery", is_flag=True)
@click.option("--discovery_file", default="config/discovery.yaml")
@click_config_file.configuration_option()
def hc2mqtt(
    devices_file: str,
    mqtt_host: str,
    mqtt_prefix: str,
    mqtt_port: int,
    mqtt_username: str,
    mqtt_password: str,
    mqtt_ssl: bool,
    mqtt_cafile: str,
    mqtt_certfile: str,
    mqtt_keyfile: str,
    mqtt_clientname: str,
    domain_suffix: str,
    debug: bool,
    ha_discovery: bool,
    discovery_file: str,
):

    def on_connect(client, userdata, flags, rc):
        if rc == 5:
            hcprint(f"ERROR MQTT connection failed: unauthorized - {rc}")
        elif rc == 0:
            hcprint(f"MQTT connection established: {rc}")
            client.publish(f"{mqtt_prefix}LWT", payload="online", qos=0, retain=True)
            # Re-subscribe to all device topics on reconnection
            for device in devices:
                mqtt_topic = f"{mqtt_prefix}{device['name']}"
                mqtt_set_topic = f"{mqtt_prefix}{device['name']}/set"
                hcprint(device["name"], f"set topic: {mqtt_set_topic}")
                client.subscribe(mqtt_set_topic)
                for value in device["features"]:
                    # If the device has the ActiveProgram feature it allows programs to be started
                    # and scheduled via /ro/activeProgram
                    if "name" in device["features"][value]:
                        if "BSH.Common.Root.ActiveProgram" == device["features"][value]["name"]:
                            mqtt_active_program_topic = (
                                f"{mqtt_prefix}{device['name']}/activeProgram"
                            )
                            hcprint(device["name"], f"program topic: {mqtt_active_program_topic}")
                            client.subscribe(mqtt_active_program_topic)
                        # If the device has the SelectedProgram feature it allows programs to be
                        # selected via /ro/selectedProgram
                        if "BSH.Common.Root.SelectedProgram" == device["features"][value]["name"]:
                            mqtt_selected_program_topic = (
                                f"{mqtt_prefix}{device['name']}/selectedProgram"
                            )
                            hcprint(
                                device["name"], f"program topic: {mqtt_selected_program_topic}"
                            )
                            client.subscribe(mqtt_selected_program_topic)
                if ha_discovery:
                    time.sleep(15)
                    publish_ha_discovery(discovery_file, device, client, mqtt_topic)
        else:
            hcprint(f"ERROR MQTT connection failed: {rc}")

    def on_disconnect(client, userdata, rc):
        hcprint(f"ERROR MQTT client disconnected: {rc}")

    def on_message(client, userdata, msg):
        mqtt_state = msg.payload.decode()
        mqtt_topic = msg.topic.split("/")
        hcprint(f"{msg.topic} received mqtt message {mqtt_state}")

        try:
            if len(mqtt_topic) >= 2:
                device_name = mqtt_topic[-2]
                topic = mqtt_topic[-1]
            else:
                raise Exception(f"Invalid mqtt topic {msg.topic}.")

            try:
                msg = json.loads(mqtt_state)
            except ValueError as e:
                raise ValueError(f"Invalid JSON in message: {mqtt_state}.") from e

            if topic == "set":
                resource = "/ro/values"
            elif topic == "activeProgram":
                resource = "/ro/activeProgram"
            elif topic == "selectedProgram":
                resource = "/ro/selectedProgram"
            else:
                raise Exception(f"Payload topic {topic} is unknown.")

            if dev[device_name].connected:
                dev[device_name].get(resource, 1, "POST", msg)
            else:
                hcprint(device_name, "ERROR cant send message as websocket is not connected")
        except Exception as e:
            print(now(), device_name, "ERROR", e, file=sys.stderr, flush=True)

    click.echo(
        f"Hello {devices_file=} {mqtt_host=} {mqtt_prefix=} "
        f"{mqtt_port=} {mqtt_username=} {mqtt_password=} "
        f"{mqtt_ssl=} {mqtt_cafile=} {mqtt_certfile=} {mqtt_keyfile=} {mqtt_clientname=}"
        f"{domain_suffix=} {debug=} {ha_discovery=}"
    )

    with open(devices_file, "r") as f:
        devices = json.load(f)

    client = mqtt.Client(mqtt_clientname)

    if mqtt_username and mqtt_password:
        client.username_pw_set(mqtt_username, mqtt_password)

    if mqtt_ssl:
        if mqtt_cafile and mqtt_certfile and mqtt_keyfile:
            client.tls_set(
                ca_certs=mqtt_cafile,
                certfile=mqtt_certfile,
                keyfile=mqtt_keyfile,
                cert_reqs=ssl.CERT_REQUIRED,
            )
        else:
            client.tls_set(cert_reqs=ssl.CERT_NONE)

    client.will_set(f"{mqtt_prefix}LWT", payload="offline", qos=0, retain=True)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.connect(host=mqtt_host, port=mqtt_port, keepalive=70)

    for device in devices:
        mqtt_topic = mqtt_prefix + device["name"]
        thread = Thread(
            target=client_connect, args=(client, device, mqtt_topic, domain_suffix, debug)
        )
        thread.start()

    client.loop_forever()


global dev
dev = {}


def client_connect(client, device, mqtt_topic, domain_suffix, debug):
    host = device["host"]
    name = device["name"]
    mydevice = None

    def on_message(msg):
        try:
            if msg is not None:
                if len(msg) > 0:
                    hcprint(name, msg)

                    update = False
                    events = {}
                    for key in msg.keys():
                        val = msg.get(key, None)

                        # Dont persist event to the device state
                        if ".Event." in key:
                            event_type = {"event_type": val}
                            events.update({key: event_type})
                        else:
                            if key in mydevice.state:
                                # Override existing values with None if they have changed
                                mydevice.state[key] = val
                                update = True
                            else:
                                # Dont store None values until something useful is populated?
                                if val is None:
                                    continue
                                else:
                                    mydevice.state[key] = val
                                    update = True

                    if not update and not events:
                        return

                    if client.is_connected():
                        for key, value in events.items():
                            event_topic_name = key.lower().replace(".", "_")
                            hcprint(
                                name,
                                f"publish to {mqtt_topic}/event/{event_topic_name}",
                            )
                            client.publish(
                                f"{mqtt_topic}/event/{event_topic_name}",
                                json.dumps(value),
                                retain=True,
                            )
                        if update:
                            hcprint(name, f"updating {json.dumps(mydevice.state)}")
                            for key, value in mydevice.state.items():
                                state_topic_name = key.lower().replace(".", "_")
                                if isinstance(value, dict):
                                    value = json.dumps(value)

                                client.publish(
                                    f"{mqtt_topic}/state/{state_topic_name}",
                                    str(value),
                                    retain=True,
                                )
                    else:
                        hcprint(
                            name,
                            "ERROR Unable to publish update as mqtt is not connected.",
                        )
        except Exception as e:
            print(repr(e))

    def on_open(ws):
        client.publish(f"{mqtt_topic}/LWT", "online", retain=True)

    def on_close(ws, code, message):
        client.publish(f"{mqtt_topic}/LWT", "offline", retain=True)
        hcprint(device["name"], "websocket closed, reconnecting...")

    while True:
        time.sleep(3)
        try:
            hcprint(name, f"connecting to {host}")
            ws = HCSocket(host, device["key"], device.get("iv", None), domain_suffix)
            mydevice = HCDevice(ws, device, debug)
            dev[name] = mydevice
            mydevice.run_forever(on_message=on_message, on_open=on_open, on_close=on_close)
        except Exception as e:
            print(now(), device["name"], "ERROR", e, file=sys.stderr, flush=True)
            client.publish(f"{mqtt_topic}/LWT", "offline", retain=True)

        time.sleep(57)


if __name__ == "__main__":
    hc2mqtt(auto_envvar_prefix="HCPY")
