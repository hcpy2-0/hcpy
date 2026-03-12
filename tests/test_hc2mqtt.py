import json
from unittest.mock import Mock, patch

import pytest

from hc2mqtt import client_connect, handle_device_message


def make_device(state=None):
    """Build a mock device with a .state dict."""
    device = Mock()
    device.state = state if state is not None else {}
    return device


def make_client(connected=True):
    """Build a mock MQTT client."""
    client = Mock()
    client.is_connected.return_value = connected
    return client


def published_payloads(client):
    """Return {topic: payload} dict from client.publish calls."""
    return {c.args[0]: c.args[1] for c in client.publish.call_args_list}


TOPIC = "homeconnect/TestOven"
NAME = "TestOven"


@patch("hc2mqtt.hcprint")
class TestNoop:
    def test_none_message(self, _hcprint):
        client = make_client()
        device = make_device()
        ps = {}
        handle_device_message(None, device, ps, client, TOPIC, NAME)
        client.publish.assert_not_called()
        assert ps == {}

    def test_empty_message(self, _hcprint):
        client = make_client()
        device = make_device()
        ps = {}
        handle_device_message({}, device, ps, client, TOPIC, NAME)
        client.publish.assert_not_called()
        assert ps == {}

    def test_all_values_unchanged(self, _hcprint):
        """When every key in the message matches published_state, nothing publishes."""
        client = make_client()
        device = make_device({"BSH.Common.Status.DoorState": "Closed"})
        ps = {"BSH.Common.Status.DoorState": "Closed"}

        handle_device_message(
            {"BSH.Common.Status.DoorState": "Closed"}, device, ps, client, TOPIC, NAME
        )
        client.publish.assert_not_called()


@patch("hc2mqtt.hcprint")
class TestFirstPublish:
    def test_all_keys_published_when_published_state_empty(self, _hcprint):
        client = make_client()
        device = make_device()
        ps = {}

        msg = {
            "BSH.Common.Status.DoorState": "Closed",
            "BSH.Common.Setting.PowerState": "On",
            "BSH.Common.Status.OperationState": "Ready",
        }
        handle_device_message(msg, device, ps, client, TOPIC, NAME)

        assert client.publish.call_count == 3
        payloads = published_payloads(client)
        assert payloads[f"{TOPIC}/state/bsh_common_status_doorstate"] == "Closed"
        assert payloads[f"{TOPIC}/state/bsh_common_setting_powerstate"] == "On"
        assert payloads[f"{TOPIC}/state/bsh_common_status_operationstate"] == "Ready"


@patch("hc2mqtt.hcprint")
class TestDiffPublish:
    def test_only_changed_key_published(self, _hcprint):
        client = make_client()
        device = make_device(
            {
                "BSH.Common.Status.DoorState": "Closed",
                "BSH.Common.Setting.PowerState": "On",
                "BSH.Common.Status.OperationState": "Ready",
            }
        )
        ps = {
            "BSH.Common.Status.DoorState": "Closed",
            "BSH.Common.Setting.PowerState": "On",
            "BSH.Common.Status.OperationState": "Ready",
        }

        msg = {
            "BSH.Common.Status.DoorState": "Open",
            "BSH.Common.Setting.PowerState": "On",
            "BSH.Common.Status.OperationState": "Ready",
        }
        handle_device_message(msg, device, ps, client, TOPIC, NAME)

        assert client.publish.call_count == 1
        payloads = published_payloads(client)
        assert payloads[f"{TOPIC}/state/bsh_common_status_doorstate"] == "Open"


@patch("hc2mqtt.hcprint")
class TestNoneValues:
    def test_none_for_new_key_skipped(self, _hcprint):
        """A new key with None value is not stored or published."""
        client = make_client()
        device = make_device()
        ps = {}

        handle_device_message(
            {"BSH.Common.Status.DoorState": None}, device, ps, client, TOPIC, NAME
        )

        client.publish.assert_not_called()
        assert "BSH.Common.Status.DoorState" not in device.state
        assert "BSH.Common.Status.DoorState" not in ps

    def test_none_for_existing_key_published(self, _hcprint):
        """An existing key set to None is a real change and gets published."""
        client = make_client()
        device = make_device({"BSH.Common.Status.DoorState": "Closed"})
        ps = {"BSH.Common.Status.DoorState": "Closed"}

        handle_device_message(
            {"BSH.Common.Status.DoorState": None}, device, ps, client, TOPIC, NAME
        )

        assert client.publish.call_count == 1
        payloads = published_payloads(client)
        assert payloads[f"{TOPIC}/state/bsh_common_status_doorstate"] == "None"
        assert ps["BSH.Common.Status.DoorState"] is None
        assert device.state["BSH.Common.Status.DoorState"] is None


