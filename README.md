![dishwasher installed in a kitchen](images/kitchen.jpg)

# HomeConnect2MQTT

Local WebSocket bridge between Bosch/Siemens Home Connect appliances and MQTT, with Home Assistant add-on support.

> Cloud login is only needed for initial setup/token refresh. Daily device control is local.

## Quick Start (Home Assistant Add-on)

### 1. Add repository

[![Add this add-on repository to your Home Assistant instance.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FDerSep%2Fhcpyhc2mqtt)

### 2. Install add-on and open Web UI

Open **Home Connect** in the Home Assistant sidebar.

### 3. Login and configure devices

1. Click **Mit Home Connect anmelden**.
2. Complete login in the opened browser tab.
3. Paste the final redirect URL into the add-on UI.
4. Click **Geraete konfigurieren**.

Important: The pasted URL must contain `code=`.

If your browser does not show the final URL clearly:

1. Press `F12`
2. Open `Network`
3. Find request URL starting with `hcauth://auth/prod?code=`
4. Copy that full URL and paste it into the add-on UI

## Features in this fork

- Ingress Web UI for setup
- MQTT auto-discovery (HA service + fallback probe)
- Token persistence and refresh
- Device merge (preserve existing hosts)
- Hostname auto-resolution (`fritz.box`, `lan`, `local`, mDNS)
- WebSocket watchdog/reconnect
- Add-on logs panel in UI

## Current Add-on Status

- `apparmor: false` (temporary compatibility setting in this fork)
- `host_network: false`
- `hassio_api: true`
- `hassio_role: default`

## MQTT Topics

- `homeconnect/{device}/state/{property}`
- `homeconnect/{device}/event/{event}`
- `homeconnect/{device}/set`
- `homeconnect/{device}/activeProgram`
- `homeconnect/{device}/selectedProgram`
- `homeconnect/{device}/LWT`
- `homeconnect/{device}/watchdog`
- `homeconnect/LWT`

## Troubleshooting

- Login fails with `invalid_grant`: pasted link is not the final URL with `code=`.
- Web UI shows no devices: finish login once, then restart add-on.
- MQTT not connected: install/configure Mosquitto add-on or set MQTT host/port manually.

## Credits

Based on [hcpy2-0/hcpy](https://github.com/hcpy2-0/hcpy).

## License

MIT - see [LICENSE](LICENSE).
