#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mesh_roaming_pi.py
==================

Live-Dienst fuer ein OpenWrt-Mesh-Netzwerk (usteer), gedacht zum
Dauerbetrieb als systemd-Dienst auf einem Raspberry Pi (z.B. neben openHAB).

Alle netzwerkspezifischen und variablen Parameter (Router, IPs, AP-
Interface-Namen, Kartenlayout, Schwellwerte, ...) kommen aus EINER
Konfigurationsdatei (JSON, Pfad ueber MESH_ROAMING_CONFIG, Default
/etc/mesh-roaming/config.json) statt aus Konstanten im Code - siehe
examples/config.example.json als Vorlage. Damit laesst sich derselbe
Code fuer ein anderes Mesh/Netzwerk einsetzen, ohne dieses Skript oder die
HTML-Datei zu aendern.

Was der Dienst macht:
- Pollt alle Mesh-Router ueber SSH (ein Hintergrund-Thread je Router), per
  ubus-Abfragen fuer hostapd-Clients, usteer, DHCP-Leases, ARP.
- Fasst die Ergebnisse serverseitig zusammen und erkennt Roam-/Connect-/
  Disconnect-Ereignisse EINMAL zentral (nicht im Browser) -> das
  Ereignis-Log, Nicknames und der letzte bekannte Verbindungsstatus liegen
  in einer SQLite-Datei und sind damit von jedem Geraet im Netz aus
  identisch sichtbar.
- Liefert per HTTP: "/" die Live-Seite (mesh-lageplan-live.html im selben
  Ordner), "/config.json" die netzwerkspezifischen Anzeige-Parameter
  (Router/Kartenlayout/Schwellwerte) fuer die Seite, "/data.json" den
  aktuellen Live-Snapshot, "/api/status" nur die Erreichbarkeit je Router
  (ohne Geraetedaten), "POST /api/rename" zum Umbenennen eines Clients,
  "POST /api/erase" zum sofortigen Loeschen aller Daten einer MAC-Adresse
  (Art. 17 DSGVO).
- Begrenzt die Aufbewahrung personenbezogener, geraetebezogener Daten
  automatisch auf "privacy.retention_days" Tage nach der letzten
  Beobachtung des jeweiligen Geraets (Art. 5 Abs. 1 lit. e DSGVO) und
  fuehrt parallel eine anonyme, stuendliche Zusammenfassung ohne MAC-Adresse
  fort, die fuer Langzeit-Trendanalysen unbegrenzt aufbewahrt werden darf -
  siehe README.md, Abschnitt "Datenschutz-Hinweis (DSGVO)".
- Optional (nur wenn mqtt.broker in der Konfiguration gesetzt ist):
  veroeffentlicht einfache Zusammenfassungs-Metriken per MQTT (optional mit
  Benutzername/Passwort und TLS, ueber mosquitto_pub), z.B. um sie
  wie andere Smarthome-Metriken ueber openHAB in InfluxDB/Grafana
  weiterzuverarbeiten. Die Kernvisualisierung bleibt bewusst AUSSERHALB
  von InfluxDB.

Start (manuell zum Testen, aus dem Projektverzeichnis heraus):
    MESH_ROAMING_CONFIG=./examples/config.example.json python3 src/mesh_roaming_pi.py
Anzeige: http://<pi-ip>:8765/
Als Dienst: siehe systemd/mesh-roaming.service bzw.
docs/deployment-raspbian-openhab.md.

Copyright Benjamin Johann (mesh-roaming-dashboard)
SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""

__version__ = "2.0"  # MESH_ROAMING_VERSION - bei Release mit control/Version abgleichen

import errno
import json
import os
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get("MESH_ROAMING_CONFIG", "/etc/mesh-roaming/config.json")

MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$", re.IGNORECASE)

# Mindestabstand zwischen zwei Durchlaeufen der Speicherbegrenzung
# (_prune_expired) - die eigentliche Pollrate (Default: 1 s) ist dafuer
# unnoetig oft, Minutengenauigkeit reicht fuer den DSGVO-Zweck voellig aus.
_PRUNE_INTERVAL_MS = 60_000


def _hour_bucket(ts_ms):
    """UTC-Stundenbucket (z. B. "2026-10-20T07") fuer die anonyme Statistik."""
    return time.strftime("%Y-%m-%dT%H", time.gmtime(ts_ms / 1000))

# --- Defaults - werden von der Konfigurationsdatei ueberschrieben/ergaenzt --

DEFAULT_CONFIG = {
    "network": {"label": "Mesh-Netzwerk"},
    "ssh": {
        "user": "root",
        "key_path": "/etc/mesh-roaming/id_ed25519",
        "connect_timeout_sec": 5,
        "command_timeout_sec": 8,
        "control_master": True,
        "control_persist": "60s",
    },
    "polling": {"interval_sec": 1},
    "http": {"bind": "0.0.0.0", "port": 8765},
    "storage": {
        "db_path": "/var/lib/mesh-roaming/state.db",
        "runtime_dir": "/run/mesh-roaming",
    },
    "html_path": None,  # None = mesh-lageplan-live.html neben diesem Skript
    "ap_ifnames": [
        "phy0-ap0", "phy0-ap1", "phy0-ap2", "phy0-ap3",
        "phy1-ap0", "phy1-ap1", "phy1-ap2", "phy1-ap3",
    ],
    "roaming": {
        "reachable_signal_threshold_dbm": -75,
        "shift_amount_min": 0.15,
        "shift_amount_max": 0.70,
        # Sekundaere Sicherheitsgrenze gegen unbegrenztes Wachstum (z. B. bei
        # falsch konfiguriertem "privacy.retention_days" oder sehr hoher
        # Ereignisrate). Die eigentliche, DSGVO-relevante Speicherbegrenzung
        # ist "privacy.retention_days" unten - NICHT diese Zahl: die hier
        # begrenzt nur die Anzahl Eintraege, nicht deren Alter.
        "log_max_entries": 200,
    },
    # Datenschutz/DSGVO: siehe README.md, Abschnitt "Datenschutz-Hinweis
    # (DSGVO)" fuer die vollstaendige Begruendung. Personenbezogene,
    # geraetebezogene Daten (MAC-Adresse, DHCP-Hostname, IP, Nickname,
    # Roaming-Log-Eintraege mit MAC) werden spaetestens "retention_days"
    # Tage NACH DEM LETZTEN BEOBACHTEN dieses Geraets automatisch und
    # dauerhaft geloescht (Art. 5 Abs. 1 lit. e DSGVO, Speicherbegrenzung) -
    # nicht nur aus der Anzeige entfernt, sondern aus der SQLite-Datenbank.
    # "anonymous_stats_enabled" fuehrt parallel dazu eine stuendliche,
    # geraeteunabhaengige Zusammenfassung (Ereignisanzahl + Ø-Signalstaerke
    # je Router/Band) fort, die KEINE MAC-Adresse enthaelt und damit kein
    # personenbezogenes Datum im Sinne der DSGVO ist - diese darf und soll
    # fuer Langzeit-Trendanalysen unbegrenzt aufbewahrt werden, auch nachdem
    # die zugehoerigen Rohdaten laengst geloescht sind.
    "privacy": {
        "retention_days": 7,
        "anonymous_stats_enabled": True,
    },
    "signal": {
        "min_dbm": -90,
        "max_dbm": -30,
        "reference_rings_dbm": [-55, -70, -90],
    },
    "map": {
        "viewbox_width": 900,
        "viewbox_height": 600,
        "radius_inner": 16,
        "radius_outer": 100,
        "ssid_colors": ["#5b8dd6", "#d6905b", "#7fbf6b", "#b06bbf", "#5bb0b0", "#c2b95a"],
        # Feste Farbe je SSID (Name -> Hex), unabhaengig von Entdeckungsreihenfolge.
        # SSIDs ohne Eintrag hier fallen auf 'ssid_colors' (nach Reihenfolge) zurueck.
        # Schluessel werden case-insensitiv verglichen. Beispiel:
        # "ssid_colors_by_name": {"MeinWLAN": "#5fb56f", "Gaeste": "#d97b32"}
        "ssid_colors_by_name": {},
    },
    # Kanalauslastung - je Funkkarte (phy; ein Interface je phy wird auf dem
    # Router automatisch gewaehlt, egal ob AP, Client oder Mesh, s.
    # SURVEY_SHELL) per "iw dev <ifname>
    # survey dump" ermittelt und als gleitende Differenz ueber 'interval_sec'
    # neu berechnet (NICHT als Anteil seit Geraete-/Interface-Start - die
    # Zaehler aus dem Kernel sind kumulativ seit Interface-up). own/foreign
    # sind zwei kategoriale Farben, 'rest' ist bewusst ein neutraler,
    # unbunter "Rest-Track" statt einer dritten Kategorialfarbe (keine echte
    # dritte Identitaet, sondern ungenutzte Kapazitaet).
    "channel_util": {
        "interval_sec": 10,
        "colors": {
            "own": "#3987e5",
            "foreign": "#e66767",
            "rest": "#2f3d46",
        },
    },
    # WLAN-Scan der Nachbarkanaele (#13): alle 'interval_sec' Sekunden je
    # Router "iw scan dump" (0 = aus); 'trigger' = wo aktiv gescannt wird
    # (off/clients/all, s. build_scan_cmd); 'own_ssids' = zusaetzlich als
    # eigen geltende SSIDs (die SSIDs/BSSIDs der eigenen AP-Interfaces werden
    # automatisch erkannt); Netze, die laenger als 'max_age_sec' nicht mehr
    # gesehen wurden, fallen heraus.
    "scan": {
        "interval_sec": 60,
        "trigger": "clients",
        "own_ssids": [],
        "max_age_sec": 300,
    },
    "routers": [],
    # Benutzername/Passwort und TLS sind optional - leer/None = anonym bzw.
    # unverschluesselt. "port": None = Standardport (1883, mit TLS 8883).
    # "tls_cafile": None = System-Zertifikate aus "tls_capath" verwenden.
    "mqtt": {
        "broker": None,
        "port": None,
        "base_topic": "mesh-roaming",
        "publish_interval_sec": 10,
        "username": None,
        "password": None,
        "tls": False,
        "tls_cafile": None,
        "tls_capath": "/etc/ssl/certs",
        "tls_insecure": False,
    },
}


