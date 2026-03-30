![dishwasher installed in a kitchen](images/kitchen.jpg)

# HomeConnect2MQTT — Local Control for Home Connect Appliances

Local WebSocket bridge between Bosch/Siemens Home Connect appliances and MQTT, with Home Assistant integration.

> **No cloud dependency for daily operation.** The cloud login is only needed once to retrieve device credentials.

## Features

| Feature | Original | This Fork |
|---------|----------|-----------|
| Local WebSocket control | Yes | Yes |
| MQTT bridge | Yes | Yes |
| HA MQTT Auto-Discovery | Yes | Yes |
| **Web-UI for setup** | No (SSH/Docker required) | **Yes (HA Ingress)** |
| **MQTT Auto-Discovery** | No (manual config) | **Yes (automatic)** |
| **Host auto-resolution** | No (manual DNS) | **Yes (fritz.box, mDNS, etc.)** |
| **Token refresh** | No (re-login every time) | **Yes (persistent token)** |
| **Device merge** | No (overwrites devices.json) | **Yes (preserves manual edits)** |
| **Watchdog reconnect** | No (silent disconnect) | **Yes (5 min timeout)** |
| **AppArmor security** | No | **Yes** |
| **Secret redaction in logs** | No | **Yes** |

## Quick Start (Home Assistant Addon)

### 1. Add Repository

[![Add this add-on repository to your Home Assistant instance.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub%2Ecom%2Fhcpy2%2D0%2Fhcpy%2F)

### 2. Login via Web-UI

Open "Home Connect" in the HA sidebar, click "Login", follow the steps.

### 3. Done

Devices appear automatically in Home Assistant via MQTT Discovery.

## MQTT Auto-Discovery

The addon automatically detects your MQTT broker:

1. **HA Services** — detected via `bashio::services mqtt` (Mosquitto addon)
2. **Network probe** — connection test on `core-mosquitto`, `localhost:1883`
3. **Manual config** — set MQTT Host/Port in addon settings

No manual MQTT configuration needed if you use the Mosquitto addon.

## Host Resolution

Device hostnames from the Home Connect cloud are short names (e.g. `Bosch-Dishwasher-ABC123`). The addon resolves them automatically:

1. User-configured suffix (e.g. `fritz.box`)
2. Common router suffixes: `fritz.box`, `speedport.ip`, `home`, `lan`, `local`
3. mDNS/Zeroconf discovery

## MQTT Topics

| Topic | Description |
|-------|-------------|
| `homeconnect/{device}/state/{property}` | Device state values |
| `homeconnect/{device}/event/{event}` | Device events |
| `homeconnect/{device}/set` | Set values (JSON) |
| `homeconnect/{device}/activeProgram` | Start a program |
| `homeconnect/{device}/selectedProgram` | Select a program |
| `homeconnect/{device}/LWT` | Device online/offline |
| `homeconnect/{device}/watchdog` | Last message timestamp |
| `homeconnect/LWT` | Bridge online/offline |

### Setting values

```json
[{"uid": 539, "value": 2}]
```

Topic: `homeconnect/coffeemaker/set`

### Starting a program

```json
{"program": 8196, "options": [{"uid": 558, "value": 600}]}
```

Topic: `homeconnect/dishwasher/activeProgram`

## Security

| Measure | Details |
|---------|---------|
| AppArmor | Restrictive profile, only needed paths allowed |
| host_network | `false` — no host network access |
| hassio_role | `default` — minimal Supervisor API rights |
| MQTT password | Masked in HA UI (password schema type) |
| Secret redaction | `key` and `iv` fields redacted in all log output |
| MQTT Auto-Discovery | No cleartext passwords in config needed |
| Graceful shutdown | SIGTERM/SIGINT handling with process cleanup |
| Container isolation | Token stored in `/data` (not user-accessible) |

## Standalone Usage (without Home Assistant)

```bash
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
pip3 install -r requirements-extra.txt

# Login (once)
python3 hc-login.py config/devices.json

# Copy and edit config
cp config/config.ini.example config/config.ini

# Run
python3 hc2mqtt.py --config config/config.ini
```

## File Structure

```
├── Dockerfile                    # HA Base Image (Alpine)
├── build.yaml                    # Multi-arch build config
├── run.sh                        # Entrypoint (HA Addon + Standalone)
├── requirements.txt              # Core Python dependencies
├── requirements-extra.txt        # Web-UI + zeroconf
├── hc2mqtt.py                    # MQTT bridge (patched: watchdog, fallback)
├── hc-login.py                   # OAuth login (patched: token refresh, merge)
├── HADiscovery.py                # HA MQTT Discovery (patched: redaction)
├── HCDevice.py                   # Device abstraction
├── HCSocket.py                   # WebSocket (TLS-PSK / AES-CBC)
├── HCxml2json.py                 # XML → JSON converter
├── discovery.yaml                # Discovery configuration
├── web-ui/                       # Flask Web-UI
│   ├── app.py
│   └── templates/index.html
├── scripts/
│   └── resolve_hosts.py          # Automatic host resolution
├── home-assistant-addon/
│   ├── config.yaml               # Addon config (Ingress, AppArmor, etc.)
│   ├── apparmor.txt              # Security profile
│   ├── DOCS.md                   # Addon documentation
│   └── translations/
│       ├── de.yaml
│       └── en.yaml
└── config/
    └── config.ini.example        # Standalone config template
```

## Supported Devices

- Dishwashers (TLS-PSK encrypted)
- Washing machines (AES-CBC encrypted)
- Dryers
- Coffee machines
- Ovens
- Range hoods
- Refrigerators
- Cleaning robots

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No devices configured" | Login via Web-UI |
| MQTT not connected | Install Mosquitto addon or configure MQTT manually |
| Device unreachable | Enter IP address in devices.json manually |
| Silent disconnect | Watchdog detects and reconnects (max 5 min) |
| Login failed | Paste the complete `hcauth://` URL |
| `sslpsk` build error | Expected on Python 3.13+ (TLS-PSK devices won't work) |
| `[Errno 111] Connection refused` | MQTT auto-discovery handles this automatically |

## Credits

Based on [hcpy2-0/hcpy](https://github.com/hcpy2-0/hcpy) by @pmagyar, @Meatballs1 and contributors.

## License

MIT License — see [LICENSE](LICENSE).