@patch("hc2mqtt.hcprint")
class TestEvents:
    def test_event_published_to_event_topic(self, _hcprint):
        client = make_client()
        device = make_device()
        ps = {}

        msg = {"BSH.Common.Event.ProgramFinished": "Program Finished"}
        handle_device_message(msg, device, ps, client, TOPIC, NAME)

        assert client.publish.call_count == 1
        topic, payload = client.publish.call_args.args[0], client.publish.call_args.args[1]
        assert topic == f"{TOPIC}/event/bsh_common_event_programfinished"
        assert json.loads(payload) == {"event_type": "Program Finished"}

    def test_event_not_stored_in_state(self, _hcprint):
        client = make_client()
        device = make_device()
        ps = {}

        msg = {"BSH.Common.Event.ProgramFinished": "Program Finished"}
        handle_device_message(msg, device, ps, client, TOPIC, NAME)

        assert "BSH.Common.Event.ProgramFinished" not in device.state
        assert "BSH.Common.Event.ProgramFinished" not in ps

    def test_event_not_stored_in_published_state(self, _hcprint):
        """Events bypass the diff mechanism entirely."""
        client = make_client()
        device = make_device()
        ps = {}

        msg = {"BSH.Common.Event.ProgramFinished": "Done"}
        handle_device_message(msg, device, ps, client, TOPIC, NAME)
        handle_device_message(msg, device, ps, client, TOPIC, NAME)

        # Event published both times since it's not diffed.
        event_calls = [c for c in client.publish.call_args_list if "event/" in c.args[0]]
        assert len(event_calls) == 2

    def test_mixed_events_and_state(self, _hcprint):
        client = make_client()
        device = make_device()
        ps = {}

        msg = {
            "BSH.Common.Status.DoorState": "Closed",
            "BSH.Common.Event.ProgramFinished": "Done",
        }
        handle_device_message(msg, device, ps, client, TOPIC, NAME)

        payloads = published_payloads(client)
        assert f"{TOPIC}/state/bsh_common_status_doorstate" in payloads
        assert f"{TOPIC}/event/bsh_common_event_programfinished" in payloads
        assert client.publish.call_count == 2


@patch("hc2mqtt.time")
@patch("hc2mqtt.HCSocket")
@patch("hc2mqtt.HCDevice")
@patch("hc2mqtt.publish_ha_discovery")
@patch("hc2mqtt.hcprint")
class TestClientConnectDiscovery:
    """Integration tests for discovery in client_connect."""

    DEVICE = {"host": "h", "name": "test", "key": "k", "features": {}}

    def _make_device(self, messages):
        """Create an HCDevice mock that delivers messages via run_forever."""
        dev = Mock()
        dev.state = {}

        def run_forever(on_message, on_open, on_close):
            for msg in messages:
                on_message(msg)

        dev.run_forever = run_forever
        return dev

    def test_fires_after_state(self, _print, mock_discovery, MockDevice, MockSocket, _time):
        MockDevice.return_value = self._make_device(
            [
                {"BSH.Common.Status.DoorState": "Closed"},
            ]
        )
        MockSocket.side_effect = [Mock(), SystemExit]

        with pytest.raises(SystemExit):
            client_connect(
                make_client(),
                self.DEVICE,
                TOPIC,
                "",
                False,
                ha_discovery=True,
                discovery_file="d",
                events_as_sensors=False,
            )

        assert mock_discovery.call_count == 1

    def test_not_fired_when_disabled(self, _print, mock_discovery, MockDevice, MockSocket, _time):
        client = make_client()
        MockDevice.return_value = self._make_device(
            [
                {"BSH.Common.Status.DoorState": "Closed"},
            ]
        )
        MockSocket.side_effect = [Mock(), SystemExit]

        with pytest.raises(SystemExit):
            client_connect(
                client,
                self.DEVICE,
                TOPIC,
                "",
                False,
                ha_discovery=False,
                discovery_file="d",
                events_as_sensors=False,
            )

        assert client.publish.call_count >= 1  # State was published.
        mock_discovery.assert_not_called()

    def test_fires_once_per_connection(
        self, _print, mock_discovery, MockDevice, MockSocket, _time
    ):
        client = make_client()
        MockDevice.return_value = self._make_device(
            [
                {"BSH.Common.Status.DoorState": "Closed"},
                {"BSH.Common.Setting.PowerState": "On"},
            ]
        )
        MockSocket.side_effect = [Mock(), SystemExit]

        with pytest.raises(SystemExit):
            client_connect(
                client,
                self.DEVICE,
                TOPIC,
                "",
                False,
                ha_discovery=True,
                discovery_file="d",
                events_as_sensors=False,
            )

        assert client.publish.call_count >= 2  # Both messages were processed.
        assert mock_discovery.call_count == 1

    def test_refires_after_reconnect(self, _print, mock_discovery, MockDevice, MockSocket, _time):
        MockDevice.side_effect = [
            self._make_device([{"BSH.Common.Status.DoorState": "Closed"}]),
            self._make_device([{"BSH.Common.Status.DoorState": "Closed"}]),
        ]
        MockSocket.side_effect = [Mock(), Mock(), SystemExit]

        with pytest.raises(SystemExit):
            client_connect(
                make_client(),
                self.DEVICE,
                TOPIC,
                "",
                False,
                ha_discovery=True,
                discovery_file="d",
                events_as_sensors=False,
            )

        assert mock_discovery.call_count == 2