def deep_merge(base, override):
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(path):
    if not os.path.isfile(path):
        raise SystemExit(
            "Konfigurationsdatei nicht gefunden: %s\n"
            "mesh-roaming-config.example.json als Vorlage nehmen, nach %s kopieren "
            "und an das jeweilige Netzwerk anpassen." % (path, path)
        )
    with open(path, "r", encoding="utf-8") as f:
        try:
            user_cfg = json.load(f)
        except json.JSONDecodeError as e:
            raise SystemExit("Konfigurationsdatei %s ist kein gueltiges JSON: %s" % (path, e))

    cfg = deep_merge(DEFAULT_CONFIG, user_cfg)

    routers = cfg.get("routers") or []
    if not routers:
        raise SystemExit(
            "Konfiguration %s enthaelt keine Router (Schluessel 'routers' ist leer)." % path
        )
    seen_ids = set()
    for r in routers:
        for field in ("id", "ip"):
            if not r.get(field):
                raise SystemExit("Router-Eintrag ohne '%s' in %s: %r" % (field, path, r))
        if r["id"] in seen_ids:
            raise SystemExit("Router-ID doppelt vergeben in %s: %s" % (path, r["id"]))
        seen_ids.add(r["id"])
        r.setdefault("name", r["id"])
        r.setdefault("room", r["id"])
        r.setdefault("map_x", 0)
        r.setdefault("map_y", 0)
        r.setdefault("mgmt_ips", [])
        # "local": true markiert den Router, auf dem der Dienst selbst laeuft
        # (Betrieb direkt auf einem Mesh-Router statt auf einem
        # separaten Pi). Fuer diesen Eintrag wird KEINE SSH-Verbindung
        # aufgebaut, die ubus-Abfrage laeuft direkt lokal - spart eine
        # SSH-Verbindung und funktioniert auch ohne eigenen Schluessel-Eintrag
        # in den eigenen authorized_keys. Bei allen anderen Setups (Dienst auf
        # separatem Pi) bleibt dieses Feld ueberall false/weggelassen.
        r.setdefault("local", False)
        # "role": "ap" (Standard) = Access Point mit Clients/Roaming;
        # "sensor" = Messpunkt, z. B. ein Router, der nur als WLAN-Client im
        # Netz haengt - von ihm wird nur die Kanalauslastung abgefragt (keine
        # Clients, DHCP-Leases oder ARP-Tabelle, s. build_remote_cmd()).
        r.setdefault("role", "ap")
        if r["role"] not in ROLES:
            raise SystemExit("Router %s in %s: unbekannte Rolle %r (erlaubt: %s)"
                             % (r["id"], path, r["role"], ", ".join(ROLES)))

    if not cfg.get("ap_ifnames"):
        raise SystemExit("Konfiguration %s: 'ap_ifnames' ist leer." % path)
    if not cfg["ssh"].get("key_path"):
        raise SystemExit("Konfiguration %s: 'ssh.key_path' fehlt." % path)
    if not cfg.get("html_path"):
        cfg["html_path"] = os.path.join(BASE_DIR, "mesh-lageplan-live.html")

    return cfg


# --- Aus der Konfiguration abgeleitete Laufzeit-Werte (siehe main()) -------

ROLES = ("ap", "sensor")

CONFIG = None
ROUTERS = {}          # id -> {ip, name, room, map_x, map_y, mgmt_ips, role}
AP_IFNAMES = []
UTIL_WINDOW_SEC = 10.0
REMOTE_CMDS = {}      # Rolle -> Befehlszeile (s. build_remote_cmd)
SCAN_INTERVAL_SEC = 60.0
SCAN_CMD = ""         # s. build_scan_cmd
SCAN_OWN_SSIDS = set()
SCAN_MAX_AGE_SEC = 300.0
SSH_USER = "root"
SSH_KEY = ""
SSH_CONNECT_TIMEOUT = 5
SSH_COMMAND_TIMEOUT = 8
USE_CONTROL_MASTER = True
CONTROL_PERSIST = "60s"
POLL_INTERVAL_SEC = 1.0
HTTP_BIND = "0.0.0.0"
HTTP_PORT = 8765
DB_PATH = "/var/lib/mesh-roaming/state.db"
RUNTIME_DIR = "/run/mesh-roaming"
HTML_PATH = ""
LOG_MAX = 200
MQTT_BROKER = None
MQTT_PORT = None
MQTT_BASE_TOPIC = "mesh-roaming"
MQTT_PUBLISH_INTERVAL_SEC = 10.0
MQTT_USERNAME = None
MQTT_PASSWORD = None
MQTT_TLS = False
MQTT_TLS_CAFILE = None
MQTT_TLS_CAPATH = "/etc/ssl/certs"
MQTT_TLS_INSECURE = False

STATE = None  # wird in main() gesetzt


# Kanalauslastung: Survey-Daten sind eine Eigenschaft der Funkkarte (phy) und
# ihres aktuellen Kanals, nicht eines einzelnen Interfaces - jedes Interface
# derselben phy liefert dieselben Zaehler. Deshalb wird auf dem Router je phy
# das erste Interface aus "iw dev" genommen, egal ob AP ("type AP"), Client
# ("type managed", z. B. phy1-sta0), Mesh oder Monitor. So funktioniert die
# Messung auch auf einem Router, der nur als WLAN-Client im Netz haengt, und
# mit beliebigen Interface-Namen (wlan0, mesh0, ...). Je phy entsteht ein
# Abschnitt "===SURVEY <phy> <ifname> <typ>===", bei Client-/AP-Interfaces
# gefolgt von "SSID=<name>" (das Netz, in dem der Messpunkt Client ist) und
# "DRIVER=<treiber>" (z. B. ath9k, mt7915e - zeigt, ob der Chip eigenen und
# fremden Verkehr trennen kann, #10).
SURVEY_SHELL = (
    "iw dev 2>/dev/null | awk '"
    "/^phy#/{p=\"phy\" substr($1,5)} "
    "$1==\"Interface\"{i=$2; s=\"\"} "
    "$1==\"ssid\"{s=substr($0, index($0, \"ssid \")+5)} "
    "$1==\"type\"{if(!(p in seen)){seen[p]=1; print p, i, $2, s}}' "
    "| while read p i t s; do echo \"===SURVEY $p $i $t===\"; "
    "[ -n \"$s\" ] && echo \"SSID=$s\"; "
    "d=$(readlink /sys/class/ieee80211/$p/device/driver 2>/dev/null); "
    "[ -n \"$d\" ] && echo \"DRIVER=${d##*/}\"; "
    "iw dev \"$i\" survey dump 2>/dev/null; done"
)


# Eigener Verkehr je Funkkarte (#11): Fuer JEDES WLAN-Interface die
# Sende-/Empfangszeit je verbundener Station aus "iw dev <if> station dump"
# (mac80211-Airtime-Zaehler "rx duration"/"tx duration" in Mikrosekunden,
# kumulativ). Beim AP sind das alle Clients, beim Messpunkt (Client) der AP,
# mit dem er verbunden ist. Ausgegeben werden nur Station-Zeile (MAC als
# Schluessel fuer die Differenzbildung - wird weder gespeichert noch
# angezeigt), die beiden Zeiten und das Signal (fuer den Signal-Rausch-
# Abstand eines Client-Interfaces, #12).
STATION_SHELL = (
    "iw dev 2>/dev/null | awk '"
    "/^phy#/{p=\"phy\" substr($1,5)} "
    "$1==\"Interface\"{print p, $2}' "
    "| while read p i; do echo \"===STA $p $i===\"; "
    "iw dev \"$i\" station dump 2>/dev/null "
    "| grep -E '^Station|rx duration|tx duration|signal:'; done"
)


def build_remote_cmd(role="ap"):
    parts = []
    if role != "sensor":
        # Messpunkte ("sensor") haben keine eigenen Clients - von ihnen werden
        # bewusst KEINE Client-Listen, DHCP-Leases oder ARP-Tabellen abgefragt
        # (Datenminimierung, s. README "Datenschutz").
        parts += ["echo ===WIRELESS===", "ubus call network.wireless status"]
        for ifname in AP_IFNAMES:
            parts.append("echo ===HOSTAPD-%s===" % ifname)
            parts.append("ubus call hostapd.%s get_clients 2>/dev/null" % ifname)
        parts.append("echo ===USTEER===")
        parts.append("ubus call usteer get_clients 2>/dev/null")
        parts.append("echo ===LEASES===")
        parts.append("cat /tmp/dhcp.leases 2>/dev/null")
        parts.append("echo ===ARP===")
        parts.append("cat /proc/net/arp 2>/dev/null")
    parts.append("echo ===SURVEYS===")
    parts.append(SURVEY_SHELL)
    parts.append("echo ===STATIONS===")
    parts.append(STATION_SHELL)
    parts.append("echo ===DONE===")
    return "; ".join(parts)


def known_hosts_path():
    return os.path.join(os.path.dirname(DB_PATH) or ".", "known_hosts")


def build_ssh_cmd(router_ip, remote_cmd):
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=%d" % int(SSH_CONNECT_TIMEOUT),
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=%s" % known_hosts_path(),
        "-i", SSH_KEY,
    ]
    if USE_CONTROL_MASTER:
        cmd += [
            "-o", "ControlMaster=auto",
            "-o", "ControlPath=%s/cm-%%r@%%h:%%p" % RUNTIME_DIR,
            "-o", "ControlPersist=%s" % CONTROL_PERSIST,
        ]
    cmd += ["%s@%s" % (SSH_USER, router_ip), remote_cmd]
    return cmd


# ---- Parsing der Router-Ausgaben -----------------------------------------

# "iw dev <ifname> survey dump"-Ausgabe. Felder sind seit Interface-Up
# kumulierte Millisekunden - "channel BSS receive time" (NL80211_SURVEY_INFO_
# TIME_BSS_RX) ist der neueste der Werte und nicht auf jedem Treiber verfuegbar
# (auf mt76-basierten Geraeten erwartet, auf aelteren ath9k-Chipsaetzen
# ggf. nicht) - fehlt er, bleibt "own"/"foreign" fuer dieses Interface None
# ("nicht verfuegbar" in der Anzeige), siehe _compute_util().
_SURVEY_FIELD_RE = {
    "active_ms": re.compile(r"channel active time:\s*([0-9]+)\s*ms"),
    "busy_ms": re.compile(r"channel busy time:\s*([0-9]+)\s*ms"),
    "receive_ms": re.compile(r"channel receive time:\s*([0-9]+)\s*ms"),
    "transmit_ms": re.compile(r"channel transmit time:\s*([0-9]+)\s*ms"),
    "bss_receive_ms": re.compile(r"channel BSS receive time:\s*([0-9]+)\s*ms"),
}
_SURVEY_NOISE_RE = re.compile(r"noise:\s*(-?[0-9]+)\s*dBm")
_SURVEY_FREQ_RE = re.compile(r"frequency:\s*([0-9]+)\s*MHz\s*\[in use\]")
_SURVEY_HEAD_RE = re.compile(r"^===SURVEY (\S+) (\S+) (\S+)===$")


def band_for_freq(freq_mhz):
    """'2g'/'5g'/'6g' aus der Mittenfrequenz (unabhaengig vom Interface-Typ)."""
    if not freq_mhz:
        return None
    if freq_mhz < 3000:
        return "2g"
    if freq_mhz < 5925:
        return "5g"
    return "6g"


def channel_for_freq(freq_mhz):
    if not freq_mhz:
        return None
    if freq_mhz == 2484:
        return 14
    if freq_mhz < 3000:
        return (freq_mhz - 2407) // 5
    if freq_mhz < 5925:
        return (freq_mhz - 5000) // 5
    return (freq_mhz - 5950) // 5


def _parse_one_survey_block(section_lines):
    # "survey dump" listet einen Block je bekanntem Kanal; uns interessiert nur
    # der aktuell genutzte ("[in use]" hinter der Frequenz).
    blocks = []
    current = []
    for line in section_lines:
        if line.strip().startswith("Survey data from"):
            if current:
                blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)
    for block in blocks:
        text = "\n".join(block)
        freq_match = _SURVEY_FREQ_RE.search(text)
        if not freq_match:
            continue
        out = {"freq_mhz": int(freq_match.group(1))}
        for key, rx in _SURVEY_FIELD_RE.items():
            m = rx.search(text)
            out[key] = int(m.group(1)) if m else None
        m = _SURVEY_NOISE_RE.search(text)
        out["noise_dbm"] = int(m.group(1)) if m else None
        return out
    return None


