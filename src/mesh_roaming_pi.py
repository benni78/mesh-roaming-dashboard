#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mesh_roaming_pi.py
==================

Ersatz fuer ein PowerShell/plink-basiertes Live-Skript, gedacht zum
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
  aktuellen Live-Snapshot, "POST /api/rename" zum Umbenennen eines Clients.
- Optional (nur wenn mqtt.broker in der Konfiguration gesetzt ist):
  veroeffentlicht einfache Zusammenfassungs-Metriken per MQTT, z.B. um sie
  wie andere Smarthome-Metriken ueber openHAB in InfluxDB/Grafana
  weiterzuverarbeiten. Die Kernvisualisierung bleibt bewusst AUSSERHALB
  von InfluxDB.

Start (manuell zum Testen, aus dem Projektverzeichnis heraus):
    MESH_ROAMING_CONFIG=./examples/config.example.json python3 src/mesh_roaming_pi.py
Anzeige: http://<pi-ip>:8765/
Als Dienst: siehe systemd/mesh-roaming.service bzw.
docs/deployment-raspbian-openhab.md.
"""

import errno
import json
import os
import re
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
        "log_max_entries": 200,
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
    # Kanalauslastung - je AP-Interface (ein Interface pro Funkband wird
    # automatisch ausgewaehlt, s. compute_survey_ifnames()) per "iw dev <ifname>
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
    "routers": [],
    "mqtt": {"broker": None, "base_topic": "mesh-roaming", "publish_interval_sec": 10},
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

    if not cfg.get("ap_ifnames"):
        raise SystemExit("Konfiguration %s: 'ap_ifnames' ist leer." % path)
    if not cfg["ssh"].get("key_path"):
        raise SystemExit("Konfiguration %s: 'ssh.key_path' fehlt." % path)
    if not cfg.get("html_path"):
        cfg["html_path"] = os.path.join(BASE_DIR, "mesh-lageplan-live.html")

    return cfg


# --- Aus der Konfiguration abgeleitete Laufzeit-Werte (siehe main()) -------

CONFIG = None
ROUTERS = {}          # id -> {ip, name, room, map_x, map_y, mgmt_ips}
AP_IFNAMES = []
SURVEY_IFNAMES = []   # Teilmenge von AP_IFNAMES: ein Interface je Funkband/phy (s. compute_survey_ifnames)
UTIL_WINDOW_SEC = 10.0
REMOTE_CMD = ""
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
MQTT_BASE_TOPIC = "mesh-roaming"
MQTT_PUBLISH_INTERVAL_SEC = 10.0

STATE = None  # wird in main() gesetzt


def compute_survey_ifnames(ap_ifnames):
    # Waehlt automatisch GENAU EIN AP-Interface je Funkband/phy aus ap_ifnames
    # aus (das jeweils erste in der konfigurierten Reihenfolge), ueber das
    # spaeter "iw dev <ifname> survey dump" abgefragt wird. Survey-Daten sind
    # eine Eigenschaft des Kanals/der Phy, nicht der einzelnen SSID/des
    # einzelnen AP-Interfaces - jedes AP-Interface derselben Phy liefert
    # identische Kanal-Statistiken, ein zusaetzliches Konfigurationsfeld dafuer
    # waere also redundant (User-Entscheidung).
    seen = {}
    order = []
    for ifn in ap_ifnames:
        grp = ifn.split("-ap")[0] if "-ap" in ifn else ifn
        if grp not in seen:
            seen[grp] = ifn
            order.append(grp)
    return [seen[g] for g in order]


def build_remote_cmd():
    parts = ["echo ===WIRELESS===", "ubus call network.wireless status"]
    for ifname in AP_IFNAMES:
        parts.append("echo ===HOSTAPD-%s===" % ifname)
        parts.append("ubus call hostapd.%s get_clients 2>/dev/null" % ifname)
    parts.append("echo ===USTEER===")
    parts.append("ubus call usteer get_clients 2>/dev/null")
    parts.append("echo ===LEASES===")
    parts.append("cat /tmp/dhcp.leases 2>/dev/null")
    parts.append("echo ===ARP===")
    parts.append("cat /proc/net/arp 2>/dev/null")
    for ifname in SURVEY_IFNAMES:
        parts.append("echo ===SURVEY-%s===" % ifname)
        parts.append("iw dev %s survey dump 2>/dev/null" % ifname)
    parts.append("echo ===DONE===")
    return "; ".join(parts)


def known_hosts_path():
    return os.path.join(os.path.dirname(DB_PATH) or ".", "known_hosts")


def build_ssh_cmd(router_ip):
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
    cmd += ["%s@%s" % (SSH_USER, router_ip), REMOTE_CMD]
    return cmd


# ---- Parsing (Port von Convert-RouterOutput aus mesh-roaming-live.ps1) ----

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
_SURVEY_FREQ_RE = re.compile(r"frequency:\s*([0-9]+)\s*MHz\s*\[in use\]")


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
        return out
    return None


def parse_survey_output(lines):
    result = {}
    for i, ifname in enumerate(SURVEY_IFNAMES):
        start_marker = "===SURVEY-%s===" % ifname
        end_marker = "===SURVEY-%s===" % SURVEY_IFNAMES[i + 1] if i < len(SURVEY_IFNAMES) - 1 else "===DONE==="
        result[ifname] = _parse_one_survey_block(get_section(lines, start_marker, end_marker))
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

    arp_end_marker = "===SURVEY-%s===" % SURVEY_IFNAMES[0] if SURVEY_IFNAMES else "===DONE==="
    for line in get_section(lines, "===ARP===", arp_end_marker):
        if line.strip().startswith("IP address"):
            continue
        parts = line.strip().split()
        if len(parts) >= 4 and MAC_RE.match(parts[3]) and parts[3] != "00:00:00:00:00:00":
            mac = parts[3].lower()
            ips.setdefault(mac, parts[0])

    # Kanalauslastung: Band je Interface aus demselben iface_info, das
    # oben bereits aus ===WIRELESS=== gewonnen wurde - so bleibt "Band" fuer
    # Anzeige/Gruppierung konsistent mit den Client-Zuordnungen.
    survey = {}
    for ifname, sample in parse_survey_output(lines).items():
        if sample is None:
            continue
        info = iface_info.get(ifname)
        sample["band"] = info["band"] if info else None
        survey[ifname] = sample

    return router_result, names, ips, survey


# ---- Persistenz (SQLite als einfacher JSON-Key/Value-Speicher) -----------

class Store:
    def __init__(self, path):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.conn.commit()
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
        # Kanalauslastung - rein im RAM, bewusst NICHT persistiert: es
        # sind kurzlebige gleitende Differenzen (s. UTIL_WINDOW_SEC), nach
        # einem Neustart des Dienstes baut sich die Historie binnen eines
        # Intervalls von selbst wieder auf.
        self.util_history = {}  # rid -> ifname -> deque[(ts, sample-dict)]
        self.util_latest = {}   # rid -> ifname -> berechnetes Ergebnis oder None

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
                new_assignment[mac] = {"rid": rid, "ssid": info.get("ssid"), "signal": info.get("signal")}

        ts = int(time.time() * 1000)
        changed = False
        for mac, info in new_assignment.items():
            to_rid = info["rid"]
            ssid = info["ssid"]
            sig = info["signal"]
            prev = self.last_seen.get(mac)
            from_rid = self._prev_rid(prev)
            if from_rid is None:
                self.log.append({"time": ts, "kind": "connect", "mac": mac, "from": None, "to": to_rid, "signal": sig, "ssid": ssid})
                changed = True
            elif from_rid != to_rid:
                self.log.append({"time": ts, "kind": "roam", "mac": mac, "from": from_rid, "to": to_rid, "signal": sig, "ssid": ssid})
                changed = True
        for mac, prev in list(self.last_seen.items()):
            if mac not in new_assignment:
                self.log.append({
                    "time": ts, "kind": "disconnect", "mac": mac,
                    "from": self._prev_rid(prev), "to": None, "signal": None,
                    "ssid": self._prev_ssid(prev),
                })
                changed = True

        self.last_seen = new_assignment
        self.store.set_json("last_seen", self.last_seen)
        if changed:
            if len(self.log) > LOG_MAX:
                self.log = self.log[-LOG_MAX:]
            self.store.set_json("log", self.log)

    def update_survey(self, rid, survey):
        # survey: ifname -> {"freq_mhz", "active_ms", "busy_ms", "receive_ms",
        # "transmit_ms", "bss_receive_ms", "band"} - kumulative Zaehler aus
        # "iw dev <ifname> survey dump" seit Interface-Up (s. parse_survey_output).
        with self.lock:
            now = time.time()
            router_hist = self.util_history.setdefault(rid, {})
            router_latest = self.util_latest.setdefault(rid, {})
            for ifname, sample in (survey or {}).items():
                if sample is None:
                    continue
                dq = router_hist.setdefault(ifname, deque())
                dq.append((now, sample))
                # Nur so viel Historie behalten wie fuer die naechste Differenz
                # gebraucht wird (etwas mehr als 2x Fensterbreite als Puffer
                # gegen unregelmaessige Poll-Abstaende).
                cutoff = now - (UTIL_WINDOW_SEC * 2 + 5)
                while len(dq) > 2 and dq[0][0] < cutoff:
                    dq.popleft()
                computed = self._compute_util(dq)
                if computed is not None:
                    computed["band"] = sample.get("band")
                router_latest[ifname] = computed

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
        receive_delta = d("receive_ms")
        transmit_delta = d("transmit_ms")
        bss_receive_delta = d("bss_receive_ms")
        if active_delta is None or active_delta <= 0:
            return None

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

        return {
            "freq_mhz": newest.get("freq_mhz"),
            "window_sec": round(elapsed_sec, 1),
            "active_ms": active_delta,
            "own_ms": round(own_ms),
            "foreign_ms": round(foreign_ms),
            "rest_ms": round(rest_ms),
            "own_pct": round(own_ms / active_delta * 100, 1),
            "foreign_pct": round(foreign_ms / active_delta * 100, 1),
            "rest_pct": round(rest_ms / active_delta * 100, 1),
        }

    def rename(self, mac, name):
        mac = mac.lower()
        with self.lock:
            if name:
                self.nicknames[mac] = name
            else:
                self.nicknames.pop(mac, None)
            self.store.set_json("nicknames", self.nicknames)

    def snapshot(self):
        with self.lock:
            router_status = {}
            for rid in ROUTERS:
                rr = self.routers.get(rid) or {}
                router_status[rid] = rr.get("error", "ok") if "error" in rr else "ok"
            return {
                "routers": self.routers,
                "names": self.names,
                "ips": self.ips,
                "nicknames": self.nicknames,
                "log": self.log,
                "channelUtil": self.util_latest,
                "meta": {
                    "generatedAt": int(max(self.generated_at.values()) * 1000) if self.generated_at else 0,
                    "routerStatus": router_status,
                },
            }

    def client_counts_per_router(self):
        with self.lock:
            return {rid: len(self._flat_clients(self.routers.get(rid))) for rid in ROUTERS}

    def log_len(self):
        with self.lock:
            return len(self.log)


# ---- Router-Poller (ein Thread je Router, analog PS-Runspace) -----------

def router_worker(rid, ip, stop_event, local=False):
    # "local": der Dienst laeuft auf genau diesem Router - die
    # ubus-Abfrage wird direkt ueber die lokale Shell ausgefuehrt statt per
    # SSH auf sich selbst. Timeout/Fehlerbehandlung bleiben identisch zum
    # SSH-Fall, nur der eigentliche Verbindungsaufbau entfaellt.
    cmd = [ "/bin/sh", "-c", REMOTE_CMD ] if local else None
    while not stop_event.is_set():
        try:
            proc = subprocess.run(
                cmd if local else build_ssh_cmd(ip),
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

def mqtt_publisher(stop_event):
    if not MQTT_BROKER:
        return
    while not stop_event.is_set():
        try:
            counts = STATE.client_counts_per_router()
            for rid, n in counts.items():
                subprocess.run(
                    ["mosquitto_pub", "-h", MQTT_BROKER, "-t", "%s/%s/clients" % (MQTT_BASE_TOPIC, rid), "-m", str(n)],
                    timeout=3, check=False,
                )
            subprocess.run(
                ["mosquitto_pub", "-h", MQTT_BROKER, "-t", "%s/roam_events_total" % MQTT_BASE_TOPIC, "-m", str(STATE.log_len())],
                timeout=3, check=False,
            )
        except Exception:
            pass
        stop_event.wait(MQTT_PUBLISH_INTERVAL_SEC)


# ---- Oeffentliche (netzwerkspezifische) Konfiguration fuer die HTML-Seite -

def public_config():
    return {
        "network": CONFIG.get("network", {}),
        "routers": [
            {
                "id": r["id"], "ip": r["ip"], "name": r["name"], "room": r["room"],
                "map_x": r["map_x"], "map_y": r["map_y"], "mgmt_ips": r.get("mgmt_ips") or [],
            }
            for r in CONFIG["routers"]
        ],
        "roaming": CONFIG["roaming"],
        "signal": CONFIG["signal"],
        "map": CONFIG["map"],
        "channel_util": CONFIG["channel_util"],
    }


# ---- HTTP-Server ----------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "MeshRoamingPi/1.0"

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
        else:
            self.send_error(404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
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
    global CONFIG, STATE, ROUTERS, AP_IFNAMES, SURVEY_IFNAMES, UTIL_WINDOW_SEC, REMOTE_CMD
    global SSH_USER, SSH_KEY, SSH_CONNECT_TIMEOUT, SSH_COMMAND_TIMEOUT
    global USE_CONTROL_MASTER, CONTROL_PERSIST, POLL_INTERVAL_SEC
    global HTTP_BIND, HTTP_PORT, DB_PATH, RUNTIME_DIR, HTML_PATH, LOG_MAX
    global MQTT_BROKER, MQTT_BASE_TOPIC, MQTT_PUBLISH_INTERVAL_SEC

    CONFIG = load_config(CONFIG_PATH)

    ROUTERS = {r["id"]: r for r in CONFIG["routers"]}
    AP_IFNAMES = CONFIG["ap_ifnames"]
    SURVEY_IFNAMES = compute_survey_ifnames(AP_IFNAMES)
    UTIL_WINDOW_SEC = float(CONFIG["channel_util"]["interval_sec"])
    REMOTE_CMD = build_remote_cmd()

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

    MQTT_BROKER = CONFIG["mqtt"].get("broker") or None
    MQTT_BASE_TOPIC = CONFIG["mqtt"]["base_topic"]
    MQTT_PUBLISH_INTERVAL_SEC = float(CONFIG["mqtt"]["publish_interval_sec"])

    store = Store(DB_PATH)
    STATE = MeshState(store)

    os.makedirs(RUNTIME_DIR, exist_ok=True)

    stop_event = threading.Event()
    threads = []
    for rid, r in ROUTERS.items():
        t = threading.Thread(
            target=router_worker, args=(rid, r["ip"], stop_event, bool(r.get("local"))),
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
        "Mesh-Roaming-Pi-Server (%s) laeuft: http://%s:%d/ (bind %s:%d), Konfiguration: %s"
        % (label, hostname, HTTP_PORT, HTTP_BIND, HTTP_PORT, CONFIG_PATH),
        flush=True,
    )
    httpd.serve_forever()

    stop_event.set()
    for t in threads:
        t.join(timeout=2)


if __name__ == "__main__":
    main()