@patch("hc2mqtt.hcprint")
class TestReconnectSync:
    """When the WebSocket drops and reconnects, published_state.clear() runs
    in the while True loop. Everything must republish even if values haven't
    changed, because the broker may have lost retained messages or HA may have
    restarted."""

    def test_clear_forces_full_republish(self, _hcprint):
        """Simulates the reconnect lifecycle: publish -> clear -> same values
        arrive -> all keys republish."""
        client = make_client()
        device = make_device()
        ps = {}

        state = {
            "BSH.Common.Status.DoorState": "Closed",
            "BSH.Common.Setting.PowerState": "On",
            "BSH.Common.Status.OperationState": "Ready",
        }
        handle_device_message(state, device, ps, client, TOPIC, NAME)
        assert client.publish.call_count == 3
        client.reset_mock()

        # WebSocket drops, while loop creates new HCDevice and clears published_state.
        ps.clear()
        device.state.clear()

        # Same values arrive from /ro/allMandatoryValues on the new connection.
        handle_device_message(state, device, ps, client, TOPIC, NAME)
        assert client.publish.call_count == 3


@patch("hc2mqtt.hcprint")
class TestPayloadFormat:
    """HA sensors consume these MQTT payloads. Verify the str() / json.dumps()
    contract for every type that comes out of parse_values."""

    def test_bool_published_as_string(self, _hcprint):
        client = make_client()
        device = make_device()
        ps = {}

        handle_device_message(
            {
                "BSH.Common.Setting.ChildLock": True,
                "BSH.Common.Setting.RemoteStart": False,
            },
            device,
            ps,
            client,
            TOPIC,
            NAME,
        )

        payloads = published_payloads(client)
        assert payloads[f"{TOPIC}/state/bsh_common_setting_childlock"] == "True"
        assert payloads[f"{TOPIC}/state/bsh_common_setting_remotestart"] == "False"

    def test_integer_published_as_string(self, _hcprint):
        client = make_client()
        device = make_device()
        ps = {}

        handle_device_message(
            {"BSH.Common.Option.RemainingTime": 180}, device, ps, client, TOPIC, NAME
        )

        payload = client.publish.call_args.args[1]
        assert payload == "180"

    def test_dict_published_as_json(self, _hcprint):
        client = make_client()
        device = make_device()
        ps = {}

        handle_device_message(
            {"ipV4": {"ipAddress": "198.51.100.50"}},
            device,
            ps,
            client,
            TOPIC,
            NAME,
        )

        payload = client.publish.call_args.args[1]
        assert json.loads(payload) == {"ipAddress": "198.51.100.50"}