def parse_survey_output(lines):
    """Abschnitte "===SURVEY <phy> <ifname> <typ>===" (s. SURVEY_SHELL) ->
    {phy: sample oder None}. sample enthaelt zusaetzlich ifname, iftype,
    ssid (falls vorhanden), band und channel."""
    result = {}
    blocks = []
    current = None
    for line in lines:
        stripped = line.strip()
        m = _SURVEY_HEAD_RE.match(stripped)
        if m:
            current = {"phy": m.group(1), "ifname": m.group(2), "iftype": m.group(3), "ssid": None,
                       "driver": None, "lines": []}
            blocks.append(current)
            continue
        if stripped in ("===DONE===", "===STATIONS===") or stripped.startswith("===STA "):
            current = None
            continue
        if current is not None:
            if stripped.startswith("SSID=") and not current["lines"]:
                current["ssid"] = stripped[5:] or None
            elif stripped.startswith("DRIVER=") and not current["lines"]:
                current["driver"] = stripped[7:] or None
            else:
                current["lines"].append(line)
    for b in blocks:
        sample = _parse_one_survey_block(b["lines"])
        if sample is not None:
            sample.update({
                "ifname": b["ifname"], "iftype": b["iftype"], "ssid": b["ssid"],
                "driver": b["driver"],
                "band": band_for_freq(sample["freq_mhz"]),
                "channel": channel_for_freq(sample["freq_mhz"]),
            })
        result[b["phy"]] = sample
    return result


_STA_HEAD_RE = re.compile(r"^===STA (\S+) (\S+)===$")
_STA_MAC_RE = re.compile(r"^Station\s+([0-9a-fA-F:]{17})")
_STA_RX_DUR_RE = re.compile(r"rx duration:\s*([0-9]+)\s*us")
_STA_TX_DUR_RE = re.compile(r"tx duration:\s*([0-9]+)\s*us")
_STA_SIGNAL_RE = re.compile(r"^signal:\s*(-?[0-9]+)")


def parse_station_output(lines):
    """Abschnitte "===STA <phy> <ifname>===" (s. STATION_SHELL) ->
    {phy: {"<ifname>|<mac>": {"rx_us", "tx_us", "signal_dbm", "ifname"}}}.
    Fehlende Werte (Treiber ohne Airtime-Zaehler) bleiben None."""
    result = {}
    phy = ifname = None
    sta = None
    for line in lines:
        s = line.strip()
        m = _STA_HEAD_RE.match(s)
        if m:
            phy, ifname = m.group(1), m.group(2)
            result.setdefault(phy, {})
            sta = None
            continue
        if s.startswith("===") or phy is None:
            phy = None if s.startswith("===") else phy
            sta = None
            continue
        m = _STA_MAC_RE.match(s)
        if m:
            sta = {"rx_us": None, "tx_us": None, "signal_dbm": None, "ifname": ifname}
            result[phy]["%s|%s" % (ifname, m.group(1).lower())] = sta
            continue
        if sta is None:
            continue
        m = _STA_RX_DUR_RE.search(s)
        if m:
            sta["rx_us"] = int(m.group(1))
            continue
        m = _STA_TX_DUR_RE.search(s)
        if m:
            sta["tx_us"] = int(m.group(1))
            continue
        m = _STA_SIGNAL_RE.match(s)
        if m:
            sta["signal_dbm"] = int(m.group(1))
    return result


def get_section(lines, start_marker, end_marker):
    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if start_idx is None and line.strip() == start_marker:
            start_idx = i + 1
            continue
        if start_idx is not None and line.strip() == end_marker:
            end_idx = i
            break
    if start_idx is None:
        return []
    if end_idx is None:
        end_idx = len(lines)
    return lines[start_idx:end_idx]


def convert_router_output(lines):
    router_result = {}
    names = {}
    ips = {}

    wireless_lines = get_section(lines, "===WIRELESS===", "===HOSTAPD-%s===" % AP_IFNAMES[0])
    iface_info = {}
    wireless_text = "\n".join(wireless_lines).strip()
    if wireless_text:
        try:
            wireless = json.loads(wireless_text)
            for radio in wireless.values():
                band = (radio.get("config") or {}).get("band")
                for iface in radio.get("interfaces", []):
                    cfg = iface.get("config") or {}
                    if cfg.get("mode") == "ap" and cfg.get("ssid"):
                        iface_info[iface.get("ifname")] = {"ssid": cfg["ssid"], "band": band}
        except Exception:
            pass

    ssids_out = {}
    for i, ifname in enumerate(AP_IFNAMES):
        start_marker = "===HOSTAPD-%s===" % ifname
        end_marker = "===HOSTAPD-%s===" % AP_IFNAMES[i + 1] if i < len(AP_IFNAMES) - 1 else "===USTEER==="
        section_text = "\n".join(get_section(lines, start_marker, end_marker)).strip()
        if not section_text:
            continue
        try:
            parsed = json.loads(section_text)
        except Exception:
            continue
        clients = parsed.get("clients") if isinstance(parsed, dict) else None
        if not clients:
            continue
        info = iface_info.get(ifname)
        ssid_name = info["ssid"] if info else "Unbekannt (%s)" % ifname
        band = info["band"] if info else None
        bucket = ssids_out.setdefault(ssid_name, {"clients": {}})
        for mac_raw, c in clients.items():
            mac = mac_raw.lower()
            signal = None
            if isinstance(c, dict):
                for field in ("signal", "rssi", "signal_avg"):
                    if c.get(field) is not None:
                        signal = c[field]
                        break
            bucket["clients"][mac] = {"signal": signal, "band": band, "ifname": ifname}
    router_result["ssids"] = ssids_out

    usteer_text = "\n".join(get_section(lines, "===USTEER===", "===LEASES===")).strip()
    if usteer_text:
        try:
            router_result["usteer_raw"] = json.loads(usteer_text)
        except Exception:
            pass

    for line in get_section(lines, "===LEASES===", "===ARP==="):
        parts = line.strip().split()
        if len(parts) >= 4 and MAC_RE.match(parts[1]):
            mac = parts[1].lower()
            if parts[2]:
                ips[mac] = parts[2]
            if parts[3] and parts[3] != "*":
                names[mac] = parts[3]

    for line in get_section(lines, "===ARP===", "===SURVEYS==="):
        if line.strip().startswith("IP address"):
            continue
        parts = line.strip().split()
        if len(parts) >= 4 and MAC_RE.match(parts[3]) and parts[3] != "00:00:00:00:00:00":
            mac = parts[3].lower()
            ips.setdefault(mac, parts[0])

    # Kanalauslastung je phy; das Band ergibt sich aus der Frequenz (s.
    # parse_survey_output) - funktioniert damit auch fuer Client-Interfaces,
    # die in iface_info (nur AP-Interfaces) gar nicht vorkommen.
    survey = {phy: s for phy, s in parse_survey_output(lines).items() if s is not None}
    for phy, stations in parse_station_output(lines).items():
        if phy in survey:
            survey[phy]["stations"] = stations

    return router_result, names, ips, survey


# ---- WLAN-Scan: Auslastung der Nachbarkanaele (#13) ----------------------
#
# Zyklisch je Router: "iw dev <if> scan dump" (zuletzt gefundene Netze) auf
# einem Interface je Funkkarte (bevorzugt Client, sonst AP), vorher je nach
# Einstellung "scan trigger" fuer den naechsten Durchlauf (asynchron - die
# Ergebnisse kommen beim naechsten Dump an):
#   off     - nie aktiv scannen, nur vorhandene Ergebnisse auswerten
#   clients - nur auf Client-Interfaces (Messpunkte); dort scannt
#             wpa_supplicant ohnehin, die Verbindung bleibt praktisch ungestoert
#   all     - zusaetzlich auf AP-Interfaces ("ap-force"); die Funkkarte
#             verlaesst dafuer kurz ihren Kanal (kurze Pause fuer die Clients)
# Ausserdem meldet jeder Router die BSSID/SSID seiner eigenen AP-Interfaces
# ("OWNAP"), damit eigene und fremde Netze automatisch unterschieden werden.
# Ausgegeben werden nur die fuer die Auswertung noetigen Zeilen.
SCAN_GREP = ("^BSS |freq:|signal:|last seen:|SSID:|DS Parameter set|operation:|"
             "primary channel|secondary channel offset|channel width|"
             "center freq segment|station count|channel utili")


def build_scan_cmd(trigger="clients"):
    pick = (
        "iw dev 2>/dev/null | awk '"
        "/^phy#/{p=\"phy\" substr($1,5)} "
        "$1==\"Interface\"{i=$2} "
        "$1==\"type\"{t=$2; "
        "if(t==\"managed\" && !(p in man)){man[p]=1; best[p]=i\" \"t} "
        "else if(t==\"AP\" && !(p in best)){best[p]=i\" \"t}} "
        "END{for(p in best) print p, best[p]}'"
    )
    trig = {
        "off": ":",
        "clients": "[ \"$t\" = managed ] && iw dev \"$i\" scan trigger >/dev/null 2>&1",
        "all": "if [ \"$t\" = managed ]; then iw dev \"$i\" scan trigger >/dev/null 2>&1; "
               "else iw dev \"$i\" scan trigger ap-force >/dev/null 2>&1; fi",
    }.get(trigger, ":")
    own = (
        "iw dev 2>/dev/null | awk '"
        "$1==\"addr\"{a=$2} "
        "$1==\"ssid\"{s=substr($0, index($0, \"ssid \")+5)} "
        "$1==\"Interface\"{a=\"\"; s=\"\"} "
        "$1==\"type\" && $2==\"AP\"{print \"OWNAP \" a \" \" s}'"
    )
    return "; ".join([
        "echo ===SCAN-OWN===",
        own,
        pick + " | while read p i t; do " + trig + "; "
        "echo \"===SCAN $p $i $t===\"; "
        "iw dev \"$i\" scan dump 2>/dev/null | grep -E '" + SCAN_GREP + "'; done",
        "echo ===DONE===",
    ])


_SCAN_BSS_RE = re.compile(r"^BSS ([0-9a-fA-F:]{17})")
_SCAN_FREQ_RE = re.compile(r"^freq:\s*([0-9]+)")
_SCAN_SIGNAL_RE = re.compile(r"^signal:\s*(-?[0-9]+)")
_SCAN_SEEN_RE = re.compile(r"^last seen:\s*([0-9]+)\s*ms")
_SCAN_DS_RE = re.compile(r"DS Parameter set: channel ([0-9]+)")
_SCAN_OFFSET_RE = re.compile(r"secondary channel offset:\s*(\S+)")
_SCAN_WIDTH_RE = re.compile(r"\* channel width:\s*([0-9]+)")
_SCAN_SEG1_RE = re.compile(r"center freq segment 1:\s*([0-9]+)")
_SCAN_SEG2_RE = re.compile(r"center freq segment 2:\s*([0-9]+)")
_SCAN_STACOUNT_RE = re.compile(r"station count:\s*([0-9]+)")
_SCAN_UTIL_RE = re.compile(r"channel utili[sz]ation:\s*([0-9]+)/255")


