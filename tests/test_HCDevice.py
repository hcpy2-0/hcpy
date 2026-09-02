import json
from unittest.mock import Mock, patch

import pytest

from HCDevice import HCDevice


def make_device(services, features=None):
    """Build an HCDevice with pre-set services, ready to call reconnect().

    Sets the services event so reconnect() proceeds past the wait.
    Mocks ws.send and ws.close so nothing hits the network.
    """
    ws = Mock()
    device_config = {
        "name": "TestDevice",
        "features": features or {},
    }
    dev = HCDevice(ws, device_config)
    dev.session_id = 1
    dev.tx_msg_id = 1000
    dev.services = services
    dev._services_event.set()
    return dev


def sent_resources(device):
    """Return list of (resource, action) tuples from ws.send calls."""
    results = []
    for call in device.ws.send.call_args_list:
        msg = call.args[0]
        results.append((msg["resource"], msg["action"]))
    return results


def sent_get_resources(device):
    """Return list of resource paths that were sent as GETs."""
    return [r for r, a in sent_resources(device) if a == "GET"]


def sent_notify_resources(device):
    """Return list of resource paths that were sent as NOTIFYs."""
    return [r for r, a in sent_resources(device) if a == "NOTIFY"]


# Service profiles from research captures.
IZ_SERVICES = {
    "ci": {"version": 3},
    "ei": {"version": 2},
    "iz": {"version": 1},
    "ni": {"version": 1},
    "ro": {"version": 1},
}

# Same as IZ_SERVICES but with iz version bumped so the version override
# test is meaningful (default version param in get() is 1, so version 1
# passes whether or not the override fires).
IZ_SERVICES_V2 = {
    **IZ_SERVICES,
    "iz": {"version": 2},
}

NON_IZ_SERVICES = {
    "ro": {"version": 1},
    "ei": {"version": 2},
    "ci": {"version": 2},
    "ni": {"version": 1},
}


@patch("HCDevice.HCDevice.print")
class TestReconnectIzCapable:
    """iz-capable devices (ci:3): use /iz/info, skip auth and /ci/info."""

    def test_queries_iz_info(self, _print):
        dev = make_device(IZ_SERVICES)
        dev.reconnect()
        assert "/iz/info" in sent_get_resources(dev)

    def test_skips_ci_info(self, _print):
        dev = make_device(IZ_SERVICES)
        dev.reconnect()
        assert "/ci/info" not in sent_get_resources(dev)

    def test_skips_ci_authentication(self, _print):
        dev = make_device(IZ_SERVICES)
        dev.reconnect()
        assert "/ci/authentication" not in sent_get_resources(dev)

    def test_queries_ni_info(self, _print):
        dev = make_device(IZ_SERVICES)
        dev.reconnect()
        assert "/ni/info" in sent_get_resources(dev)

    def test_sends_device_ready(self, _print):
        dev = make_device(IZ_SERVICES)
        dev.reconnect()
        assert "/ei/deviceReady" in sent_notify_resources(dev)

    def test_queries_all_mandatory_values(self, _print):
        dev = make_device(IZ_SERVICES)
        dev.reconnect()
        assert "/ro/allMandatoryValues" in sent_get_resources(dev)

    def test_queries_all_description_changes(self, _print):
        dev = make_device(IZ_SERVICES)
        dev.reconnect()
        assert "/ro/allDescriptionChanges" in sent_get_resources(dev)


@patch("HCDevice.HCDevice.print")
class TestReconnectNonIz:
    """Non-iz devices (ci:2): use /ci/authentication + /ci/info, skip /iz/info."""

    def test_queries_ci_authentication(self, _print):
        dev = make_device(NON_IZ_SERVICES)
        dev.reconnect()
        assert "/ci/authentication" in sent_get_resources(dev)

    def test_queries_ci_info(self, _print):
        dev = make_device(NON_IZ_SERVICES)
        dev.reconnect()
        assert "/ci/info" in sent_get_resources(dev)

    def test_skips_iz_info(self, _print):
        dev = make_device(NON_IZ_SERVICES)
        dev.reconnect()
        assert "/iz/info" not in sent_get_resources(dev)

    def test_auth_before_ci_info(self, _print):
        """Auth nonce must be sent before /ci/info."""
        dev = make_device(NON_IZ_SERVICES)
        dev.reconnect()
        gets = sent_get_resources(dev)
        auth_idx = gets.index("/ci/authentication")
        info_idx = gets.index("/ci/info")
        assert auth_idx < info_idx

    def test_queries_ni_info(self, _print):
        dev = make_device(NON_IZ_SERVICES)
        dev.reconnect()
        assert "/ni/info" in sent_get_resources(dev)

    def test_sends_device_ready(self, _print):
        dev = make_device(NON_IZ_SERVICES)
        dev.reconnect()
        assert "/ei/deviceReady" in sent_notify_resources(dev)


