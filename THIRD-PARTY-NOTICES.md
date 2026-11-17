# Hinweise zu Software Dritter – Mesh Roaming Dashboard

*English summary: The Mesh Roaming Dashboard (service, live page, OpenWrt
packages, LuCI pages, Raspberry Pi variant) is licensed under the PolyForm
Noncommercial License 1.0.0 (see [`LICENSE`](LICENSE)). The only third-party
code contained in its source tree is the build tool `openwrt-ipk2apk` (MIT,
section 1). Section 2 lists third-party software the dashboard uses at
runtime but does **not** ship.*

Gilt für: Dienst `mesh_roaming_pi.py`, Live-Seite, OpenWrt-Pakete
`mesh-roaming` und `luci-app-mesh-roaming`, Raspberry-Pi-Variante
(`src/`, `systemd/`). Stand: Version 1.2.

## 1. Enthaltene Software Dritter

### openwrt-ipk2apk

- Dateien: `openwrt/tools/openwrt-ipk2apk/openwrt-ipk2apk.py`,
  `openwrt/tools/openwrt-ipk2apk/convert-apk-v2-to-v3.sh`
- Herkunft: <https://github.com/rychly/openwrt-ipk2apk>, Commit `60caa88a`,
  mit zwei dokumentierten Änderungen (siehe
  [`README-vendored.md`](openwrt/tools/openwrt-ipk2apk/README-vendored.md))
- Verwendung: nur als Werkzeug beim Bauen der `.apk`-Pakete. Es ist weder in
  den Paketen noch in der Raspberry-Pi-Variante enthalten.
- Lizenz: MIT, Originaltext auch in
  [`openwrt/tools/openwrt-ipk2apk/LICENSE`](openwrt/tools/openwrt-ipk2apk/LICENSE)

```text
MIT License

Copyright (c) 2026 Marek Rychly <marek@rychly.org>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 2. Genutzte, aber nicht enthaltene Open-Source-Software

Das Dashboard ruft die folgende Software auf oder läuft in ihr. Sie wird
**nicht** mitgeliefert, sondern ist auf dem Zielsystem vorhanden oder wird
vom Paketmanager installiert. Es wird kein Code daraus kopiert oder statisch
eingebunden. Die Liste dient der Transparenz.

### Dienst (Raspberry Pi und OpenWrt)

| Software | Wofür | Lizenz |
|---|---|---|
| Python 3 mit Standardbibliothek | Laufzeit von `mesh_roaming_pi.py` und `mesh-roaming-uci2json` | Python Software Foundation License 2.0 |
| SQLite (über Pythons `sqlite3`) | Ereignis-Log, Gerätenamen | Public Domain |
| OpenSSH-Client (Raspberry Pi, OpenWrt-Paket `openssh-client-utils`) | Abfrage der Router per SSH | BSD-artige Lizenz |
| Mosquitto-Client `mosquitto_pub` (optional) | MQTT-Veröffentlichung | EPL-2.0 / EDL-1.0 |
| `ip` (iproute2 bzw. BusyBox) | Nachbartabelle | GPL-2.0 |

### Nur Raspberry Pi

| Software | Wofür | Lizenz |
|---|---|---|
| systemd | Dienstverwaltung (`systemd/mesh-roaming.service`) | LGPL-2.1+ |

### Nur OpenWrt

| Software | Wofür | Lizenz |
|---|---|---|
| OpenWrt (base-files, procd, `/etc/rc.common`, `/lib/functions.sh`) | Init-Skript, UCI-Zugriff | GPL-2.0 |
| rpcd | Aufruf von `mesh-roaming-status` aus LuCI | ISC |
| uclient-fetch | HTTP-Abfrage in `mesh-roaming-status` | ISC |
| LuCI (luci-base, JavaScript-Framework `form`, `view`, `ui`, `uci`, `fs`) | Oberfläche von `luci-app-mesh-roaming` | Apache-2.0 |

### Auf den abgefragten Routern (nur über Schnittstellen genutzt)

| Software | Wofür | Lizenz |
|---|---|---|
| ubus | Abfrage von hostapd/usteer/DHCP | LGPL-2.1 |
| usteer | Roaming-Daten | GPL-2.0 |
| hostapd | Client- und Kanal-Informationen | BSD-3-Clause |
| Dropbear | SSH-Server der Router | MIT |

### Schriften

Die Live-Seite nennt in ihren CSS-Angaben die Schriftfamilien IBM Plex Sans,
IBM Plex Sans Condensed und IBM Plex Mono (SIL Open Font License 1.1). Sie
werden **nicht** mitgeliefert und nicht nachgeladen. Ist die Schrift
installiert, nutzt der Browser sie, sonst eine Systemschrift.

## 3. Marken

OpenWrt, LuCI, Wi-Fi, Raspberry Pi, Raspbian, openHAB, InfluxDB, Grafana,
TP-Link, Archer und HiLink sind Marken oder eingetragene Marken ihrer
jeweiligen Inhaber. Sie werden hier nur beschreibend verwendet, um
Kompatibilität und Einsatzumgebung zu nennen. Dieses Projekt steht in keiner
Verbindung zu diesen Inhabern und wird von ihnen nicht unterstützt.