def parse_scan_output(lines):
    """-> (liste der Netze, {bssid: ssid} der eigenen AP-Interfaces).
    Netz: {bssid, freq, signal, ssid, last_seen_ms, offset, vht_width,
    seg1, seg2, sta_count, util_pct}."""
    nets = []
    own = {}
    cur = None
    block = None   # aktueller Operation-Block ("HT", "VHT", "HE", ...)
    for raw in lines:
        s = raw.strip()
        if s.startswith("OWNAP "):
            parts = s.split(" ", 2)
            if len(parts) >= 2 and len(parts[1]) == 17:
                own[parts[1].lower()] = parts[2] if len(parts) > 2 else ""
            continue
        if s.startswith("==="):
            cur = None
            continue
        m = _SCAN_BSS_RE.match(s)
        if m:
            cur = {"bssid": m.group(1).lower(), "freq": None, "signal": None, "ssid": "",
                   "last_seen_ms": 0, "offset": None, "vht_width": None, "seg1": 0, "seg2": 0,
                   "sta_count": None, "util_pct": None}
            nets.append(cur)
            block = None
            continue
        if cur is None:
            continue
        if s.endswith("operation:"):
            block = s.split()[0]
            continue
        m = _SCAN_FREQ_RE.match(s)
        if m:
            cur["freq"] = int(m.group(1))
            continue
        m = _SCAN_SIGNAL_RE.match(s)
        if m:
            cur["signal"] = int(m.group(1))
            continue
        m = _SCAN_SEEN_RE.match(s)
        if m:
            cur["last_seen_ms"] = int(m.group(1))
            continue
        if s.startswith("SSID:"):
            cur["ssid"] = s[5:].strip()
            continue
        m = _SCAN_OFFSET_RE.search(s)
        if m:
            cur["offset"] = m.group(1)
            continue
        if block == "VHT":
            m = _SCAN_WIDTH_RE.search(s)
            if m:
                cur["vht_width"] = int(m.group(1))
                continue
            m = _SCAN_SEG1_RE.search(s)
            if m:
                cur["seg1"] = int(m.group(1))
                continue
            m = _SCAN_SEG2_RE.search(s)
            if m:
                cur["seg2"] = int(m.group(1))
                continue
        m = _SCAN_STACOUNT_RE.search(s)
        if m:
            cur["sta_count"] = int(m.group(1))
            continue
        m = _SCAN_UTIL_RE.search(s)
        if m:
            cur["util_pct"] = round(int(m.group(1)) / 255 * 100, 1)
    return [n for n in nets if n["freq"] and n["signal"] is not None], own


def net_span(n):
    """Vom Netz belegter Frequenzbereich (lo, hi) in MHz."""
    f = n["freq"]
    lo, hi = f - 10, f + 10
    if n.get("offset") == "above":
        hi = f + 30
    elif n.get("offset") == "below":
        lo = f - 30
    w, s1, s2 = n.get("vht_width"), n.get("seg1") or 0, n.get("seg2") or 0
    if 5000 < f < 5925 and w and s1:
        c1 = 5000 + 5 * s1
        if w == 1 and s2 and abs(s2 - s1) == 8:
            c2 = 5000 + 5 * s2       # 160 MHz (neue Signalisierung)
            lo, hi = c2 - 80, c2 + 80
        elif w == 2:
            lo, hi = c1 - 80, c1 + 80  # 160 MHz (alte Signalisierung)
        else:
            lo, hi = c1 - 40, c1 + 40  # 80 MHz (bzw. 80+80: erster Block)
    return lo, hi


SCAN_CHANNELS = {
    "2g": [(ch, 2407 + 5 * ch) for ch in range(1, 14)],
    "5g": [(ch, 5000 + 5 * ch) for ch in
           list(range(36, 65, 4)) + list(range(100, 145, 4)) + list(range(149, 166, 4))],
}


def scan_signal_weight(rssi):
    return min(1.0, max(0.05, (rssi + 95) / 45.0))


def analyze_scan(nets, is_own):
    """Belegung je 20-MHz-Kanal und Band, aufgeteilt eigen/fremd -
    gleiche Logik wie tools/WlanAnalyzer (Analysis/ChannelAnalysis.cs)."""
    out = {}
    for band, channels in SCAN_CHANNELS.items():
        band_nets = [n for n in nets if band_for_freq(n["freq"]) == band]
        rows = []
        for ch, f in channels:
            overlapping = []
            for n in band_nets:
                lo, hi = net_span(n)
                if lo < f + 10 and hi > f - 10:
                    overlapping.append((n, lo, hi))
            own_w = foreign_w = 0.0
            own_sta = foreign_sta = own_cnt = foreign_cnt = 0
            measured = None
            for n, lo, hi in overlapping:
                own = is_own(n)
                w = scan_signal_weight(n["signal"])
                if own:
                    own_w += w
                    own_cnt += 1
                    own_sta += n.get("sta_count") or 0
                else:
                    foreign_w += w
                    foreign_cnt += 1
                    foreign_sta += n.get("sta_count") or 0
                if n.get("util_pct") is not None and lo <= f <= hi:
                    measured = max(measured or 0.0, n["util_pct"])
            estimated = min(100.0, (own_w + foreign_w) * 20.0)
            # Geraeteanzahl nur, wenn ALLE beteiligten Netze sie melden - sonst
            # zaehlte ein fremdes Netz ohne BSS Load wie "0 Geraete" (anders
            # als WlanAnalyzer, dort fuehrt das zu "fremd 0 %")
            all_counts = all(n.get("sta_count") is not None for n, _, _ in overlapping)
            if measured is not None and all_counts and own_sta + foreign_sta > 0:
                share = own_sta / (own_sta + foreign_sta)
            elif own_w + foreign_w > 0:
                share = own_w / (own_w + foreign_w)
            else:
                share = 0.0
            total = measured if measured is not None else estimated
            top = sorted(overlapping, key=lambda x: -x[0]["signal"])[:6]
            rows.append({
                "channel": ch, "freq_mhz": f,
                "dfs": band == "5g" and 52 <= ch <= 144,
                "measured_pct": measured, "estimated_pct": round(estimated, 1),
                "total_pct": round(total, 1),
                "own_pct": round(total * share, 1), "foreign_pct": round(total * (1 - share), 1),
                "own_count": own_cnt, "foreign_count": foreign_cnt,
                "networks": [{"ssid": n["ssid"], "signal": n["signal"], "own": is_own(n),
                              "primary": channel_for_freq(n["freq"])} for n, _, _ in top],
            })
        out[band] = {
            "channels": rows,
            "recommendation": scan_recommendation(band, rows),
            "network_count": len(band_nets),
        }
    return out


def scan_recommendation(band, rows):
    """Kanal mit der geringsten Belegung durch FREMDE Netze: 2,4 GHz einer
    von 1/6/11, 5 GHz ein 80-MHz-Block (bei Gleichstand ohne DFS)."""
    by_ch = {r["channel"]: r for r in rows}
    if band == "2g":
        best = min((1, 6, 11), key=lambda c: (by_ch[c]["foreign_pct"], c))
        return {"text": "Kanal %d" % best, "channels": [best]}
    blocks = [[s + 4 * i for i in range(4)] for s in (36, 52, 100, 116, 132, 149)]
    blocks = [b for b in blocks if all(c in by_ch for c in b)]
    if not blocks:
        return {"text": "–", "channels": []}
    best = min(blocks, key=lambda b: (round(sum(by_ch[c]["foreign_pct"] for c in b) / 4, 1),
                                      by_ch[b[0]]["dfs"], b[0]))
    return {"text": "Kanal %d–%d (80 MHz%s)" % (best[0], best[-1], ", DFS" if by_ch[best[0]]["dfs"] else ""),
            "channels": best}


# ---- Persistenz (SQLite als einfacher JSON-Key/Value-Speicher) -----------

class Store:
    def __init__(self, path):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        # Geloeschte personenbezogene Daten auch physisch ueberschreiben statt
        # sie nur als freie Seiten in der Datei liegen zu lassen.
        self.conn.execute("PRAGMA secure_delete=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.conn.commit()
        # Die Datenbank enthaelt personenbezogene Daten - nur fuer den Dienst
        # lesbar, auch wenn sie von einer aelteren Version mit 0644 stammt.
        for suffix in ("", "-wal", "-shm"):
            try:
                os.chmod(path + suffix, 0o600)
            except OSError:
                pass
        self.lock = threading.Lock()

    def get_json(self, key, default):
        with self.lock:
            row = self.conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row[0])
        except Exception:
            return default

    def set_json(self, key, value):
        payload = json.dumps(value, ensure_ascii=False)
        with self.lock:
            self.conn.execute(
                "INSERT INTO kv(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, payload),
            )
            self.conn.commit()


# ---- Zentraler Zustand + Roam-/Connect-/Disconnect-Erkennung -------------

