#!/usr/bin/env python3
"""
Automatische Host-Auflösung für devices.json nach dem OAuth-Login.
Versucht Hostnamen aufzulösen und durch erreichbare IPs/FQDNs zu ersetzen.
"""
import json
import os
import re
import socket
import sys


def is_ip(host):
    """Prüft ob ein Host eine IP-Adresse ist."""
    try:
        socket.inet_aton(host)
        return True
    except socket.error:
        return False


def test_reachable(host, ports=(443, 80, 8080), timeout=2):
    """Testet ob ein Host über einen der Ports erreichbar ist."""
    for port in ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
            s.close()
            return True
        except (socket.timeout, socket.error, OSError):
            continue
    return False


def resolve_with_suffix(hostname, suffix, timeout=2):
    """Versucht hostname.suffix aufzulösen und zu erreichen."""
    fqdn = f"{hostname}.{suffix}"
    try:
        socket.getaddrinfo(fqdn, None)
        if test_reachable(fqdn, timeout=timeout):
            return fqdn
    except socket.gaierror:
        pass
    return None


def try_mdns_discovery(hostname, timeout=5):
    """Versucht mDNS/zeroconf Discovery als Fallback."""
    try:
        from zeroconf import ServiceBrowser, Zeroconf

        found = {}

        class Listener:
            def add_service(self, zc, type_, name):
                info = zc.get_service_info(type_, name)
                if info and info.server:
                    server = info.server.rstrip(".")
                    if hostname.lower() in server.lower():
                        addresses = info.parsed_addresses()
                        if addresses:
                            found[server] = addresses[0]

            def remove_service(self, zc, type_, name):
                pass

            def update_service(self, zc, type_, name):
                pass

        zc = Zeroconf()
        ServiceBrowser(zc, "_http._tcp.local.", Listener())

        import time
        time.sleep(timeout)
        zc.close()

        if found:
            # Return first match
            server, ip = next(iter(found.items()))
            return ip
    except ImportError:
        print("  zeroconf nicht installiert, mDNS-Discovery übersprungen", flush=True)
    except Exception as e:
        print(f"  mDNS-Discovery Fehler: {e}", flush=True)

    return None


def resolve_hosts(devices_file, user_suffix=""):
    """Hauptfunktion: Löst Hosts in devices.json auf."""
    if not os.path.exists(devices_file):
        print(f"Datei nicht gefunden: {devices_file}", flush=True)
        return

    with open(devices_file, "r") as f:
        devices = json.load(f)

    # DNS-Suffixe zum Probieren
    suffixes = []
    if user_suffix:
        suffixes.append(user_suffix)
    suffixes.extend(["fritz.box", "speedport.ip", "home", "lan", "local"])

    changed = False

    for device in devices:
        host = device.get("host", "")
        name = device.get("name", "?")

        if not host:
            print(f"  [{name}] Kein Host konfiguriert, überspringe", flush=True)
            continue

        # 1. Already an IP?
        if is_ip(host):
            if test_reachable(host):
                print(f"  [{name}] {host} (IP) erreichbar", flush=True)
            else:
                print(f"  [{name}] WARNUNG: {host} (IP) nicht erreichbar", flush=True)
            continue

        # 2. Already an FQDN (contains dot)?
        if "." in host:
            if test_reachable(host):
                print(f"  [{name}] {host} (FQDN) erreichbar", flush=True)
                continue
            else:
                print(f"  [{name}] {host} (FQDN) nicht erreichbar, versuche Alternativen...", flush=True)

        # 3. Try DNS suffixes
        resolved = None
        for suffix in suffixes:
            resolved = resolve_with_suffix(host, suffix)
            if resolved:
                print(f"  [{name}] {host} -> {resolved} (via .{suffix})", flush=True)
                device["host"] = resolved
                changed = True
                break

        if resolved:
            continue

        # 4. Try mDNS as fallback
        print(f"  [{name}] DNS fehlgeschlagen, versuche mDNS...", flush=True)
        mdns_result = try_mdns_discovery(host)
        if mdns_result:
            print(f"  [{name}] {host} -> {mdns_result} (via mDNS)", flush=True)
            device["host"] = mdns_result
            changed = True
            continue

        # 5. Not found
        print(f"  [{name}] WARNUNG: {host} konnte nicht aufgelöst werden", flush=True)

    if changed:
        # Create backup
        backup_file = devices_file + ".backup"
        if not os.path.exists(backup_file):
            import shutil
            shutil.copy2(devices_file, backup_file)
            print(f"  Backup erstellt: {backup_file}", flush=True)

        # Write updated file
        with open(devices_file, "w") as f:
            json.dump(devices, f, ensure_ascii=True, indent=4)
        print("  Host-Auflösung abgeschlossen, devices.json aktualisiert", flush=True)
    else:
        print("  Keine Änderungen nötig", flush=True)


if __name__ == "__main__":
    devices_path = sys.argv[1] if len(sys.argv) > 1 else "/config/devices.json"
    domain_suffix = sys.argv[2] if len(sys.argv) > 2 else ""
    print(f"Host-Auflösung für {devices_path}...", flush=True)
    resolve_hosts(devices_path, domain_suffix)