@patch("HCDevice.HCDevice.print")
class TestReconnectNoNi:
    """Device without ni service should skip /ni/info."""

    def test_skips_ni_info(self, _print):
        services = {
            "ci": {"version": 3},
            "ei": {"version": 2},
            "iz": {"version": 1},
            "ro": {"version": 1},
        }
        dev = make_device(services)
        dev.reconnect()
        assert "/ni/info" not in sent_get_resources(dev)


@patch("HCDevice.HCDevice.print")
class TestReconnectRoValues:
    """/ro/values should never be queried during reconnect."""

    def test_ro_values_not_queried_iz(self, _print):
        dev = make_device(IZ_SERVICES)
        dev.reconnect()
        gets = sent_get_resources(dev)
        assert len(gets) > 1
        assert "/ro/values" not in gets

    def test_ro_values_not_queried_non_iz(self, _print):
        dev = make_device(NON_IZ_SERVICES)
        dev.reconnect()
        gets = sent_get_resources(dev)
        assert len(gets) > 1
        assert "/ro/values" not in gets


@patch("HCDevice.HCDevice.print")
class TestReconnectTimeout:
    """When /ci/services never arrives, reconnect should close and return."""

    def test_closes_websocket_on_timeout(self, _print):
        ws = Mock()
        dev = HCDevice(ws, {"name": "TestDevice", "features": {}})
        dev.session_id = 1
        dev.tx_msg_id = 1000
        # Do not set the event, so wait() will time out.
        dev._services_event.wait = Mock(return_value=False)

        dev.reconnect()

        ws.close.assert_called_once()

    def test_no_post_discovery_requests_on_timeout(self, _print):
        ws = Mock()
        dev = HCDevice(ws, {"name": "TestDevice", "features": {}})
        dev.session_id = 1
        dev.tx_msg_id = 1000
        dev._services_event.wait = Mock(return_value=False)

        dev.reconnect()

        # Only /ci/services should have been sent (before the wait).
        resources = sent_get_resources(dev)
        assert resources == ["/ci/services"]


@patch("HCDevice.HCDevice.print")
class TestReconnectVersionOverride:
    """Services versions should be used in requests."""

    def test_iz_info_uses_iz_version(self, _print):
        dev = make_device(IZ_SERVICES_V2)
        dev.reconnect()
        for call in dev.ws.send.call_args_list:
            msg = call.args[0]
            if msg["resource"] == "/iz/info":
                assert msg["version"] == 2
                return
        pytest.fail("/iz/info not found in sent messages")

    def test_ci_info_uses_ci_version(self, _print):
        dev = make_device(NON_IZ_SERVICES)
        dev.reconnect()
        for call in dev.ws.send.call_args_list:
            msg = call.args[0]
            if msg["resource"] == "/ci/info":
                assert msg["version"] == 2
                return
        pytest.fail("/ci/info not found in sent messages")


@patch("HCDevice.HCDevice.print")
class TestServicesEvent:
    """The /ci/services response handler should set the event."""

    def test_event_set_on_services_response(self, _print):
        ws = Mock()
        dev = HCDevice(ws, {"name": "TestDevice", "features": {}})
        dev.session_id = 1
        dev.tx_msg_id = 1000

        assert not dev._services_event.is_set()

        import json

        msg = json.dumps(
            {
                "sID": 1,
                "msgID": 1000,
                "resource": "/ci/services",
                "version": 1,
                "action": "RESPONSE",
                "data": [
                    {"service": "ci", "version": 3},
                    {"service": "ei", "version": 2},
                    {"service": "iz", "version": 1},
                    {"service": "ro", "version": 1},
                ],
            }
        )
        dev.handle_message(msg)

        assert dev._services_event.is_set()
        assert "ci" in dev.services
        assert "iz" in dev.services

    def test_services_populated_from_response(self, _print):
        ws = Mock()
        dev = HCDevice(ws, {"name": "TestDevice", "features": {}})
        dev.session_id = 1
        dev.tx_msg_id = 1000

        import json

        msg = json.dumps(
            {
                "sID": 1,
                "msgID": 1000,
                "resource": "/ci/services",
                "version": 1,
                "action": "RESPONSE",
                "data": [
                    {"service": "ro", "version": 1},
                    {"service": "ci", "version": 2},
                ],
            }
        )
        dev.handle_message(msg)

        assert dev.services == {
            "ro": {"version": 1},
            "ci": {"version": 2},
        }