class MeshState:
    def __init__(self, store):
        self.lock = threading.RLock()
        self.store = store
        self.routers = {rid: {"error": "Noch keine Antwort erhalten"} for rid in ROUTERS}
        self.generated_at = {}
        self.names = store.get_json("device_names", {})
        self.ips = store.get_json("device_ips", {})
        self.nicknames = store.get_json("nicknames", {})
        self.last_seen = store.get_json("last_seen", {})  # mac -> {"rid":..., "ssid":...} (aeltere Daten: mac -> routerId als reiner String)
        self.log = store.get_json("log", [])
        # mac -> Zeitpunkt (ms) der letzten Beobachtung dieses Geraets, egal
        # ob als WLAN-Client (new_assignment) oder nur per DHCP-Lease/ARP
        # (names/ips) - Grundlage fuer die Speicherbegrenzung in
        # _prune_expired(). Bewusst getrennt von "last_seen" oben: das wird
        # jeden Zyklus komplett neu aufgebaut (nur aktuell verbundene WLAN-
        # Clients), dieses hier bleibt bestehen, bis die Aufbewahrungsfrist
        # abgelaufen ist.
        self.device_last_seen_ts = store.get_json("device_last_seen_ts", {})
        # Stuendliche, anonyme Zusammenfassung ohne MAC-Adresse (siehe
        # DEFAULT_CONFIG["privacy"] oben) - kein personenbezogenes Datum,
        # daher keine Ablaufgrenze in _prune_expired().
        # Struktur: {"<YYYY-MM-DDTHH>": {"<router_id>": {
        #   "connect": n, "roam": n, "disconnect": n,
        #   "signal_sum": f, "signal_n": n,
        #   "by_band": {"<band>": {"signal_sum": f, "signal_n": n}},
        # }}}
        self.stats = store.get_json("stats_hourly", {})
        self._stats_dirty = False
        self._last_prune_ms = 0
        # Kanalauslastung - rein im RAM, bewusst NICHT persistiert: es
        # sind kurzlebige gleitende Differenzen (s. UTIL_WINDOW_SEC), nach
        # einem Neustart des Dienstes baut sich die Historie binnen eines
        # Intervalls von selbst wieder auf.
        self.util_history = {}  # rid -> ifname -> deque[(ts, sample-dict)]
        self.util_latest = {}   # rid -> ifname -> berechnetes Ergebnis oder None
        # WLAN-Scan (#13): bssid -> (zeitpunkt zuletzt gesehen, netz, rid);
        # nur im Arbeitsspeicher, Eintraege verfallen nach SCAN_MAX_AGE_SEC
        self.scan_bss = {}
        self.scan_own_aps = {}   # rid -> {bssid: ssid} der eigenen AP-Interfaces
        self.scan_at = {}        # rid -> zeitpunkt des letzten Scans
        self._scan_cache_key = None
        self._scan_cache = None

    @staticmethod
    def _flat_clients(router_result):
        flat = {}
        if not router_result or "error" in router_result or "ssids" not in router_result:
            return flat
        for ssid_name, bucket in router_result.get("ssids", {}).items():
            for mac, c in (bucket.get("clients") or {}).items():
                if MAC_RE.match(mac):
                    flat[mac] = {"mac": mac, "signal": c.get("signal"), "band": c.get("band"), "ssid": ssid_name}
        return flat

    def set_router_error(self, rid, message):
        with self.lock:
            self.routers[rid] = {"error": message}
            self._recompute_and_log()

    def update_router(self, rid, router_result, names, ips):
        with self.lock:
            self.routers[rid] = router_result
            self.generated_at[rid] = time.time()

            # Jedes Geraet, das diesen Zyklus per DHCP-Lease/ARP auftaucht,
            # gilt als "gerade beobachtet" - unabhaengig davon, ob sich sein
            # Name/IP seit dem letzten Mal geaendert hat (ein unveraendertes
            # DHCP-Lease ist trotzdem ein Beleg, dass das Geraet noch da
            # ist). Das haelt device_last_seen_ts fuer die Speicherbegrenzung
            # aktuell, s. _prune_expired().
            now_ms = int(time.time() * 1000)
            for mac in set(names) | set(ips):
                self.device_last_seen_ts[mac] = now_ms

            changed_names = False
            for mac, name in names.items():
                if name and self.names.get(mac) != name:
                    self.names[mac] = name
                    changed_names = True
            changed_ips = False
            for mac, ip in ips.items():
                if ip and self.ips.get(mac) != ip:
                    self.ips[mac] = ip
                    changed_ips = True
            if changed_names:
                self.store.set_json("device_names", self.names)
            if changed_ips:
                self.store.set_json("device_ips", self.ips)

            self._recompute_and_log()

    @staticmethod
    def _prev_rid(prev):
        # last_seen-Eintrag: neues Format {"rid":..., "ssid":...}, alte Daten
        # (vor v15) waren ein reiner routerId-String - beides akzeptieren.
        if isinstance(prev, dict):
            return prev.get("rid")
        return prev

    @staticmethod
    def _prev_ssid(prev):
        return prev.get("ssid") if isinstance(prev, dict) else None

    def _recompute_and_log(self):
        # Muss unter self.lock aufgerufen werden.
        # mac -> {"rid":..., "ssid":..., "signal":...} - die SSID wird mit
        # abgelegt, damit das Ereignis-Log auch spaeter noch weiss, an welcher
        # SSID ein Ereignis stattfand (fuer die Farbmarkierung im Log),
        # unabhaengig davon, ob der Client inzwischen die SSID gewechselt hat
        # oder ganz weg ist.
        new_assignment = {}
        for rid, rr in self.routers.items():
            for mac, info in self._flat_clients(rr).items():
                new_assignment[mac] = {
                    "rid": rid, "ssid": info.get("ssid"), "signal": info.get("signal"),
                    "band": info.get("band"),
                }

        ts = int(time.time() * 1000)
        changed = False
        for mac, info in new_assignment.items():
            self.device_last_seen_ts[mac] = ts
            to_rid = info["rid"]
            ssid = info["ssid"]
            sig = info["signal"]
            band = info["band"]
            prev = self.last_seen.get(mac)
            from_rid = self._prev_rid(prev)
            if from_rid is None:
                self.log.append({"time": ts, "kind": "connect", "mac": mac, "from": None, "to": to_rid, "signal": sig, "ssid": ssid})
                self._bump_stat(ts, to_rid, "connect", sig, band)
                changed = True
            elif from_rid != to_rid:
                self.log.append({"time": ts, "kind": "roam", "mac": mac, "from": from_rid, "to": to_rid, "signal": sig, "ssid": ssid})
                self._bump_stat(ts, to_rid, "roam", sig, band)
                changed = True
        for mac, prev in list(self.last_seen.items()):
            if mac not in new_assignment:
                from_rid = self._prev_rid(prev)
                self.log.append({
                    "time": ts, "kind": "disconnect", "mac": mac,
                    "from": from_rid, "to": None, "signal": None,
                    "ssid": self._prev_ssid(prev),
                })
                self._bump_stat(ts, from_rid, "disconnect")
                changed = True

        self.last_seen = new_assignment
        self.store.set_json("last_seen", self.last_seen)
        if changed:
            if len(self.log) > LOG_MAX:
                self.log = self.log[-LOG_MAX:]
            self.store.set_json("log", self.log)
        if new_assignment:
            self.store.set_json("device_last_seen_ts", self.device_last_seen_ts)
        if self._stats_dirty:
            self.store.set_json("stats_hourly", self.stats)
            self._stats_dirty = False

        self._prune_expired(ts)

    def _bump_stat(self, ts_ms, rid, kind, signal=None, band=None):
        # Muss unter self.lock aufgerufen werden. Anonyme, geraeteunabhaengige
        # Zusammenfassung (kein MAC-Feld!) - s. DEFAULT_CONFIG["privacy"] und
        # self.stats oben.
        if not STATS_ENABLED or not rid:
            return
        bucket = self.stats.setdefault(_hour_bucket(ts_ms), {})
        r = bucket.setdefault(rid, {
            "connect": 0, "roam": 0, "disconnect": 0,
            "signal_sum": 0.0, "signal_n": 0, "by_band": {},
        })
        r[kind] = r.get(kind, 0) + 1
        if signal is not None:
            r["signal_sum"] += signal
            r["signal_n"] += 1
            if band:
                bb = r["by_band"].setdefault(band, {"signal_sum": 0.0, "signal_n": 0})
                bb["signal_sum"] += signal
                bb["signal_n"] += 1
        self._stats_dirty = True

    def _prune_expired(self, now_ms):
        # Muss unter self.lock aufgerufen werden. Loescht geraetebezogene
        # personenbezogene Daten (Roaming-Log, Name, IP, Nickname), deren
        # Geraet seit "privacy.retention_days" nicht mehr beobachtet wurde -
        # echte Speicherbegrenzung (Art. 5 Abs. 1 lit. e DSGVO), nicht nur
        # eine Anzeige-/Anzahlgrenze wie LOG_MAX. self.stats ist davon
        # bewusst ausgenommen: keine MAC-Adresse enthalten, also kein
        # personenbezogenes Datum, s. DEFAULT_CONFIG["privacy"].
        if RETENTION_MS <= 0:
            return  # 0/negativ = Aufbewahrungsfrist bewusst deaktiviert
        if now_ms - self._last_prune_ms < _PRUNE_INTERVAL_MS:
            return
        self._last_prune_ms = now_ms
        cutoff = now_ms - RETENTION_MS

        before = len(self.log)
        self.log = [e for e in self.log if e.get("time", 0) >= cutoff]
        if len(self.log) != before:
            self.store.set_json("log", self.log)

        stale_macs = [mac for mac, seen in self.device_last_seen_ts.items() if seen < cutoff]
        if stale_macs:
            for mac in stale_macs:
                self.device_last_seen_ts.pop(mac, None)
                self.names.pop(mac, None)
                self.ips.pop(mac, None)
                self.nicknames.pop(mac, None)
            self.store.set_json("device_last_seen_ts", self.device_last_seen_ts)
            self.store.set_json("device_names", self.names)
            self.store.set_json("device_ips", self.ips)
            self.store.set_json("nicknames", self.nicknames)

    def erase_device(self, mac):
        # Sofort-Loeschung auf Zuruf fuer eine einzelne MAC-Adresse (Art. 17
        # DSGVO, Recht auf Loeschung) - unabhaengig von der automatischen
        # Frist in _prune_expired(). Ueber POST /api/erase ansprechbar.
        with self.lock:
            before = len(self.log)
            self.log = [e for e in self.log if e.get("mac") != mac]
            removed_log = before - len(self.log)
            # Bewusst NICHT als "or"-Kette mit Kurzschlussauswertung - sonst
            # wuerden z. B. ips/nicknames/device_last_seen_ts gar nicht erst
            # geleert, sobald schon names.pop() etwas gefunden hat.
            had_name = self.names.pop(mac, None) is not None
            had_ip = self.ips.pop(mac, None) is not None
            had_nickname = self.nicknames.pop(mac, None) is not None
            had_seen = self.device_last_seen_ts.pop(mac, None) is not None
            had_data = had_name or had_ip or had_nickname or had_seen or removed_log > 0
            if had_data:
                self.store.set_json("log", self.log)
                self.store.set_json("device_names", self.names)
                self.store.set_json("device_ips", self.ips)
                self.store.set_json("nicknames", self.nicknames)
                self.store.set_json("device_last_seen_ts", self.device_last_seen_ts)
            return removed_log

    def update_survey(self, rid, survey):
        # survey: phy -> {"freq_mhz", "active_ms", "busy_ms", "receive_ms",
        # "transmit_ms", "bss_receive_ms", "noise_dbm", "band", "channel",
        # "ifname", "iftype", "ssid"} - kumulative Zaehler aus
        # "iw dev <ifname> survey dump" seit Interface-Up (s. parse_survey_output).
        with self.lock:
            now = time.time()
            router_hist = self.util_history.setdefault(rid, {})
            router_latest = self.util_latest.setdefault(rid, {})
            for phy, sample in (survey or {}).items():
                if sample is None:
                    continue
                dq = router_hist.setdefault(phy, deque())
                # Kanalwechsel (z. B. AP des Messpunkts wechselt den Kanal):
                # Zaehler beziehen sich dann auf einen anderen Kanal - alte
                # Samples verwerfen statt ueber zwei Kanaele zu mitteln.
                if dq and dq[-1][1].get("freq_mhz") != sample.get("freq_mhz"):
                    dq.clear()
                dq.append((now, sample))
                # Nur so viel Historie behalten wie fuer die naechste Differenz
                # gebraucht wird (etwas mehr als 2x Fensterbreite als Puffer
                # gegen unregelmaessige Poll-Abstaende).
                cutoff = now - (UTIL_WINDOW_SEC * 2 + 5)
                while len(dq) > 2 and dq[0][0] < cutoff:
                    dq.popleft()
                computed = self._compute_util(dq)
                if computed is not None:
                    for key in ("band", "channel", "ifname", "iftype", "ssid", "noise_dbm", "driver"):
                        computed[key] = sample.get(key)
                    # Client-Interface (Messpunkt): Signal des verbundenen AP
                    # und Signal-Rausch-Abstand (#12)
                    signal = self._client_signal(sample)
                    computed["signal_dbm"] = signal
                    noise = sample.get("noise_dbm")
                    computed["snr_db"] = (signal - noise) if signal is not None and noise is not None else None
                router_latest[phy] = computed

    @staticmethod
    def _compute_util(deque_samples):
        # Kernstueck der Kanalauslastung: NICHT der Anteil seit
        # Router-/Interface-Start, sondern die Differenz zwischen dem
        # juengsten Sample und dem aeltesten Sample, das mindestens
        # UTIL_WINDOW_SEC zurueckliegt - macht aus den kumulativen
        # Kernel-Zaehlern eine "letzte N Sekunden"-Rate.
        if len(deque_samples) < 2:
            return None
        newest_ts, newest = deque_samples[-1]
        reference = deque_samples[0]
        for ts, counters in deque_samples:
            if newest_ts - ts >= UTIL_WINDOW_SEC:
                reference = (ts, counters)
            else:
                break
        ref_ts, ref = reference
        elapsed_sec = newest_ts - ref_ts
        if elapsed_sec <= 0:
            return None

        def d(key):
            a = ref.get(key)
            b = newest.get(key)
            if a is None or b is None:
                return None
            delta = b - a
            # Negative Differenz = Zaehler-Ueberlauf/Interface-Neustart
            # zwischen den Samples - dann lieber "nicht verfuegbar" als ein
            # falscher Wert.
            return delta if delta >= 0 else None

        active_delta = d("active_ms")
        busy_delta = d("busy_ms")
        receive_delta = d("receive_ms")
        transmit_delta = d("transmit_ms")
        bss_receive_delta = d("bss_receive_ms")
        if active_delta is None or active_delta <= 0:
            return None

        def pct(ms):
            return round(ms / active_delta * 100, 1)

        # Eigener Verkehr ueber die Airtime-Zaehler der verbundenen Stationen
        # (#11) - unabhaengig davon, ob der Chip BSS-Empfangszeit liefert.
        sta = MeshState._station_airtime(ref, newest)

        base = {
            "freq_mhz": newest.get("freq_mhz"),
            "window_sec": round(elapsed_sec, 1),
            "active_ms": active_delta,
            "busy_pct": pct(min(busy_delta, active_delta)) if busy_delta is not None else None,
        }

        if bss_receive_delta is None and receive_delta is not None and transmit_delta is not None:
            # Treiber ohne "channel BSS receive time" (z. B. ath9k: AR9340,
            # AR9580) - keine Aufteilung eigen/fremd moeglich. Stattdessen
            # ehrlich gemessene Anteile (User-Entscheidung, Issue #5):
            #   Senden    = transmit
            #   Empfang   = receive (eigenes Netz UND Nachbarn zusammen)
            #   Stoerung  = busy - receive - transmit (Kanal belegt, aber kein
            #               dekodierbarer WLAN-Frame: andere Funktechnik,
            #               zu schwache/kollidierte Frames)
            #   Frei      = active - busy
            rx_ms, tx_ms = receive_delta, transmit_delta
            if rx_ms + tx_ms > active_delta:
                scale = active_delta / (rx_ms + tx_ms)
                rx_ms *= scale
                tx_ms *= scale
            busy = min(busy_delta, active_delta) if busy_delta is not None else rx_ms + tx_ms
            busy = max(busy, rx_ms + tx_ms)
            other_ms = busy - rx_ms - tx_ms
            free_ms = active_delta - busy
            base.update({
                "mode": "rx_tx",
                "rx_ms": round(rx_ms), "tx_ms": round(tx_ms),
                "other_ms": round(other_ms), "free_ms": round(free_ms),
                "rx_pct": pct(rx_ms), "tx_pct": pct(tx_ms),
                "other_pct": pct(other_ms), "free_pct": pct(free_ms),
            })
            if sta is not None:
                # Empfang aufteilen: von den eigenen Stationen empfangen
                # (gemessen) vs. Rest = andere WLANs auf dem Kanal (#11)
                rx_own = min(sta["rx_ms"], rx_ms)
                base.update({
                    "rx_own_ms": round(rx_own), "rx_other_ms": round(rx_ms - rx_own),
                    "rx_own_pct": pct(rx_own), "rx_other_pct": pct(rx_ms - rx_own),
                })
            MeshState._add_station_fields(base, sta, active_delta)
            return base

        # "Eigene Nutzung" = eigene BSS-Empfangszeit + eigene Sendezeit (User-
        # Entscheidung): was der AP fuer/durch sein eigenes BSS gesendet UND
        # empfangen hat. "Fremde Nutzung" = alles, was das Radio
        # sonst noch dekodiert hat (receive_ms) abzueglich der eigenen
        # BSS-Empfangszeit - also Nachbarnetze/Fremdgeraete auf demselben Kanal.
        own_ms = None
        foreign_ms = None
        if bss_receive_delta is not None and transmit_delta is not None:
            own_ms = bss_receive_delta + transmit_delta
        if receive_delta is not None and bss_receive_delta is not None:
            foreign_ms = max(0, receive_delta - bss_receive_delta)

        if own_ms is None or foreign_ms is None:
            # Typischerweise: Treiber liefert kein "channel BSS receive time"
            # (s. Kommentar bei _SURVEY_FIELD_RE) - Segmente bleiben None,
            # Frontend zeigt "nicht verfuegbar" statt falscher Werte.
            return None

        # 100% moegliche Auslastung = tatsaechliche channel-active-time-
        # Differenz (User-Entscheidung) statt einer fest angenommenen
        # Intervalllaenge - robust gegen Poll-Jitter/verpasste Zyklen.
        if own_ms + foreign_ms > active_delta:
            scale = active_delta / (own_ms + foreign_ms)
            own_ms *= scale
            foreign_ms *= scale
        rest_ms = active_delta - (own_ms + foreign_ms)

        base.update({
            "mode": "own_foreign",
            "own_ms": round(own_ms),
            "foreign_ms": round(foreign_ms),
            "rest_ms": round(rest_ms),
            "own_pct": round(own_ms / active_delta * 100, 1),
            "foreign_pct": round(foreign_ms / active_delta * 100, 1),
            "rest_pct": round(rest_ms / active_delta * 100, 1),
        })
        MeshState._add_station_fields(base, sta, active_delta)
        return base

    @staticmethod
    def _client_signal(sample):
        """Signal (dBm) des AP, mit dem ein Client-Interface verbunden ist
        (aus "iw station dump" desselben Interfaces), sonst None."""
        if sample.get("iftype") != "managed":
            return None
        values = [s.get("signal_dbm") for s in (sample.get("stations") or {}).values()
                  if s.get("ifname") == sample.get("ifname") and s.get("signal_dbm") is not None]
        return max(values) if values else None

    @staticmethod
    def _station_airtime(ref, newest):
        """Summe der Sende-/Empfangszeit aller Stationen zwischen zwei
        Samples (#11). Nur Stationen, die in beiden Samples vorkommen
        (neu verbundene/getrennte fallen fuer dieses Fenster heraus).
        -> {"rx_ms", "tx_ms", "stations"} oder None, wenn der Treiber keine
        Airtime-Zaehler liefert."""
        a = ref.get("stations")
        b = newest.get("stations")
        if a is None or b is None:
            return None
        if not b:
            # Keine verbundenen Geraete - eigener Verkehr ist dann 0.
            return {"rx_ms": 0.0, "tx_ms": 0.0, "stations": 0}
        rx_us = tx_us = 0
        supported = False
        for key, nb in b.items():
            if nb.get("rx_us") is not None or nb.get("tx_us") is not None:
                supported = True
            na = a.get(key)
            if not na:
                continue
            for field in ("rx_us", "tx_us"):
                if nb.get(field) is None or na.get(field) is None:
                    continue
                delta = nb[field] - na[field]
                if delta < 0:
                    continue  # Zaehler zurueckgesetzt (Neuverbindung)
                if field == "rx_us":
                    rx_us += delta
                else:
                    tx_us += delta
        if not supported:
            return None
        return {"rx_ms": rx_us / 1000.0, "tx_ms": tx_us / 1000.0, "stations": len(b)}

    @staticmethod
    def _add_station_fields(base, sta, active_delta):
        """Eigener Verkehr (gemessen ueber die Stationen) zum Abgleich mit
        der Kanalauslastung (#11)."""
        if sta is None:
            base["sta_available"] = False
            return
        total = min(sta["rx_ms"] + sta["tx_ms"], active_delta)
        base.update({
            "sta_available": True,
            "sta_count": sta["stations"],
            "sta_rx_ms": round(sta["rx_ms"]),
            "sta_tx_ms": round(sta["tx_ms"]),
            "sta_pct": round(total / active_delta * 100, 1),
        })

    def rename(self, mac, name):
        mac = mac.lower()
        with self.lock:
            if name:
                self.nicknames[mac] = name
            else:
                self.nicknames.pop(mac, None)
            self.store.set_json("nicknames", self.nicknames)

    def snapshot(self):
        data = self._snapshot_core()
        data["scan"] = self.scan_snapshot()
        return data

    def _snapshot_core(self):
        with self.lock:
            router_status = {}
            for rid in ROUTERS:
                rr = self.routers.get(rid) or {}
                router_status[rid] = rr.get("error", "ok") if "error" in rr else "ok"
            # Datenminimierung: Hostnamen nur fuer Geraete, die die Karte
            # tatsaechlich anzeigt (aktuell im WLAN oder im Ereignis-Log) -
            # nicht fuer jedes Geraet aus den DHCP-Leases (auch kabelgebundene).
            # IP-Adressen braucht die Seite gar nicht, sie werden nur intern
            # (Speicherbegrenzung) gefuehrt.
            shown = set(self.last_seen) | {e.get("mac") for e in self.log} | set(self.nicknames)
            for rr in self.routers.values():
                for macs in ((rr or {}).get("usteer_raw") or {}).keys():
                    shown.add(str(macs).lower())
            return {
                "routers": self.routers,
                "names": {mac: n for mac, n in self.names.items() if mac in shown},
                "nicknames": self.nicknames,
                "log": self.log,
                "channelUtil": self.util_latest,
                "meta": {
                    "generatedAt": int(max(self.generated_at.values()) * 1000) if self.generated_at else 0,
                    "routerStatus": router_status,
                },
            }

    def status(self):
        """Nur der Erreichbarkeitsstatus je Router - ohne geraetebezogene
        Daten (fuer die Statusspalte in luci-app-mesh-roaming)."""
        with self.lock:
            router_status = {}
            for rid in ROUTERS:
                rr = self.routers.get(rid) or {}
                router_status[rid] = rr["error"] if "error" in rr else "ok"
            return {
                # Version des laufenden Dienstes - luci-app-mesh-roaming
                # vergleicht sie mit dem installierten Paket und weist auf
                # einen fehlenden Neustart nach einem Upgrade hin (#9).
                "version": __version__,
                "generatedAt": int(max(self.generated_at.values()) * 1000) if self.generated_at else 0,
                "routerStatus": router_status,
            }

    def client_counts_per_router(self):
        # Messpunkte ("sensor") haben keine Clients - keine Zahl melden.
        with self.lock:
            return {rid: len(self._flat_clients(self.routers.get(rid)))
                    for rid, r in ROUTERS.items() if r.get("role") != "sensor"}

    def update_scan(self, rid, nets, own_aps):
        with self.lock:
            now = time.time()
            self.scan_at[rid] = now
            self.scan_own_aps[rid] = own_aps
            for n in nets:
                seen = now - n.get("last_seen_ms", 0) / 1000.0
                old = self.scan_bss.get(n["bssid"])
                # je BSSID der juengste Eintrag; etwa gleich alt -> staerkeres Signal
                if (old is None or seen > old[0] + 5
                        or (abs(seen - old[0]) <= 5 and n["signal"] > old[1]["signal"])):
                    self.scan_bss[n["bssid"]] = (seen, n, rid)
            cutoff = now - SCAN_MAX_AGE_SEC
            for bssid in [b for b, v in self.scan_bss.items() if v[0] < cutoff]:
                del self.scan_bss[bssid]

    def scan_snapshot(self):
        """Auswertung des WLAN-Scans je Band (#13) fuer data.json/MQTT.
        Zwischengespeichert, bis ein neuer Scan eintrifft."""
        with self.lock:
            key = (tuple(sorted(self.scan_at.items())), len(self.scan_bss))
            if key == self._scan_cache_key:
                return self._scan_cache
            nets = [v[1] for v in self.scan_bss.values()]
            own_bssids = set()
            own_ssids = {s.lower() for s in SCAN_OWN_SSIDS}
            for aps in self.scan_own_aps.values():
                for bssid, ssid in aps.items():
                    own_bssids.add(bssid)
                    if ssid:
                        own_ssids.add(ssid.lower())
            sources = sorted(rid for rid in self.scan_at if rid in ROUTERS)
            last = max(self.scan_at.values()) if self.scan_at else None

        def is_own(n):
            return n["bssid"] in own_bssids or (n["ssid"] or "").lower() in own_ssids

        value = {
            "enabled": SCAN_INTERVAL_SEC > 0,
            "interval_sec": SCAN_INTERVAL_SEC,
            "updated_at": int(last * 1000) if last else None,
            "sources": [ROUTERS[rid].get("name", rid) for rid in sources],
            "bands": analyze_scan(nets, is_own) if nets else None,
        }
        with self.lock:
            self._scan_cache_key, self._scan_cache = key, value
        return value

    def util_snapshot(self):
        """Kopie der aktuellen Kanalauslastung: rid -> phy -> Werte oder None."""
        with self.lock:
            return {rid: dict(per_phy) for rid, per_phy in self.util_latest.items()}

    def log_len(self):
        with self.lock:
            return len(self.log)