@patch("hc2mqtt.hcprint")
class TestDictComparison:
    """Dict values (ipV4, ipV6, Timezone) need deep comparison via Python's !=.
    These are the only type where equality semantics are non-obvious."""

    def test_same_dict_not_republished(self, _hcprint):
        client = make_client()
        device = make_device()
        ps = {}

        msg = {"ipV4": {"ipAddress": "198.51.100.50"}}
        handle_device_message(msg, device, ps, client, TOPIC, NAME)
        client.reset_mock()

        # Same dict content, different object.
        msg2 = {"ipV4": {"ipAddress": "198.51.100.50"}}
        handle_device_message(msg2, device, ps, client, TOPIC, NAME)
        client.publish.assert_not_called()

    def test_changed_nested_value_republished(self, _hcprint):
        client = make_client()
        device = make_device({"ipV4": {"ipAddress": "198.51.100.50"}})
        ps = {"ipV4": {"ipAddress": "198.51.100.50"}}

        handle_device_message(
            {"ipV4": {"ipAddress": "198.51.100.99"}}, device, ps, client, TOPIC, NAME
        )

        assert client.publish.call_count == 1


@patch("hc2mqtt.hcprint")
class TestMqttDisconnected:
    def test_state_updated_when_disconnected(self, _hcprint):
        client = make_client(connected=False)
        device = make_device()
        ps = {}

        handle_device_message(
            {"BSH.Common.Status.DoorState": "Closed"}, device, ps, client, TOPIC, NAME
        )

        assert device.state["BSH.Common.Status.DoorState"] == "Closed"

    def test_published_state_not_updated_when_disconnected(self, _hcprint):
        client = make_client(connected=False)
        device = make_device()
        ps = {}

        handle_device_message(
            {"BSH.Common.Status.DoorState": "Closed"}, device, ps, client, TOPIC, NAME
        )

        assert "BSH.Common.Status.DoorState" not in ps
        client.publish.assert_not_called()

    def test_stale_value_published_after_reconnect(self, _hcprint):
        """If the value didn't change between disconnect and reconnect,
        it still gets published because published_state never recorded it."""
        client = make_client(connected=False)
        device = make_device()
        ps = {}

        handle_device_message(
            {"BSH.Common.Status.DoorState": "Closed"}, device, ps, client, TOPIC, NAME
        )

        client.is_connected.return_value = True
        # Same value, but published_state doesn't have it.
        handle_device_message(
            {"BSH.Common.Status.DoorState": "Closed"}, device, ps, client, TOPIC, NAME
        )

        assert client.publish.call_count == 1
        assert ps["BSH.Common.Status.DoorState"] == "Closed"


@patch("hc2mqtt.hcprint")
class TestRetainFlag:
    def test_state_published_with_retain(self, _hcprint):
        client = make_client()
        device = make_device()
        ps = {}

        handle_device_message(
            {"BSH.Common.Status.DoorState": "Closed"}, device, ps, client, TOPIC, NAME
        )

        call_kwargs = client.publish.call_args_list[0]
        assert call_kwargs.kwargs.get("retain") is True or (
            len(call_kwargs.args) > 2 and call_kwargs.args[2] is True
        )

    def test_event_published_with_retain(self, _hcprint):
        client = make_client()
        device = make_device()
        ps = {}

        handle_device_message(
            {"BSH.Common.Event.ProgramFinished": "Done"}, device, ps, client, TOPIC, NAME
        )

        call_kwargs = client.publish.call_args_list[0]
        assert call_kwargs.kwargs.get("retain") is True or (
            len(call_kwargs.args) > 2 and call_kwargs.args[2] is True
        )


@patch("hc2mqtt.hcprint")
class TestTopicFormatting:
    def test_dots_replaced_with_underscores(self, _hcprint):
        client = make_client()
        device = make_device()
        ps = {}

        handle_device_message(
            {"BSH.Common.Status.DoorState": "Closed"}, device, ps, client, TOPIC, NAME
        )

        topic = client.publish.call_args_list[0].args[0]
        assert topic == f"{TOPIC}/state/bsh_common_status_doorstate"


@patch("hc2mqtt.hcprint")
class TestSentinel:
    def test_sentinel_distinguishes_never_published_from_none(self, _hcprint):
        """A key published as None should not re-publish when it arrives as None again.
        But a key never published should publish even if the value is None (for existing keys)."""
        client = make_client()
        device = make_device({"BSH.Common.Status.DoorState": "Closed"})
        ps = {}

        # First time: None for existing key. Never published, so it's new.
        handle_device_message(
            {"BSH.Common.Status.DoorState": None}, device, ps, client, TOPIC, NAME
        )
        assert client.publish.call_count == 1
        assert ps["BSH.Common.Status.DoorState"] is None
        client.reset_mock()

        # Second time: None again. Already published as None, skip.
        handle_device_message(
            {"BSH.Common.Status.DoorState": None}, device, ps, client, TOPIC, NAME
        )
        client.publish.assert_not_called()
