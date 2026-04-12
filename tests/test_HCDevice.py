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
