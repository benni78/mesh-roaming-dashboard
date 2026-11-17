# Hinweise zu Software Dritter / Third-Party Notices

*English summary: This project's own code is licensed under the PolyForm
Noncommercial License 1.0.0 (see [`LICENSE`](LICENSE)). The only third-party
code contained in this repository is `openwrt-ipk2apk` (MIT, section 1).
Section 2 lists third-party software that the programs use at runtime or
build time but that is **not** contained in this repository or in the
packages under `packages/`.*

Stand: mesh-roaming-dashboard 1.2, WLAN-Analyzer 1.1.0

## 1. In diesem Repository enthaltene Software Dritter

### openwrt-ipk2apk

- Dateien: `openwrt/tools/openwrt-ipk2apk/openwrt-ipk2apk.py`,
  `openwrt/tools/openwrt-ipk2apk/convert-apk-v2-to-v3.sh`
- Herkunft: <https://github.com/rychly/openwrt-ipk2apk>, Commit `60caa88a`,
  mit zwei dokumentierten Änderungen (siehe
  [`README-vendored.md`](openwrt/tools/openwrt-ipk2apk/README-vendored.md))
- Verwendung: nur als Werkzeug beim Bauen der `.apk`-Pakete, nicht
  Bestandteil der Pakete
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

Die Programme dieses Projekts rufen die folgende Software auf oder laufen in
ihr. Sie wird **nicht** mit diesem Projekt weitergegeben, sondern ist auf dem
Zielsystem vorhanden oder wird vom Paketmanager installiert. Es wird kein Code
daraus kopiert oder statisch eingebunden. Die Liste dient der Transparenz und
nennt die jeweils maßgebliche Lizenz des Originalprojekts.

### Dienst `mesh-roaming` (Raspberry Pi / OpenWrt)

| Software | Wofür | Lizenz |
|---|---|---|
| Python 3 mit Standardbibliothek | Laufzeit von `mesh_roaming_pi.py` und `mesh-roaming-uci2json` | Python Software Foundation License 2.0 |
| SQLite (über Pythons `sqlite3`) | Ereignis-Log, Gerätenamen | Public Domain |
| OpenSSH-Client bzw. Dropbear | Abfrage der Router per SSH | BSD-artige Lizenzen bzw. MIT |
| Mosquitto-Client `mosquitto_pub` (optional) | MQTT-Veröffentlichung | EPL-2.0 / EDL-1.0 |
| `ip` (iproute2 bzw. BusyBox) | Nachbartabelle | GPL-2.0 |
| systemd (nur Raspberry Pi) | Dienstverwaltung | LGPL-2.1+ |

### Auf den OpenWrt-Routern (nur über Schnittstellen genutzt)

| Software | Wofür | Lizenz |
|---|---|---|
| OpenWrt (base-files, procd, `/etc/rc.common`, `/lib/functions.sh`) | Init-Skript, UCI-Zugriff | GPL-2.0 |
| ubus | Abfrage von hostapd/usteer/DHCP | LGPL-2.1 |
| usteer | Roaming-Daten | GPL-2.0 |
| hostapd | Client- und Kanal-Informationen | BSD-3-Clause |
| rpcd | Aufruf von `mesh-roaming-status` aus LuCI | ISC |
| uclient-fetch | HTTP-Abfrage in `mesh-roaming-status` | ISC |
| LuCI (luci-base, JavaScript-Framework `form`, `view`, `ui`, `uci`, `fs`) | Oberfläche von `luci-app-mesh-roaming` | Apache-2.0 |

### WLAN-Analyzer (Windows)

| Software | Wofür | Lizenz |
|---|---|---|
| .NET 8 Runtime und Windows Forms | Laufzeit | MIT, © .NET Foundation and Contributors |
| Windows Native WiFi API (`wlanapi.dll`) | WLAN-Scan | Bestandteil von Windows, Microsoft-Lizenzbedingungen |

Der Analyzer nutzt keine NuGet-Pakete. **Wird er als eigenständige EXE
veröffentlicht** (`dotnet publish --self-contained`), enthält die EXE die
.NET-Laufzeit. Dann gehören zur Weitergabe zusätzlich deren Lizenz (MIT) und
die Drittanbieter-Hinweise von .NET:
<https://github.com/dotnet/runtime/blob/main/LICENSE.TXT> und
<https://github.com/dotnet/runtime/blob/main/THIRD-PARTY-NOTICES.TXT>.
Beim normalen Build (abhängig von installiertem .NET) ist das nicht nötig.

### Schriften

Die Live-Seite nennt in ihren CSS-Angaben die Schriftfamilien IBM Plex Sans,
IBM Plex Sans Condensed und IBM Plex Mono (SIL Open Font License 1.1). Sie
werden **nicht** mitgeliefert und nicht nachgeladen. Ist die Schrift
installiert, nutzt der Browser sie, sonst eine Systemschrift. Der
WLAN-Analyzer verwendet die Windows-Systemschrift Segoe UI, ebenfalls nicht
mitgeliefert.

## 3. Marken

OpenWrt, LuCI, Wi-Fi, Wi-Fi 6/6E/7, Windows, Visual Studio, Raspberry Pi,
Raspbian, openHAB, InfluxDB, Grafana, TP-Link, Archer und HiLink sind Marken
oder eingetragene Marken ihrer jeweiligen Inhaber. Sie werden hier nur
beschreibend verwendet, um Kompatibilität und Einsatzumgebung zu nennen.
Dieses Projekt steht in keiner Verbindung zu diesen Inhabern und wird von
ihnen nicht unterstützt.
