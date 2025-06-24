# HADiscovery Test Suite

This directory contains comprehensive unit tests for the `HADiscovery.py` module.

## Test Structure

- `conftest.py` - Shared fixtures and test configuration
- `test_HADiscovery.py` - Main test suite for HADiscovery functionality
- `requirements-test.txt` - Test dependencies

## Test Coverage

The test suite covers the following aspects of the HADiscovery module:

### Core Functionality
- Basic discovery publication
- Device information formatting
- MQTT topic and payload generation

### Component Type Detection
- Binary sensors (based on refCID/refDID)
- Temperature sensors
- Duration sensors
- Switches (for controllable features)
- Number components
- Select components (for program selection)
- Event components
- Button components
- Light components

### Configuration Handling
- Magic overrides functionality
- Expand name functionality
- Skip entities configuration
- Disabled entities configuration
- Config file fallback behavior

### Special Cases
- Local control lockout availability
- Program session summary special handling
- Enum with On/Off values becoming switches
- Features without names being skipped
- Devices without descriptions
- Events as sensors vs events

### Edge Cases
- Config file not found scenarios
- No config available
- Device-specific features (washer vs oven)

## Fixtures

The test suite uses several fixtures defined in `conftest.py`:

- `mock_mqtt_client` - Mock MQTT client for testing
- `sample_discovery_config` - Sample discovery configuration
- `obfuscated_devices` - Test device data with obfuscated keys and IPs
- `temp_discovery_config` - Temporary discovery config file

## Running the Tests

### Prerequisites

Install test dependencies:
```bash
pip install -r tests/requirements-test.txt
```

### Run All Tests

From the project root:
```bash
pytest tests/
```

### Run Specific Test File

```bash
pytest tests/test_HADiscovery.py
```

### Run Specific Test Method

```bash
pytest tests/test_HADiscovery.py::TestHADiscovery::test_basic_discovery_publication
```

### Run with Verbose Output

```bash
pytest -v tests/
```

### Run with Coverage

```bash
pytest --cov=HADiscovery tests/
```

## Test Data

The test suite uses obfuscated device data based on real Home Connect appliances:

- **Oven device**: BOSCH oven with various features including temperature sensors, switches, and programs
- **Washer device**: BOSCH washer with laundry-specific features

All sensitive information (keys, IPs) has been obfuscated for security.

## Test Categories

### Unit Tests
- Individual function behavior
- Component type detection logic
- Configuration parsing
- MQTT payload generation

### Integration Tests
- End-to-end discovery publication
- Configuration file handling
- Device feature processing

### Edge Case Tests
- Error handling
- Missing data scenarios
- Invalid configurations

## Contributing

When adding new features to `HADiscovery.py`, please add corresponding tests to ensure:

1. The new functionality works as expected
2. Edge cases are handled properly
3. Existing functionality is not broken
4. Test coverage remains high

## Notes

- Tests use mocking extensively to avoid external dependencies
- Device data is obfuscated but maintains realistic structure
- Tests are designed to be fast and reliable
- All tests should pass in isolation and as part of the full suite