# ---- Router-Poller (ein Thread je Router) --------------------------------

def router_worker(rid, ip, stop_event, local=False, role="ap"):
    # "local": der Dienst laeuft auf genau diesem Router - die
    # ubus-Abfrage wird direkt ueber die lokale Shell ausgefuehrt statt per
    # SSH auf sich selbst. Timeout/Fehlerbehandlung bleiben identisch zum
    # SSH-Fall, nur der eigentliche Verbindungsaufbau entfaellt.
    remote_cmd = REMOTE_CMDS[role]
    cmd = [ "/bin/sh", "-c", remote_cmd ] if local else None
    last_scan = 0.0
    while not stop_event.is_set():
        # WLAN-Scan der Nachbarkanaele (#13) - eigener, seltener Aufruf
        if SCAN_INTERVAL_SEC > 0 and time.monotonic() - last_scan >= SCAN_INTERVAL_SEC:
            last_scan = time.monotonic()
            try:
                proc = subprocess.run(
                    ["/bin/sh", "-c", SCAN_CMD] if local else build_ssh_cmd(ip, SCAN_CMD),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, timeout=SSH_COMMAND_TIMEOUT,
                )
                lines = proc.stdout.splitlines()
                if "===DONE===" in [l.strip() for l in lines]:
                    nets, own_aps = parse_scan_output(lines)
                    STATE.update_scan(rid, nets, own_aps)
            except Exception:
                pass  # Fehler zeigt schon die normale Abfrage (Erreichbarkeit)
        try:
            proc = subprocess.run(
                cmd if local else build_ssh_cmd(ip, remote_cmd),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, timeout=SSH_COMMAND_TIMEOUT,
            )
            lines = proc.stdout.splitlines()
            stripped = [l.strip() for l in lines]
            if "===DONE===" not in stripped:
                tail = lines[-3:] if lines else ["<leere Antwort>"]
                quelle = "lokaler Ausfuehrung" if local else "SSH-Antwort"
                raise RuntimeError("Unvollstaendige %s (kein ===DONE===): %s" % (quelle, " | ".join(tail)))
            result, names, ips, survey = convert_router_output(lines)
            STATE.update_router(rid, result, names, ips)
            STATE.update_survey(rid, survey)
        except subprocess.TimeoutExpired:
            STATE.set_router_error(rid, "Zeitueberschreitung bei " + ("lokaler Ausfuehrung" if local else "SSH-Verbindung"))
        except Exception as e:
            STATE.set_router_error(rid, str(e))
        stop_event.wait(POLL_INTERVAL_SEC)


