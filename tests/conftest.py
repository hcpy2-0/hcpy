import os
import tempfile
from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_mqtt_client():
    """Mock MQTT client for testing"""
    client = Mock()
    client.publish = Mock()
    return client


@pytest.fixture
def sample_discovery_config():
    """Sample discovery configuration for testing"""
    return {
        "HA_DISCOVERY_PREFIX": "homeassistant",
        "MAGIC_OVERRIDES": {
            "BSH.Common.Setting.PowerState": {
                "component_type": "switch",
                "name": "Power State Override",
            }
        },
        "EXPAND_NAME": {"BSH.Common.Setting": 2},
        "SKIP_ENTITIES": ["BSH.Common.Program.ProgramGroup"],
        "DISABLED_ENTITIES": ["BSH.Common.Status.WiFiSignalStrength"],
        "DISABLED_EXCEPTIONS": ["BSH.Common.Status.WiFiSignalStrength.Override"],
        "ADDITIONAL_FEATURES": [],
    }


@pytest.fixture
def devices():
    """Sample device data for testing with realistic but sanitized data"""
    return [
        {
            "name": "test_oven",
            "description": {
                "brand": "BOSCH",
                "model": "TEST_MODEL",
                "revision": "2",
                "type": "Oven",
                "version": "4.2",
            },
            "features": {
                "256": {
                    "name": "BSH.Common.Status.DoorState",
                    "access": "read",
                    "available": "true",
                    "refCID": "03",
                    "refDID": "80",
                    "values": {"0": "Open", "1": "Closed"},
                },
                "257": {
                    "name": "BSH.Common.Status.LocalControlActive",
                    "access": "read",
                    "available": "true",
                    "refCID": "01",
                    "refDID": "00",
                },
                "258": {
                    "name": "Cooking.Oven.Option.SetpointTemperature",
                    "access": "readWrite",
                    "available": "true",
                    "refCID": "07",
                    "refDID": "A1",
                    "min": 30,
                    "max": 250,
                    "stepSize": 5,
                },
                "259": {
                    "name": "BSH.Common.Option.Duration",
                    "access": "readWrite",
                    "available": "true",
                    "refCID": "10",
                    "refDID": "82",
                    "min": 0,
                    "max": 7200,
                    "stepSize": 60,
                },
                "260": {
                    "name": "BSH.Common.Setting.ChildLock",
                    "access": "readWrite",
                    "available": "true",
                    "refCID": "01",
                    "refDID": "00",
                },
                "261": {
                    "name": "BSH.Common.Status.WiFiSignalStrength",
                    "access": "read",
                    "available": "true",
                    "refCID": "03",
                    "refDID": "80",
                    "values": {
                        "0": "No Signal",
                        "1": "Poor",
                        "2": "Fair",
                        "3": "Good",
                        "4": "Excellent",
                    },
                },
                "262": {
                    "name": "BSH.Common.Root.ActiveProgram",
                    "access": "read",
                    "available": "true",
                    "refCID": "03",
                    "refDID": "80",
                    "values": {"0": "None", "1": "Bake", "2": "Broil", "3": "Convection"},
                },
                "263": {
                    "name": "BSH.Common.Event.ProgramFinished",
                    "access": "read",
                    "available": "true",
                    "refCID": "15",
                    "refDID": "81",
                    "handling": "event",
                    "values": {
                        "0": "Program Started",
                        "1": "Program Finished",
                        "2": "Program Aborted",
                    },
                },
            },
            "host": "192.168.1.101",
            "iv": "OBFUSCATED_IV_1",
            "key": "OBFUSCATED_KEY_1",
        },
        {
            "name": "test_washer",
            "description": {
                "brand": "BOSCH",
                "model": "TEST_WASHER_MODEL",
                "revision": "1",
                "type": "Washer",
                "version": "3.1",
            },
            "features": {
                "300": {
                    "name": "BSH.Common.Status.DoorState",
                    "access": "read",
                    "available": "true",
                    "refCID": "03",
                    "refDID": "80",
                    "values": {"0": "Open", "1": "Closed"},
                },
                "301": {
                    "name": "LaundryCare.Washer.Option.Temperature",
                    "access": "readWrite",
                    "available": "true",
                    "refCID": "07",
                    "refDID": "A4",
                    "min": 20,
                    "max": 90,
                    "stepSize": 10,
                },
                "302": {
                    "name": "LaundryCare.Washer.Option.SpinSpeed",
                    "access": "readWrite",
                    "available": "true",
                    "refCID": "11",
                    "refDID": "A0",
                    "min": 400,
                    "max": 1600,
                    "stepSize": 200,
                },
                "303": {
                    "name": "LaundryCare.Washer.Program.Cotton",
                    "access": "read",
                    "available": "true",
                    "refCID": "03",
                    "refDID": "80",
                    "values": {"0": "Not Selected", "1": "Selected"},
                },
            },
            "host": "192.168.1.102",
            "iv": "OBFUSCATED_IV_2",
            "key": "OBFUSCATED_KEY_2",
        },
    ]


@pytest.fixture
def temp_discovery_config():
    """Create a temporary discovery config file"""
    config = {
        "HA_DISCOVERY_PREFIX": "homeassistant",
        "MAGIC_OVERRIDES": {},
        "EXPAND_NAME": {},
        "SKIP_ENTITIES": [],
        "DISABLED_ENTITIES": [],
        "DISABLED_EXCEPTIONS": [],
        "ADDITIONAL_FEATURES": [],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        import yaml

        yaml.dump(config, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    os.unlink(temp_path)
