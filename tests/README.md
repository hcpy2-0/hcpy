# HADiscovery Test Suite

Unit tests for the `HADiscovery.py` module.

## Quick Start

```bash
# Install dependencies
pip install -r tests/requirements-test.txt

# Run tests
pytest tests/
```

## Test Coverage

- Component detection (binary sensors, temperature, switches, numbers, selects, events, buttons, lights)
- Configuration handling (magic overrides, skip/disabled entities)
- Special cases (local control lockout, program session summary)
- Edge cases (missing config files, devices without descriptions)

## Fixtures

- `mock_mqtt_client` - Mock MQTT client
- `sample_discovery_config` - Sample discovery configuration
- `devices` - Test device data (obfuscated)

## Running Tests

```bash
# All tests
pytest tests/

# Specific test
pytest tests/test_HADiscovery.py::TestHADiscovery::test_basic_discovery_publication

# With coverage
pytest --cov=HADiscovery tests/
```

## Test Data

Uses realistic but obfuscated device data from BOSCH appliances (oven and washer).