# ---- Optionale MQTT-Zusammenfassung --------------------------------------

# Benutzername/Passwort gehen bewusst NICHT als Argument an mosquitto_pub
# (-u/-P), sonst waeren sie fuer jeden lokalen Nutzer in "ps" bzw.
# /proc/<pid>/cmdline sichtbar. Stattdessen landen sie in einer nur fuer den
# Dienst lesbaren Optionsdatei "$XDG_CONFIG_HOME/mosquitto_pub", die
# mosquitto_pub von selbst als Standardoptionen einliest (eine Option je
# Zeile, der Rest der Zeile ist der Wert - Leerzeichen im Passwort sind ok).
MQTT_OPTIONS_DIR = None   # wird in mqtt_prepare_options() gesetzt
_MQTT_ERROR_LOG_INTERVAL_SEC = 60.0


def mqtt_prepare_options():
    global MQTT_OPTIONS_DIR
    MQTT_OPTIONS_DIR = os.path.join(RUNTIME_DIR, "mqtt")
    options_path = os.path.join(MQTT_OPTIONS_DIR, "mosquitto_pub")
    if not MQTT_USERNAME:
        # Keine Anmeldung - eine evtl. alte Optionsdatei mit Zugangsdaten
        # darf nicht weiter benutzt werden.
        try:
            os.remove(options_path)
        except FileNotFoundError:
            pass
        return
    for value in (MQTT_USERNAME, MQTT_PASSWORD or ""):
        if "\n" in value or "\r" in value:
            raise SystemExit("MQTT-Benutzername/-Passwort darf keinen Zeilenumbruch enthalten.")
    os.makedirs(MQTT_OPTIONS_DIR, mode=0o700, exist_ok=True)
    os.chmod(MQTT_OPTIONS_DIR, 0o700)
    lines = ["-u %s" % MQTT_USERNAME]
    if MQTT_PASSWORD:
        lines.append("-P %s" % MQTT_PASSWORD)
    tmp_path = options_path + ".tmp"
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp_path, options_path)


def mqtt_base_cmd():
    cmd = ["mosquitto_pub", "-h", MQTT_BROKER]
    if MQTT_PORT:
        cmd += ["-p", str(MQTT_PORT)]
    if MQTT_TLS:
        if MQTT_TLS_CAFILE:
            cmd += ["--cafile", MQTT_TLS_CAFILE]
        else:
            cmd += ["--capath", MQTT_TLS_CAPATH]
        if MQTT_TLS_INSECURE:
            cmd.append("--insecure")
    return cmd


# Kanalauslastung je Router und Funkband als einzelne Zahlen-Topics (fuer
# openHAB-Items -> InfluxDB -> Grafana):
#   <base>/<router>/util/<band>/busy      Kanal belegt gesamt, %
#   .../own, .../foreign, .../free        Treiber mit BSS-Empfangszeit (mt76)
#   .../rx, .../tx, .../other, .../free   Treiber ohne (ath9k), s. _compute_util
#   .../noise                             Rauschen, dBm
#   .../signal, .../snr                   Client-Interface: Signal des AP (dBm)
#                                         und Signal-Rausch-Abstand (dB), #12
#   .../channel                           aktueller Kanal
#   .../mode                              own_foreign (Chip trennt eigen/fremd)
#                                         oder rx_tx (Chip kann das nicht), #10
#   .../driver                            WLAN-Treiber, z. B. ath9k, mt7915e
#   .../own_sta                           eigener Verkehr ueber die verbundenen
#                                         Stationen gemessen, % (#11)
#   .../rx_own, .../rx_other              ath9k: Empfang von eigenen Stationen
#                                         bzw. von anderen WLANs, % (#11)
# <band> ist 2g/5g/6g; haben zwei Funkkarten eines Routers dasselbe Band,
# wird stattdessen der phy-Name (phy0, phy1, ...) verwendet.
_UTIL_MQTT_FIELDS = {
    "own_foreign": (("own", "own_pct"), ("foreign", "foreign_pct"), ("free", "rest_pct")),
    "rx_tx": (("rx", "rx_pct"), ("tx", "tx_pct"), ("other", "other_pct"), ("free", "free_pct")),
}


def util_mqtt_values(util):
    out = []
    for rid in sorted(util):
        per_phy = util[rid] or {}
        bands = [(v or {}).get("band") for v in per_phy.values()]
        for phy in sorted(per_phy):
            v = per_phy[phy]
            if not v:
                continue
            band = v.get("band")
            key = band if band and bands.count(band) == 1 else phy
            prefix = "%s/util/%s" % (rid, key)
            fields = [("busy", "busy_pct"), ("noise", "noise_dbm"), ("signal", "signal_dbm"),
                      ("snr", "snr_db"), ("channel", "channel"),
                      ("mode", "mode"), ("driver", "driver"), ("own_sta", "sta_pct"),
                      ("rx_own", "rx_own_pct"), ("rx_other", "rx_other_pct")]
            fields += list(_UTIL_MQTT_FIELDS.get(v.get("mode"), ()))
            for name, field in fields:
                if v.get(field) is not None:
                    out.append(("%s/%s" % (prefix, name), str(v[field])))
    return out


# WLAN-Scan je Band (#13), bewusst nur zwei Topics je Band (jedes Topic
# kostet einen mosquitto_pub-Aufruf auf dem Router):
#   <base>/scan/<band>/recommendation   Empfehlung, z. B. "Kanal 6"
#   <base>/scan/<band>/channels         JSON {"1": 12.5, "2": 30.1, ...},
#                                       Gesamtbelegung je Kanal in %
def scan_mqtt_values(scan):
    out = []
    for band, data in sorted(((scan or {}).get("bands") or {}).items()):
        out.append(("scan/%s/recommendation" % band, data["recommendation"]["text"]))
        out.append(("scan/%s/channels" % band, json.dumps(
            {str(r["channel"]): r["total_pct"] for r in data["channels"]}, separators=(",", ":"))))
    return out


def mqtt_publisher(stop_event):
    if not MQTT_BROKER:
        return
    base_cmd = mqtt_base_cmd()
    env = dict(os.environ, XDG_CONFIG_HOME=MQTT_OPTIONS_DIR)
    last_error_log = 0.0

    def publish(topic, payload):
        proc = subprocess.run(
            base_cmd + ["-t", topic, "-m", payload],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, timeout=5, check=False, env=env,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or "").strip() or "Exit-Code %d" % proc.returncode)

    while not stop_event.is_set():
        try:
            counts = STATE.client_counts_per_router()
            for rid, n in counts.items():
                publish("%s/%s/clients" % (MQTT_BASE_TOPIC, rid), str(n))
            publish("%s/roam_events_total" % MQTT_BASE_TOPIC, str(STATE.log_len()))
            for topic, value in util_mqtt_values(STATE.util_snapshot()):
                publish("%s/%s" % (MQTT_BASE_TOPIC, topic), value)
            for topic, value in scan_mqtt_values(STATE.scan_snapshot()):
                publish("%s/%s" % (MQTT_BASE_TOPIC, topic), value)
        except Exception as e:
            # Fehler (falsches Passwort, Broker weg, Zertifikat ungueltig)
            # sichtbar machen, aber hoechstens einmal pro Minute ins Log.
            now = time.monotonic()
            if now - last_error_log >= _MQTT_ERROR_LOG_INTERVAL_SEC:
                last_error_log = now
                print("MQTT-Veroeffentlichung an %s fehlgeschlagen: %s" % (MQTT_BROKER, e),
                      file=sys.stderr, flush=True)
        stop_event.wait(MQTT_PUBLISH_INTERVAL_SEC)


