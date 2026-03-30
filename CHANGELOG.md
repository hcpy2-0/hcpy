## [0.5.0] - 2026-03-30 — "Friendly Fork"

### New Features
* **Web-UI** for setup via Home Assistant Ingress — no SSH or Docker commands needed
* **MQTT Auto-Discovery** — broker detected automatically (HA Services, network probe)
* **Host auto-resolution** — device hostnames resolved via DNS suffixes (fritz.box, speedport.ip, etc.) and mDNS
* **Token refresh** — persistent OAuth token, no re-login needed for device updates
* **Device merge** — devices.json preserves manual edits (IPs, FQDNs) on re-login
* **Watchdog** per device — detects silent WebSocket disconnects (5 min timeout), forces reconnect
* **Watchdog MQTT topic** — `{prefix}{device}/watchdog` publishes last message timestamp
* **"Update devices" button** in Web-UI — refresh device list without browser login

### Security
* **AppArmor profile** — restrictive security policy for the addon container
* **host_network: false** — no host network access
* **Secret redaction** — `key` and `iv` fields redacted in all log output (HADiscovery + hc2mqtt)
* **MQTT password masked** — `password` schema type in HA UI
* **hassio_role: default** — minimal Supervisor API permissions
* **Container-isolated token** — stored in /data, not user-visible /config

### HA Compliance
* **Ingress support** — Web-UI accessible from HA sidebar
* **addon_config map** — proper file access via /config
* **mqtt:want** (not need) — addon starts even without MQTT
* **watchdog** — TCP health check on ingress port
* **hot backup** — backup without stopping addon
* **Translations** — German and English for all config options
* **DOCS.md** — addon documentation following HA standards
* **build.yaml** — multi-arch HA base images (aarch64, amd64, armhf, armv7, i386)

### Bug Fixes
* **Issue #120** — WebSocket connections going silent are now detected and reconnected
* **Issue #215** — MQTT localhost fallback to core-mosquitto in HA addon context
* **Issue #108** — Device secrets (key/iv) no longer leaked in log output
* **Login cluster (#81, #116)** — Web-UI replaces F12 dev tools workflow

### Changes
* Dockerfile rebuilt on HA base images (Alpine + Python 3.13)
* run.sh completely rewritten with MQTT auto-discovery, graceful shutdown, Web-UI process management
* config.yaml updated: optional MQTT fields, ingress, AppArmor, new options
* .gitignore updated for Python project
* Removed: compose.yaml, .github/, .vscode/, linting configs

## [0.4.8] - 2025-07-15
* Show SingleKey ID login page
* Use valid default_entity_id
* HA MQTT options_id deprecation fix

## [0.4.6] - 2025-06-20
* Add Cooking.Oven.Option.SetpointTemperature as a controllable number in AutoDiscovery
* Add ZeoliteDry to discovery.yaml
* Add MIT License
* Support legacy devices with different message deviceType value

## [0.4.5] - 2025-04-09
* Small fix for events as sensors

## [0.4.4] - 2025-04-09
* Set cooking temps as C
* Process BaseProgram as a selectable Program
* Add an availability topic that disables controls when LocalControlActive is True
* Add config option to model events as sensors

## [0.4.3] - 2025-03-15
* ActiveProgram/SelectedProgram display shortened Program Name
* Added additional Dishcare options as switches
* Instantiate new device object on reconnect
* Dangerous entities disabled by default
* Allow named entities in set topic
* Replace DEVICE_NAME in discovery.yaml
* Add Cooking Light and Ambient Light

## [0.4.2] - 2025-03-04
* Fix parsing step where it is a float instead of an integer
* Revert use of step to indicate a writeable number value
* Add IDos to discovery.yaml as numbers

## [0.4.1] - 2025-03-03
* Allow discovery.yaml configuration by user

## [0.4.0] - 2025-02-28
### Breaking
* Moved to one topic per device attribute

## [0.3.0] - 2025-02-21
* Login update — remove redundant email/password arguments
* Discovery naming and initValue improvements
* Switches, buttons, numbers, select entities for controllable items

## [0.2.3] - 2025-02-13
* Fix payload off typo

## [0.2.2] - 2025-02-03
* Revert removal of features being stored in devices.json

## [0.2.1] - 2025-01-31
* Add Add-on link to Readme
* Fix stderr print

## [0.2.0] - 2025-01-31
### Breaking
* Use fully qualified names for attributes

## [0.1.8] - 2025-01-30
* Change hc-login due to hcaptcha

## [0.1.7] - 2025-01-30
* Fix MQTT reconnection exception
* Flush print all log messages

## [0.1.5] - 2024-10-07
* Execute hc login on first run

## [0.1.4] - 2024-09-25
* Revert host to name in mqtt topic

## [0.1.3] - 2024-08-19
* Add Home Assistant MQTT autodiscovery

## [0.1.2] - 2024-07-21
* New feature: selecting program

## [0.1.1] - 2024-05-14
* Multiple improvements: description changes, LWT, North America support, debug/domain options

## [0.1.0] - 2024-04-20
* Home Assistant Add-On
