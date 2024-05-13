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

from HCDevice import HCDevice
from HCSocket import HCSocket, now


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
):

    def on_connect(client, userdata, flags, rc):
        if rc == 5:
            print(now(), f"ERROR MQTT connection failed: unauthorized - {rc}")
        elif rc == 0:
            print(now(), f"MQTT connection established: {rc}")
            client.publish(f"{mqtt_prefix}LWT", payload="online", qos=0, retain=True)
            # Re-subscribe to all device topics on reconnection
            for device in devices:
                mqtt_set_topic = f"{mqtt_prefix}{device['name']}/set"
                print(now(), device["name"], f"set topic: {mqtt_set_topic}")
                client.subscribe(mqtt_set_topic)
                for value in device["features"]:
                    # If the device has the ActiveProgram feature it allows programs to be started
                    # and scheduled via /ro/activeProgram
                    if "BSH.Common.Root.ActiveProgram" == device["features"][value]["name"]:
                        mqtt_active_program_topic = f"{mqtt_prefix}{device['name']}/activeProgram"
                        print(now(), device["name"], f"program topic: {mqtt_active_program_topic}")
                        client.subscribe(mqtt_active_program_topic)
        else:
            print(now(), f"ERROR MQTT connection failed: {rc}")

    def on_disconnect(client, userdata, rc):
        print(now(), f"ERROR MQTT client disconnected: {rc}")

    def on_message(client, userdata, msg):
        mqtt_state = msg.payload.decode()
        mqtt_topic = msg.topic.split("/")
        print(now(), f"{msg.topic} received mqtt message {mqtt_state}")

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
            else:
                raise Exception(f"Payload topic {topic} is unknown.")

            if dev[device_name].connected:
                dev[device_name].get(resource, 1, "POST", msg)
            else:
                print(now(), device_name, "ERROR cant send message as websocket is not connected")
        except Exception as e:
            print(now(), device_name, "ERROR", e, file=sys.stderr)

    click.echo(
        f"Hello {devices_file=} {mqtt_host=} {mqtt_prefix=} "
        f"{mqtt_port=} {mqtt_username=} {mqtt_password=} "
        f"{mqtt_ssl=} {mqtt_cafile=} {mqtt_certfile=} {mqtt_keyfile=} {mqtt_clientname=}"
        f"{domain_suffix=} {debug=}"
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

    # HCDevice should maintain its own state?
    state = {}

    def on_message(msg):
        if msg is not None:
            if len(msg) > 0:
                print(now(), name, msg)

                update = False
                for key in msg.keys():
                    val = msg.get(key, None)
                    if key in state:
                        # Override existing values with None if they have changed
                        state[key] = val
                        update = True
                    else:
                        # Dont store None values until something useful is populated?
                        if val is None:
                            continue
                        else:
                            state[key] = val
                            update = True

                if not update:
                    return

                if client.is_connected():
                    msg = json.dumps(state)
                    print(now(), name, f"publish to {mqtt_topic} with {msg}")
                    client.publish(f"{mqtt_topic}/state", msg, retain=True)
                else:
                    print(
                        now(),
                        name,
                        "ERROR Unable to publish update as mqtt is not connected.",
                    )

    def on_open(ws):
        client.publish(f"{mqtt_topic}/LWT", "online", retain=True)

    def on_close(ws, code, message):
        client.publish(f"{mqtt_topic}/LWT", "offline", retain=True)
        print(now(), device["name"], "websocket closed, reconnecting...")

    while True:
        time.sleep(3)
        try:
            print(now(), name, f"connecting to {host}")
            ws = HCSocket(host, device["key"], device.get("iv", None), domain_suffix)
            dev[name] = HCDevice(ws, device, debug)
            dev[name].run_forever(on_message=on_message, on_open=on_open, on_close=on_close)
        except Exception as e:
            print(now(), device["name"], "ERROR", e, file=sys.stderr)
            client.publish(f"{mqtt_topic}/LWT", "offline", retain=True)

        time.sleep(57)


if __name__ == "__main__":
    hc2mqtt(auto_envvar_prefix="HCPY")
