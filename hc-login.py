#!/usr/bin/env python3
# This directly follows the OAuth login flow that is opaquely described
# https://github.com/openid/AppAuth-Android
# A really nice walk through of how it works is:
# https://auth0.com/docs/get-started/authentication-and-authorization-flow/call-your-api-using-the-authorization-code-flow-with-pkce
import io
import json
import re
import sys
from base64 import urlsafe_b64encode as base64url_encode
from urllib.parse import unquote, urlencode
from zipfile import ZipFile

import requests
from Crypto.Hash import SHA256
from Crypto.Random import get_random_bytes

from HCxml2json import xml2json

# These two lines enable debugging at httplib level (requests->urllib3->http.client)
# You will see the REQUEST, including HEADERS and DATA, and RESPONSE with HEADERS but without DATA.
# The only thing missing will be the response.body which is not logged.
# http_client.HTTPConnection.debuglevel = 1

# You must initialize logging, otherwise you'll not see debug output.
# logging.basicConfig()
# logging.getLogger().setLevel(logging.DEBUG)
# requests_log = logging.getLogger("requests.packages.urllib3")
# requests_log.setLevel(logging.DEBUG)
# requests_log.propagate = True


def debug(*args):
    print(*args, file=sys.stderr)


devicefile = sys.argv[1]

session = requests.Session()

base_url = "https://api.home-connect.com/security/oauth/"
asset_urls = [
    "https://prod.reu.rest.homeconnectegw.com/",  # EU
    "https://prod.rna.rest.homeconnectegw.com/",  # US
]

#
# Start by fetching the old login page, which gives
# us the verifier and challenge for getting the token,
# even after the singlekey detour.
#
# The app_id and scope are hardcoded in the application
app_id = "9B75AC9EC512F36C84256AC47D813E2C1DD0D6520DF774B020E1E6E2EB29B1F3"
# scopes used by the Home Connect app: Control
# DeleteAppliance IdentifyAppliance Images
# Monitor ReadAccount ReadOrigApi Settings
# WriteAppliance WriteOrigApi
scope = [
    "ReadOrigApi",
]


def b64(b):
    return re.sub(r"=", "", base64url_encode(b).decode("UTF-8"))


def b64random(num):
    return b64(base64url_encode(get_random_bytes(num)))


verifier = b64(get_random_bytes(32))

login_query = {
    "response_type": "code",
    "prompt": "login",
    "code_challenge": b64(SHA256.new(verifier.encode("UTF-8")).digest()),
    "code_challenge_method": "S256",
    "client_id": app_id,
    "scope": " ".join(scope),
    "nonce": b64random(16),
    "state": b64random(16),
    "redirect_uri": "hcauth://auth/prod",
}

loginpage_url = base_url + "authorize?" + urlencode(login_query)
token_url = base_url + "token"

print(
    "Visit the following URL in Chrome, use the F12 developer tools "
    "to monitor the network responses, and look for the request starting "
    "hcauth://auth for the relevant authentication tokens:"
)
print(loginpage_url)

code = unquote(input("Input code:"))
state = input("Input state:")
grant_type = "authorization_code"

debug(f"{code=} {grant_type=} {state=}")

auth_url = base_url + "login"
token_url = base_url + "token"

token_fields = {
    "grant_type": grant_type,
    "client_id": app_id,
    "code_verifier": verifier,
    "code": code,
    "redirect_uri": login_query["redirect_uri"],
}

debug(f"{token_url=} {token_fields=}")

r = requests.post(token_url, data=token_fields, allow_redirects=False)
if r.status_code != requests.codes.ok:
    print("Bad code?", file=sys.stderr)
    print(r.headers, r.text)
    exit(1)

debug("--------- got token page ----------")

token = json.loads(r.text)["access_token"]
debug(f"Received access {token=}")

headers = {
    "Authorization": "Bearer " + token,
}


# Try to request account details from all geos. Whichever works, we'll use next.
for asset_url in asset_urls:
    r = requests.get(asset_url + "account/details", headers=headers)
    if r.status_code == requests.codes.ok:
        break

# now we can fetch the rest of the account info
if r.status_code != requests.codes.ok:
    print("unable to fetch account details", file=sys.stderr)
    print(r.headers, r.text)
    exit(1)

# print(r.text)
account = json.loads(r.text)
configs = []

print(account, file=sys.stderr)

for app in account["data"]["homeAppliances"]:
    app_brand = app["brand"]
    app_type = app["type"]
    app_id = app["identifier"]

    config = {
        "name": app_type.lower(),
    }

    configs.append(config)

    if "tls" in app:
        # fancy machine with TLS support
        config["host"] = app_brand + "-" + app_type + "-" + app_id
        config["key"] = app["tls"]["key"]
    else:
        # less fancy machine with HTTP support
        config["host"] = app_id
        config["key"] = app["aes"]["key"]
        config["iv"] = app["aes"]["iv"]

    # Fetch the XML zip file for this device
    app_url = asset_url + "api/iddf/v1/iddf/" + app_id
    print("fetching", app_url, file=sys.stderr)
    r = requests.get(app_url, headers=headers)
    if r.status_code != requests.codes.ok:
        print(app_id, ": unable to fetch machine description?")
        next

    # we now have a zip file with XML, let's unpack them
    content = r.content
    print(app_url + ": " + app_id + ".zip", file=sys.stderr)
    with open(app_id + ".zip", "wb") as f:
        f.write(content)
    z = ZipFile(io.BytesIO(content))
    # print(z.infolist())
    features = z.open(app_id + "_FeatureMapping.xml").read()
    description = z.open(app_id + "_DeviceDescription.xml").read()

    machine = xml2json(features, description)
    config["description"] = machine["description"]
    config["features"] = machine["features"]
    print("Discovered device: " + config["name"] + " - Device hostname: " + config["host"])

with open(devicefile, "w") as f:
    json.dump(configs, f, ensure_ascii=True, indent=4)

print(
    "Success. You can now edit "
    + devicefile
    + ", if needed, and run hc2mqtt.py or start Home Assistant addon again"
)
