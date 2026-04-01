# AppArmor Next Steps (Local Plan)

Stand: 2026-04-01

## Ziel
AppArmor wieder aktivieren (`apparmor: true`) ohne Startup-Regressions, mit reproduzierbarer Testreihenfolge.

## Aktueller Zustand
- Add-on startet aktuell mit `apparmor: false`.
- Startpfad aktuell: `ENTRYPOINT ["/app/run.sh"]` + `#!/bin/bash`.
- Hauptproblem bisher: Permission-/PID1-Konflikte bei wechselnden Startpfaden und AppArmor-Regeln.

## Arbeitsprinzip
- Immer nur **eine Variable** pro Testlauf ändern.
- Nach jeder Änderung: Add-on neu bauen und Startlog ab Zeile 1 prüfen.
- Nur Regeln ergänzen, die durch konkrete DENIED-Meldungen belegt sind.

## Phase 1: Minimal funktionsfähiges Profil
1. `apparmor: true` in `hcpy/config.yaml` setzen.
2. `hcpy/apparmor.txt` auf minimalen Satz reduzieren (nur aktueller Startpfad):
   - `/app/run.sh rix,`
   - `/bin/bash rix,`
   - `/usr/bin/python3* rix,`
   - `/usr/local/bin/python3* rix,`
   - `/app/** r,`
   - `/app/**/*.py rix,`
   - `/config/** rw, /data/** rw, /tmp/** rw,`
   - `network inet/inet6 stream,dgram`
3. Add-on neu bauen/starten.
4. Ergebnis dokumentieren (OK / genaue Fehlermeldung).

## Phase 2: Denied-driven Erweiterung
1. Bei Fehlern nur **eine** Regel pro Iteration ergänzen.
2. Jede Iteration dokumentieren:
   - Zeit
   - Denied-Pfad
   - hinzugefügte Regel
   - Ergebnis
3. Erst wenn Start stabil ist: Login testen.

## Phase 3: Funktions-Checks
1. Start ohne Fehler
2. Web-UI erreichbar
3. Login-Flow (inkl. F12-Fallback) funktioniert
4. `refresh-devices` funktioniert
5. MQTT-Verbindung + Topic-Publishing funktioniert

## Phase 4: Härtung
1. Überbreite Regeln reduzieren (`/app/** rix` vermeiden, wo möglich konkretisieren)
2. Zusätzliche deny-Regeln vorsichtig ergänzen
3. Regressionstest (Phase 3 komplett wiederholen)

## Test-Checkliste (pro Build)
- [ ] Add-on baut
- [ ] Add-on startet
- [ ] Keine FATAL-Fehler im Startlog
- [ ] Web-UI lädt
- [ ] Login/Token ok
- [ ] MQTT online

## Notizen
- Nicht zwischen `/init`- und `run.sh`-Startpfad hin- und herwechseln, solange AppArmor debuggt wird.
- Erst Stabilität, dann Security-Härtung.