# ---- Oeffentliche (netzwerkspezifische) Konfiguration fuer die HTML-Seite -

def public_config():
    return {
        "version": __version__,
        "network": CONFIG.get("network", {}),
        "routers": [
            {
                "id": r["id"], "ip": r["ip"], "name": r["name"], "room": r["room"],
                "map_x": r["map_x"], "map_y": r["map_y"], "mgmt_ips": r.get("mgmt_ips") or [],
                "role": r.get("role", "ap"),
            }
            for r in CONFIG["routers"]
        ],
        "roaming": CONFIG["roaming"],
        "signal": CONFIG["signal"],
        "map": CONFIG["map"],
        "channel_util": CONFIG["channel_util"],
        # Fuer Transparenz gegenueber betroffenen Personen (Art. 13 DSGVO) -
        # die Oberflaeche kann das anzeigen, falls gewuenscht.
        "privacy": CONFIG["privacy"],
    }


# ---- HTTP-Server ----------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "MeshRoamingPi/" + __version__

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            try:
                with open(HTML_PATH, "rb") as f:
                    body = f.read()
            except FileNotFoundError:
                self.send_error(404, "mesh-lageplan-live.html nicht gefunden (html_path in der Konfiguration pruefen)")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/config.json":
            self._send_json(public_config())
        elif path == "/data.json":
            self._send_json(STATE.snapshot())
        elif path == "/api/status":
            self._send_json(STATE.status())
        else:
            self.send_error(404)

    def _post_allowed(self):
        # Schutz gegen CSRF: Ohne diese Pruefung koennte jede beliebige
        # Webseite, die jemand im Heimnetz aufruft, per Formular/fetch
        # Geraete umbenennen oder Daten loeschen. "application/json" erzwingt
        # im Browser einen CORS-Preflight (den dieser Server nie erlaubt), ein
        # mitgeschicktes Origin muss zum eigenen Host passen.
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            return False
        origin = self.headers.get("Origin")
        if origin and origin != "null":
            host = self.headers.get("Host") or ""
            if urllib.parse.urlparse(origin).netloc.lower() != host.lower():
                return False
        elif origin == "null":
            return False
        return True

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/api/rename", "/api/erase") and not self._post_allowed():
            self._send_json({"ok": False, "error": "Anfrage abgelehnt (Content-Type/Origin)"}, status=403)
            return
        if path == "/api/rename":
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
                mac = str(payload.get("mac", "")).lower().strip()
                name = str(payload.get("name", "")).strip()
                if not MAC_RE.match(mac):
                    raise ValueError("ungueltige MAC-Adresse")
                STATE.rename(mac, name)
                self._send_json({"ok": True})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=400)
        elif path == "/api/erase":
            # Recht auf Loeschung (Art. 17 DSGVO) auf Zuruf fuer eine
            # einzelne MAC-Adresse - loescht Name/IP/Nickname/Roaming-Log-
            # Eintraege fuer dieses Geraet sofort, unabhaengig von der
            # automatischen Frist in privacy.retention_days.
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
                mac = str(payload.get("mac", "")).lower().strip()
                if not MAC_RE.match(mac):
                    raise ValueError("ungueltige MAC-Adresse")
                removed = STATE.erase_device(mac)
                self._send_json({"ok": True, "removed_log_entries": removed})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=400)
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):
        pass  # ruhig halten - bei Bedarf hier wieder auf journald loggen


# Fehler, die einen weggegangenen Client bedeuten (WLAN-Roaming/-Abriss waehrend
# des Schreibens der Antwort, Tab/App geschlossen, Handy im Standby) - kein
# Fehler des Dienstes selbst, deshalb ohne Traceback im Log. Alles andere geht
# weiterhin ganz normal (mit Traceback) ins journal, damit echte Bugs sichtbar
# bleiben.
_QUIET_CLIENT_ERRNOS = {
    errno.EPIPE,         # Broken pipe
    errno.ECONNRESET,    # Connection reset by peer
    errno.ETIMEDOUT,     # Connection timed out
    errno.EHOSTUNREACH,  # No route to host
    errno.ENETUNREACH,   # Network is unreachable
    errno.ECONNABORTED,  # Software caused connection abort
}


class MeshRoamingServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, OSError) and exc.errno in _QUIET_CLIENT_ERRNOS:
            return
        super().handle_error(request, client_address)


def main():
    global CONFIG, STATE, ROUTERS, AP_IFNAMES, UTIL_WINDOW_SEC, REMOTE_CMDS
    global SCAN_INTERVAL_SEC, SCAN_CMD, SCAN_OWN_SSIDS, SCAN_MAX_AGE_SEC
    global SSH_USER, SSH_KEY, SSH_CONNECT_TIMEOUT, SSH_COMMAND_TIMEOUT
    global USE_CONTROL_MASTER, CONTROL_PERSIST, POLL_INTERVAL_SEC
    global HTTP_BIND, HTTP_PORT, DB_PATH, RUNTIME_DIR, HTML_PATH, LOG_MAX
    global MQTT_BROKER, MQTT_PORT, MQTT_BASE_TOPIC, MQTT_PUBLISH_INTERVAL_SEC
    global MQTT_USERNAME, MQTT_PASSWORD
    global MQTT_TLS, MQTT_TLS_CAFILE, MQTT_TLS_CAPATH, MQTT_TLS_INSECURE
    global RETENTION_MS, STATS_ENABLED

    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print("mesh_roaming_pi.py (mesh-roaming-dashboard) %s" % __version__)
        return

    # Alle vom Dienst angelegten Dateien (SQLite-DB, known_hosts,
    # MQTT-Optionsdatei) nur fuer den Dienst selbst lesbar.
    os.umask(0o077)
    CONFIG = load_config(CONFIG_PATH)

    ROUTERS = {r["id"]: r for r in CONFIG["routers"]}
    AP_IFNAMES = CONFIG["ap_ifnames"]
    UTIL_WINDOW_SEC = float(CONFIG["channel_util"]["interval_sec"])
    REMOTE_CMDS = {role: build_remote_cmd(role) for role in ROLES}
    scan_cfg = CONFIG["scan"]
    SCAN_INTERVAL_SEC = float(scan_cfg.get("interval_sec") or 0)
    trigger = scan_cfg.get("trigger") or "clients"
    if trigger not in ("off", "clients", "all"):
        raise SystemExit("Konfiguration %s: scan.trigger %r unbekannt (erlaubt: off, clients, all)"
                         % (CONFIG_PATH, trigger))
    SCAN_CMD = build_scan_cmd(trigger)
    SCAN_OWN_SSIDS = set(scan_cfg.get("own_ssids") or [])
    SCAN_MAX_AGE_SEC = float(scan_cfg.get("max_age_sec") or 300)

    SSH_USER = CONFIG["ssh"]["user"]
    SSH_KEY = CONFIG["ssh"]["key_path"]
    SSH_CONNECT_TIMEOUT = CONFIG["ssh"]["connect_timeout_sec"]
    SSH_COMMAND_TIMEOUT = CONFIG["ssh"]["command_timeout_sec"]
    USE_CONTROL_MASTER = bool(CONFIG["ssh"]["control_master"])
    CONTROL_PERSIST = CONFIG["ssh"]["control_persist"]

    POLL_INTERVAL_SEC = float(CONFIG["polling"]["interval_sec"])
    HTTP_BIND = CONFIG["http"]["bind"]
    HTTP_PORT = int(CONFIG["http"]["port"])
    DB_PATH = CONFIG["storage"]["db_path"]
    RUNTIME_DIR = CONFIG["storage"]["runtime_dir"]
    HTML_PATH = CONFIG["html_path"]
    LOG_MAX = int(CONFIG["roaming"]["log_max_entries"])

    # Speicherbegrenzung (DSGVO, Art. 5 Abs. 1 lit. e) - s. DEFAULT_CONFIG
    # ["privacy"] und MeshState._prune_expired() fuer Details.
    RETENTION_MS = int(CONFIG["privacy"]["retention_days"]) * 86400_000
    STATS_ENABLED = bool(CONFIG["privacy"]["anonymous_stats_enabled"])

    mqtt = CONFIG["mqtt"]
    MQTT_BROKER = mqtt.get("broker") or None
    MQTT_PORT = int(mqtt["port"]) if mqtt.get("port") else None
    MQTT_BASE_TOPIC = mqtt["base_topic"]
    MQTT_PUBLISH_INTERVAL_SEC = float(mqtt["publish_interval_sec"])
    MQTT_USERNAME = mqtt.get("username") or None
    MQTT_PASSWORD = mqtt.get("password") or None
    MQTT_TLS = bool(mqtt.get("tls"))
    MQTT_TLS_CAFILE = mqtt.get("tls_cafile") or None
    MQTT_TLS_CAPATH = mqtt.get("tls_capath") or "/etc/ssl/certs"
    MQTT_TLS_INSECURE = bool(mqtt.get("tls_insecure"))

    store = Store(DB_PATH)
    STATE = MeshState(store)

    os.makedirs(RUNTIME_DIR, exist_ok=True)
    mqtt_prepare_options()
    if MQTT_BROKER and not shutil.which("mosquitto_pub"):
        print(
            "WARNUNG: MQTT-Broker %s konfiguriert, aber mosquitto_pub nicht gefunden - "
            "MQTT bleibt aus (OpenWrt: apk add mosquitto-client-ssl, "
            "Debian/Raspbian: apt install mosquitto-clients)." % MQTT_BROKER,
            file=sys.stderr, flush=True,
        )
        MQTT_BROKER = None

    stop_event = threading.Event()
    threads = []
    for rid, r in ROUTERS.items():
        t = threading.Thread(
            target=router_worker, args=(rid, r["ip"], stop_event, bool(r.get("local")), r.get("role", "ap")),
            daemon=True, name="poll-%s" % rid,
        )
        t.start()
        threads.append(t)

    if MQTT_BROKER:
        t = threading.Thread(target=mqtt_publisher, args=(stop_event,), daemon=True, name="mqtt-publish")
        t.start()
        threads.append(t)

    httpd = MeshRoamingServer((HTTP_BIND, HTTP_PORT), Handler)

    def handle_signal(signum, frame):
        stop_event.set()
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    hostname = socket.gethostname()
    label = CONFIG.get("network", {}).get("label", "Mesh-Netzwerk")
    print(
        "Mesh-Roaming-Pi-Server %s (%s) laeuft: http://%s:%d/ (bind %s:%d), Konfiguration: %s"
        % (__version__, label, hostname, HTTP_PORT, HTTP_BIND, HTTP_PORT, CONFIG_PATH),
        flush=True,
    )
    httpd.serve_forever()

    stop_event.set()
    for t in threads:
        t.join(timeout=2)


if __name__ == "__main__":
    main()
