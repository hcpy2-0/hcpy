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
#
# /iz/services

import sys
import json
import re
import time
import io
import traceback
from datetime import datetime

def now():
	return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

class HCDevice:
	def __init__(self, ws):
		self.ws = ws
		self.machine = None
		self.session_id = None
		self.tx_msg_id = None
		self.device_name = "hcpy"
		self.device_id = "0badcafe"

	def load_description(self, device_type):
		json_file = "xml/" + device_type + ".json"
		try:
			with io.open(json_file, "r") as fp:
				self.machine = json.load(fp)
			print(now(), json_file + ": parsed machine description")
		except Exception as e:
			print(now(), json_file + ": unable to load machine description", e)

	def parse_values(self, values):
		if not self.machine:
			return

		result = {}
		
		for msg in values:
			uid = str(msg["uid"])
			value = msg["value"]
			value_str = str(value)

			name = uid
			status = None

			if uid in self.machine["status"]:
				status = self.machine["status"][uid]
			elif uid in self.machine["options"]:
				status = self.machine["options"][uid]
			elif uid in self.machine["commands"]:
				status = self.machine["commands"][uid]

			if status:
				name = status["name"]
				if "values" in status \
				and value_str in status["values"]:
					value = status["values"][value_str]

			# trim everything off the name except the last part
			name = re.sub(r'^.*\.', '', name)
			result[name] = value

		return result

	def recv(self):
		try:
			buf = self.ws.recv()
			self.handle_message(buf)
			return buf
		except Exception as e:
			print("error handling msg", e, buf, traceback.format_exc())
			return None

	# reply to a POST or GET message with new data
	def reply(self, msg, reply):
		self.ws.send({
			'sID': msg["sID"],
			'msgID': msg["msgID"], # same one they sent to us
			'resource': msg["resource"],
			'version': msg["version"],
			'action': 'RESPONSE',
			'data': [reply],
		})

	# send a message to the device
	def get(self, resource, version=1, action="GET", data=None):
		msg = {
			"sID": self.session_id,
			"msgID": self.tx_msg_id,
			"resource": resource,
			"version": version,
			"action": action,
		}

		if data is not None:
			msg["data"] = [data]

		self.ws.send(msg)
		self.tx_msg_id += 1

	def handle_message(self, buf):
		msg = json.loads(buf)
		print(now(), "RX:", msg)
		sys.stdout.flush()


		resource = msg["resource"]
		action = msg["action"]
		if "code" in msg:
			print(now(), "ERROR", msg["code"])
		elif action == "POST":
			if resource == "/ei/initialValues":
				# this is the first message they send to us and
				# establishes our session plus message ids
				self.session_id = msg["sID"]
				self.tx_msg_id = msg["data"][0]["edMsgID"]

				self.reply(msg, {
					"deviceType": "Application",
					"deviceName": self.device_name,
					"deviceID": self.device_id,
				})

				# ask the device which services it supports
				self.get("/ci/services")
				#self.get("/ci/authentication", version=2, data={"nonce": "aGVsbG93b3JsZAo="})
				self.get("/ci/info", version=2)  # clothes washer
				self.get("/iz/info")  # dish washer
				#self.get("/ci/tzInfo", version=2)
				self.get("/ni/info")
				#self.get("/ni/config", data={"interfaceID": 0})
				self.get("/ei/deviceReady", version=2, action="NOTIFY")
				self.get("/ro/allDescriptionChanges")
				self.get("/ro/allDescriptionChanges")
				self.get("/ro/allMandatoryValues")
				#self.get("/ro/values")
			else:
				print(now(), "Unknown resource", resource, file=sys.stderr)

		elif action == "RESPONSE" or action == "NOTIFY":
			if resource == "/iz/info" or resource == "/ci/info":
				# see if we have a device file for this model
				if "data" in msg:
					device = msg["data"][0]["vib"]
					self.load_description(device)

			elif resource == "/ro/allMandatoryValues" \
			or resource == "/ro/values":
				values = self.parse_values(msg["data"])
				print(now(), values)
			elif resource == "/ci/registeredDevices":
				# we don't care
				pass

			elif resource == "/ci/services":
				self.services = {}
				for service in msg["data"]:
					self.services[service["service"]] = {
						"version": service["version"],
					}
				print(now(), "services", self.services)

				# we should figure out which ones to query now
#				if "iz" in self.services:
#					self.get("/iz/info", version=self.services["iz"]["version"])
#				if "ni" in self.services:
#					self.get("/ni/info", version=self.services["ni"]["version"])
#				if "ei" in self.services:
#					self.get("/ei/deviceReady", version=self.services["ei"]["version"], action="NOTIFY")

				#self.get("/if/info")

			else:
				#print(now(), "Unknown reponse", resource)
				pass

				# we should wait till we know this worked...
				#self.get("/ei/deviceReady", version=2, action="NOTIFY")
#			if machine and "data" in msg:
#				for el in msg["data"]:
#					if "uid" not in el:
#						continue
#					uid = str(el["uid"])
#			if not(uid in machine["status"]):
#				continue
#
#			status = machine["status"][uid]
#			value = str(el["value"])
#
#			if "values" in status and value in status["values"]:
#				value = status["values"][value]
#
#			print(status["name"] + "=" + value)
				