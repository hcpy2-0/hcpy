# HomeConnect2MQTT

Lokale Steuerung von Bosch/Siemens Home Connect Geräten über MQTT.

## Voraussetzungen

- Home Connect Konto (App-Registrierung)
- MQTT-Broker (z.B. Mosquitto Addon)
- Geräte im selben Netzwerk wie Home Assistant

## Einrichtung (3 Schritte)

### 1. Addon installieren

Addon-Repository hinzufügen und das Addon installieren. MQTT wird automatisch erkannt wenn der Mosquitto-Broker als HA Addon läuft.

### 2. Über Web-UI anmelden

1. Öffne das Addon über die Seitenleiste ("Home Connect")
2. Klicke "Mit Home Connect anmelden"
3. Melde dich im neuen Tab mit deinem Home Connect Konto an
4. Kopiere die komplette `hcauth://` URL aus der Adressleiste
5. Füge sie in das Textfeld ein und klicke "Geräte konfigurieren"

### 3. Addon neustarten

Nach erfolgreicher Konfiguration das Addon neustarten. Die Geräte erscheinen automatisch in Home Assistant.

## MQTT

### Automatische Erkennung

Das Addon erkennt den MQTT-Broker automatisch in folgender Reihenfolge:

1. **Manuelle Konfiguration** — Falls MQTT Host/Port gesetzt sind
2. **HA Services** — Erkennung über `bashio::services mqtt`
3. **Netzwerk-Probe** — Verbindungstest auf core-mosquitto, localhost (Port 1883)

### Topics

| Topic | Beschreibung |
|-------|-------------|
| `homeconnect/{gerät}/state/{eigenschaft}` | Gerätestatus |
| `homeconnect/{gerät}/event/{event}` | Geräte-Events |
| `homeconnect/{gerät}/set` | Werte setzen |
| `homeconnect/{gerät}/activeProgram` | Programm starten |
| `homeconnect/{gerät}/selectedProgram` | Programm auswählen |
| `homeconnect/{gerät}/LWT` | Online/Offline Status |
| `homeconnect/{gerät}/watchdog` | Letzter Nachrichtenempfang |
| `homeconnect/LWT` | MQTT Bridge Status |

## Hostnamen

Die Geräte-Hostnamen aus der Home Connect Cloud sind oft Kurznamen (z.B. `Bosch-Dishwasher-ABC123`). Das Addon versucht diese automatisch aufzulösen:

1. Konfigurierter Domain-Suffix (z.B. `fritz.box`)
2. Häufige Router-Suffixe (`fritz.box`, `speedport.ip`, `home`, `lan`, `local`)
3. mDNS/Zeroconf Discovery

Falls die automatische Auflösung nicht funktioniert, kannst du die IP-Adresse manuell in `/config/devices.json` eintragen.

## Fehlerbehebung

| Problem | Lösung |
|---------|--------|
| "Keine Geräte konfiguriert" | Über die Web-UI anmelden |
| MQTT nicht verbunden | Mosquitto Addon installieren oder MQTT manuell konfigurieren |
| Gerät nicht erreichbar | IP-Adresse in devices.json manuell eintragen |
| WebSocket bricht ab | Watchdog erkennt dies und verbindet automatisch neu (nach max. 5 Min) |
| Login fehlgeschlagen | URL muss die komplette `hcauth://` Adresse sein |
| Token abgelaufen | Über "Geräte aktualisieren" oder erneuten Login |

## Unterstützte Geräte

- Geschirrspüler (TLS-PSK)
- Waschmaschinen (AES-CBC)
- Trockner
- Kaffeemaschinen
- Backöfen
- Dunstabzugshauben
- Kühlschränke
- Staubsaugerroboter

## Sicherheit

- AppArmor-Profil aktiv (eingeschränkte Dateizugriffe)
- Kein Host-Netzwerk-Zugriff
- MQTT-Passwort wird in der UI maskiert
- Verschlüsselungsschlüssel werden in Logs redaktiert
- Token werden in `/data` gespeichert (Container-isoliert)