# A string feature and a numeric one, as a Siemens TP713R09 coffee machine
# reports them. For refDID 8B, min/max is the length in UTF-8 bytes.
STRING_FEATURES = {
    "32825": {
        "name": "BSH.Common.Setting.Favorite.001.Name",
        "access": "readWrite",
        "available": "true",
        "refCID": "05",
        "refDID": "8B",
        "min": "0",
        "max": "30",
    },
    "4357": {
        "name": "ConsumerProducts.CoffeeMaker.Setting.BrightnessDisplay",
        "access": "readWrite",
        "available": "true",
        "refCID": "02",
        "refDID": "80",
        "min": "1",
        "max": "5",
    },
}


@patch("HCDevice.HCDevice.print")
class TestStringFeatureValidation:
    """min/max on a refDID 8B feature is a byte length, not a numeric range."""

    def device(self):
        return HCDevice(Mock(), {"name": "TestDevice", "features": STRING_FEATURES})

    def test_accepts_string_within_budget(self, _print):
        data = self.device().test_feature([{"uid": 32825, "value": "Cappuccino"}])
        assert data == [{"uid": 32825, "value": "Cappuccino"}]

    def test_accepts_exactly_max_bytes(self, _print):
        value = "A" * 30
        data = self.device().test_feature([{"uid": 32825, "value": value}])
        assert data[0]["value"] == value

    def test_rejects_too_many_bytes(self, _print):
        with pytest.raises(Exception, match="UTF-8 bytes"):
            self.device().test_feature([{"uid": 32825, "value": "A" * 31}])

    def test_counts_bytes_not_characters(self, _print):
        # 11 Braille characters are 33 UTF-8 bytes, so this must be rejected
        # even though it is well under 30 characters.
        with pytest.raises(Exception, match="but is 33"):
            self.device().test_feature([{"uid": 32825, "value": "⣿" * 11}])

    def test_accepts_multibyte_within_budget(self, _print):
        value = "⣿" * 10  # 30 bytes
        data = self.device().test_feature([{"uid": 32825, "value": value}])
        assert data[0]["value"] == value

    def test_rejects_non_string(self, _print):
        with pytest.raises(Exception, match="expects a string"):
            self.device().test_feature([{"uid": 32825, "value": 5}])

    def test_numeric_feature_still_range_checked(self, _print):
        with pytest.raises(Exception, match="integer in the range 1 and 5"):
            self.device().test_feature([{"uid": 4357, "value": 99}])

    def test_numeric_feature_accepts_valid_value(self, _print):
        data = self.device().test_feature([{"uid": 4357, "value": 4}])
        assert data[0]["value"] == 4


@patch("HCDevice.HCDevice.print")
class TestIzServices:
    """/iz/services lists each service's resources and their allowed actions."""

    # Trimmed from a Siemens TP713R09 response: ci appears at two versions and
    # ro in both roles, so entries are kept per advertisement, not per name.
    RESPONSE = {
        "sID": 1,
        "msgID": 1000,
        "resource": "/iz/services",
        "version": 1,
        "action": "RESPONSE",
        "data": [
            {
                "service": "ci",
                "version": 1,
                "role": "PROVIDER",
                "resources": [{"name": "services", "allowedActions": ["GET"]}],
            },
            {
                "service": "ci",
                "version": 3,
                "role": "PROVIDER",
                "resources": [
                    {"name": "register", "allowedActions": ["POST"]},
                    {"name": "registeredDevices", "allowedActions": ["GET", "NOTIFY"]},
                ],
            },
            {
                "service": "ro",
                "version": 1,
                "role": "CONSUMER",
                "resources": [{"name": "values", "allowedActions": ["POST", "GET", "NOTIFY"]}],
            },
        ],
    }

    def handled(self):
        dev = HCDevice(Mock(), {"name": "TestDevice", "features": {}})
        dev.session_id = 1
        dev.tx_msg_id = 1000
        dev.handle_message(json.dumps(self.RESPONSE))
        return dev

    def test_resources_populated(self, _print):
        dev = self.handled()
        assert len(dev.resources) == 3

    def test_allowed_actions_recorded(self, _print):
        dev = self.handled()
        ro = next(e for e in dev.resources if e["service"] == "ro")
        assert ro["resources"]["values"] == ["POST", "GET", "NOTIFY"]

    def test_keeps_every_advertisement_of_a_service(self, _print):
        dev = self.handled()
        versions = sorted(e["version"] for e in dev.resources if e["service"] == "ci")
        assert versions == [1, 3]

    def test_role_recorded(self, _print):
        dev = self.handled()
        assert {e["role"] for e in dev.resources} == {"PROVIDER", "CONSUMER"}

    def test_not_reported_as_unknown(self, _print):
        self.handled()
        logged = " ".join(str(c) for c in _print.call_args_list)
        assert "Unknown response or notify" not in logged
