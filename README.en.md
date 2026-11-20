# Mesh Roaming Dashboard

[Deutsch](README.md) · **English**

## What is it?

A self-hosted live dashboard for OpenWrt-based WiFi mesh networks (usteer):
a floor-plan map showing which router each client is connected to, roaming
history, signal strength and channel utilization per radio — in your
browser, in real time. No cloud, no app, just one Python service that
polls your own routers over SSH.

It runs as a small Python 3 service (standard library only), either on a
Raspberry Pi (e.g. alongside openHAB, see
[`docs/deployment-raspbian-openhab.md`](docs/deployment-raspbian-openhab.md))
or directly on OpenWrt. Everything network-specific (routers, IPs, SSIDs,
map layout, thresholds) lives in one `config.json` — the service and the
web page stay the same for any mesh. See
[`examples/config.example.json`](examples/config.example.json) for the
format.

There are two deployment variants: Raspbian/Debian (works well alongside
openHAB, see above) and directly on a mesh router instead of a separate Pi,
with an optional LuCI configuration page — see
[`docs/deployment-openwrt.md`](docs/deployment-openwrt.md) and the
[`openwrt/`](openwrt) directory. The documentation in `docs/` and the code
comments are in German.

![Example view of the dashboard with four routers, clients, roaming log and channel utilization](docs/images/dashboard-beispiel.png)

*Example view with made-up test data (routers, clients and values from
`examples/config.example.json`) — no real network data.*

## ⚠ Privacy notice (GDPR): this tool creates a personal movement profile

**This section is not an add-on, it is a prerequisite for using the tool.**
Please read it completely before installing the tool on your network —
especially if devices of other people (family, flatmates, tenants, guests,
visitors, possibly employees) use that network.

### What this tool actually records

For every device that connects to one of the monitored routers, the service
continuously records:

- which router/access point the device is currently connected to (and thus
  which place/room, if the router map is set up accordingly),
- which other access points can also receive it (including signal
  strength — an approximation of distance),
- every change of access point with its time (connect/roam/disconnect
  events, logged centrally in an SQLite database that survives a service
  restart),
- optionally a real name/nickname per device assigned by the operator,
  which explicitly links device → person,
- from the routers' DHCP leases and ARP table, the hostname and IP address
  of **all** devices on the network, including wired ones. Hostnames often
  already contain a person's name ("Annas-iPhone"). They are only stored
  for the retention period; the web interface only receives the hostnames
  of devices actually shown on the map, and no IP addresses at all.

**Since v22 this is time-limited by default, no longer unlimited:** the
configuration option `privacy.retention_days` (default: 7 days, adjustable
via UCI/LuCI on the "Datenschutz" (privacy) tab) automatically and
permanently deletes all device-related data (MAC address, name, IP,
nickname, roaming log entries) of a device from the SQLite database once it
has not been seen for that many days — not just from the display. In
addition, the service keeps (can be disabled via
`privacy.anonymous_stats_enabled`) an hourly, **MAC-free** summary (number
of events + average signal strength per router/band), which is kept
indefinitely. **Caution:** in a small household this statistic is not
reliably anonymous — if only one person lives there, "connect at 11 pm at
the bedroom router" shows when this person was where, even without a MAC
address (see "Known limitations" below). `POST /api/erase {"mac": "..."}`
deletes the data of a single device immediately at any time (Art. 17 GDPR),
regardless of the retention period. This does not change the following
sections: **during the retention period** a personal movement profile is
still created, and a legal basis for it (see below) is still required.

### Why this is a personal movement profile

WiFi-capable devices (smartphones above all) are practically always with
exactly one person in everyday life. The combination of "which device was
at which access point/place when", stored continuously over time, therefore
effectively results in a movement and location profile of the person who
owns the device — regardless of whether a real name is stored: a device MAC
address that is stable over time already makes a person re-identifiable
within the meaning of the GDPR, and a stored nickname makes this link
explicit. The dashboard is technically built for exactly this purpose
(showing where which device/person currently is in the monitored area and
how it moves there) — this is not a side effect, it is the core function.

This does not only affect the person who installs the tool: **every person
whose device connects to the monitored WiFi** is recorded — even without
their knowledge or consent, unless this is explicitly arranged. This
includes family members, flatmates, tenants of separate units in the same
mesh, guests, visitors and — when used outside a purely private
household — customers or employees.

### Legal assessment (overview, not legal advice)

- Location/movement data of an identifiable natural person is personal data
  within the meaning of Art. 4(1) GDPR. If it is used to analyse or predict
  a person's location or movement patterns, this may additionally qualify
  as profiling under Art. 4(4) GDPR.
- Every processing operation needs a legal basis under Art. 6 GDPR. In a
  shared network with several people, in practice this usually means the
  informed consent of everyone affected (Art. 6(1)(a) GDPR) — an overriding
  legitimate interest of the operator (Art. 6(1)(f) GDPR) will regularly be
  hard to justify for such a detailed, persistently stored movement profile
  of other people.
- The so-called household exemption (Art. 2(2)(c) GDPR) only applies to
  processing by a natural person for purely personal or household
  purposes — it no longer applies as soon as the tool records people
  outside this narrow circle (e.g. tenants of a separate unit, guests, or
  any use in a business/professional context).
- If affected people are informed, the transparency obligations of
  Art. 13/14 GDPR apply as well, together with the principles of data
  minimisation and storage limitation (Art. 5 GDPR) and the data subject
  rights (including access and erasure, Art. 15/17 GDPR).
- In an employment context, § 26 BDSG (German Federal Data Protection Act)
  and any co-determination rights of employee representatives must also be
  considered.
- Covert, undisclosed location monitoring of people without their
  knowledge (e.g. of tenants or flatmates) may, depending on the
  circumstances and jurisdiction, also be relevant under criminal law, not
  just data protection law.

### Practical recommendations (voluntary, but strongly advised)

- Actively inform everyone whose devices use (or could use) the monitored
  WiFi before going live and — where possible — obtain their consent; no
  covert monitoring.
- Restrict access to the dashboard: the service has **no login** (see
  "Known limitations"). Make the port (default 8765) reachable only from
  the trusted network, e.g. set `http.bind` or the UCI option `bind` to the
  LAN IP instead of `0.0.0.0`, and make sure guest WiFi/IoT networks cannot
  reach the router or Pi through the firewall. For more protection, put a
  reverse proxy with authentication in front of it.
- Actively limit the storage period: `privacy.retention_days` (default
  7 days) automatically deletes device-related data from the SQLite
  database, not just from the display — unlike `log_max_entries`, which is
  still only a safety limit on the number of entries, not a time limit.
  Choose a period as short as your purpose (e.g. troubleshooting)
  requires.
- In small households, disable `privacy.anonymous_stats_enabled` if you do
  not need long-term trends.
- If MQTT is enabled, also limit retention in openHAB/InfluxDB (retention
  policy), because the number of clients per router ends up there
  permanently — and with it, who was in which room when.
- Do without the nickname/rename function if explicit re-identification of
  people is to be avoided.
- Limit operation to the group of people and time period actually needed
  instead of permanently recording all devices.
- For any use outside a purely private household (see household exemption
  above), get legal advice beforehand (data protection officer, lawyer).

### Technical safeguards (as of 1.1)

- **Storage limitation:** device-related data is deleted from the database
  after `privacy.retention_days` without being seen; individual devices
  immediately via `POST /api/erase`. SQLite runs with `secure_delete`, so
  deleted data does not remain as leftovers in the file.
- **File permissions:** the database, `config.json` (may contain the MQTT
  password), `known_hosts` and the MQTT options file are readable by the
  service only (0600).
- **No third parties:** the web interface does not load external fonts,
  scripts or CDNs — the viewer's browser only talks to the service itself.
- **Data minimisation in the output:** `/data.json` contains no IP
  addresses, and hostnames only for devices that appear on the map.
  `/config.json` and `/api/status` (status column in LuCI) contain no
  device data.
- **Protection against foreign websites (CSRF):** `POST /api/rename` and
  `/api/erase` only accept requests with `Content-Type: application/json`
  and a matching origin. A foreign website opened by someone on the home
  network therefore cannot rename devices or delete data. Command line:
  `curl -H 'Content-Type: application/json' -d
  '{"mac":"aa:bb:cc:dd:ee:ff"}' http://<host>:8765/api/erase`.
- **MQTT:** only totals are sent (clients per router, length of the event
  log) and the channel utilization, no MAC addresses or names. Credentials do not appear in the process
  list; TLS is supported and recommended for a broker outside the
  router/Pi.
- **No access logs:** the web server does not log requests (no viewer IP
  addresses in the log).

### Known limitations

- **No login:** anyone who can reach the port sees live which device is in
  which room, and can rename devices or delete their data. Protection only
  via network/firewall or a reverse proxy (see above).
- **Anonymous statistics:** kept indefinitely and traceable to individuals
  in small households.
- **Erasing a connected device:** `POST /api/erase` deletes the stored
  data, but a device that is still connected is recorded again on the next
  poll. The only permanent fix is to take the device off the monitored
  WiFi.
- **Router access:** the service logs in to all routers via SSH as `root`
  with a key. Whoever has the key has the routers — keep the file readable
  by root only (`chmod 600`).

**This section is not legal advice.** The actual data protection
assessment depends on the specific case (context of use, people affected,
applicable national law). If in doubt, seek expert advice before use.

## Features

- Live map with routers, clients and roaming arrows on a freely
  positionable floor plan (SVG, 900×600).
- Signal strength radar per client (rings at configurable dBm thresholds).
- Central event log (connect/roam/disconnect) in SQLite — consistent for
  all viewers, survives a service restart.
- Detail panel per client: history, current connection, which other
  routers can also receive the device.
- Channel utilization per router and radio, from
  `iw dev <ifname> survey dump` (see [Channel utilization](#channel-utilization)).
- **Neighbouring channels (WiFi scan, since 2.0):** the routers scan the
  WiFi environment periodically; two charts (2.4 and 5 GHz) show how busy
  each channel is, split into own and foreign networks, with a channel
  recommendation (see [Neighbouring channels](#neighbouring-channels-wifi-scan)).
- **Measuring points:** a router that is only a WiFi client in the network
  can be added as a "measuring point" (`sensor`) and then only measures the
  channel utilization of its radios.
- Client dots: filled dot = 5 GHz, ring = 2.4 GHz.
- Clients can be renamed in the UI (nickname), stored permanently.
- Optional: metrics via MQTT (e.g. for InfluxDB/Grafana), optionally with
  username/password and TLS (see [MQTT topics](#mqtt-topics)).

### Channel utilization

For each radio (phy) the service picks any interface of that radio (AP,
client, mesh or monitor) and reads `iw dev <ifname> survey dump`. It shows
the difference over the last `channel_util.interval_sec` seconds, not the
value since the interface came up. How the busy time is split depends on
the WiFi driver:

| Driver reports … | Examples | Split |
|---|---|---|
| `channel BSS receive time` | mt76 (MediaTek) | **own network** (own BSS received + sent; on a client interface the connected network including all its devices) · **foreign networks** · free |
| no BSS receive time | ath9k (e.g. AR9340, AR9580) | **transmit** · **receive** (all WiFi networks on the channel – own and foreign together, cannot be separated) · **interference** (busy, but no decodable WiFi frame: other radio technology, too weak or collided frames) · free |

Each band also shows the channel, total busy time and noise; for a client
interface also the network it is connected to. Below each band the WiFi
driver is shown together with whether it can separate own and foreign
traffic.

**Rating noise and signal:** the noise value comes with a rating (up to
−90 dBm **good**, −89 to −80 dBm **fair**, above that **poor**; the more
negative, the better). For a client interface (measuring point) the signal
of the connected AP and the signal-to-noise ratio (SNR = signal − noise)
are added: 40 dB and more very good, 25–39 dB good, 15–24 dB sufficient,
below that poor. The thresholds are common rules of thumb; the tooltip
explains them. (The labels on the page are in German.)

**Own traffic via the connected devices:** the service also sums up the
transmit and receive time of all connected devices (clients of an AP, the
link to the AP for a measuring point) from `iw dev <if> station dump`
(`rx duration`/`tx duration`). It is shown below each band for comparison
("Eigener Verkehr 20 % · Kanal belegt 35 %"). For chips without BSS receive
time (ath9k) it also splits the receive share into "received from own
devices (measured)" and "other WiFi networks". Beacons and management
frames are not included. If the driver does not provide these counters,
the line is omitted.

**Setting up a measuring point:** add the router like any other (SSH key,
IP, map position) and set the role to "Messpunkt" (LuCI: Routers → Edit →
Rolle; JSON: `"role": "sensor"`). It measures the channel the client
interface is currently on, i.e. the channel of the access point it is
connected to. The service does not query client lists, DHCP leases or ARP
tables from measuring points.

### Neighbouring channels (WiFi scan)

Every `scan.interval_sec` seconds (default 60, 0 = off) each router evaluates
the networks it found last (`iw dev <if> scan dump`, one interface per
radio). The results of all routers are merged; networks no router has seen
for `scan.max_age_sec` are dropped. The live page shows two bar charts,
2.4 and 5 GHz, without history:

- **Height** = how busy the 20 MHz channel is. **Measured** (solid bar): the
  highest value an access point on this channel reports in its beacons
  (*BSS Load*, caused by all networks). **Estimated** (hatched): without that
  value, an occupancy index from number and signal strength of the networks
  overlapping the channel (up to 20 points per network, −95 dBm = 5 % to
  −50 dBm = 100 %) – a rough indicator, not a measurement.
- **Blue/red** = share of own/foreign networks (by connected devices if all
  networks involved report them, otherwise by signal-weighted network
  count). The SSIDs and BSSIDs of your own access points count as own
  automatically, plus `scan.own_ssids`.
- **Number above the bar** = number of networks; tooltip with the strongest
  networks; bold channel number = channel with own networks; DFS range
  shaded on 5 GHz.
- **Recommendation**: channel with the least use by foreign networks
  (2.4 GHz: 1, 6 or 11; 5 GHz: 80 MHz block, non-DFS preferred).

Above each bar chart there is a **spectrum** (since 2.1): every network as
an area over its occupied bandwidth (20/40/80/160 MHz), height = signal
strength, with the **network name** above it. Own networks (★) bold in cool
colours, foreign ones faint in warm colours; the colour is tied to the
SSID. Names are placed without overlap (own first, then the strongest
foreign ones); whatever finds no room is in the tooltip. The channel axis
is the same as in the bar chart below.

Same logic as the WLAN Analyzer (Windows). **Active scanning** depends on
`scan.trigger` (LuCI: Grundeinstellungen → WLAN-Scan):

| Value | Behaviour |
|---|---|
| `clients` (default) | client interfaces only (measuring points) – the WiFi client scans anyway, the connection is practically undisturbed |
| `all` | access points as well (`ap-force`) – the radio briefly leaves its channel, connected devices notice a short pause |
| `off` | no active scanning, only evaluate existing results |

A router that is only an access point usually reports no networks with
`clients`; use a measuring point or choose `all`. SSIDs of foreign networks
are identifiers broadcast publicly by access points, not device data; they
are not stored, only kept in memory. The page shows SSID, signal and
channel (clearly visible in the spectrum), but no BSSIDs.

### MQTT topics

With `mqtt.broker` set, the service publishes every
`mqtt.publish_interval_sec` seconds (prefix `mqtt.base_topic`, default
`mesh-roaming`):

| Topic | Value |
|---|---|
| `<base>/<router>/clients` | number of connected clients (not for measuring points) |
| `<base>/roam_events_total` | entries in the event log |
| `<base>/<router>/util/<band>/busy` | channel busy in total, % |
| `<base>/<router>/util/<band>/own`, `…/foreign` | own / foreign use, % (drivers with BSS receive time) |
| `<base>/<router>/util/<band>/rx`, `…/tx`, `…/other` | receive / transmit / interference, % (drivers without BSS receive time) |
| `<base>/<router>/util/<band>/free` | free, % |
| `<base>/<router>/util/<band>/noise` | noise, dBm |
| `<base>/<router>/util/<band>/signal`, `…/snr` | client interface: signal of the AP (dBm), signal-to-noise ratio (dB) |
| `<base>/<router>/util/<band>/channel` | current channel |
| `<base>/<router>/util/<band>/mode` | `own_foreign` (chip separates own/foreign) or `rx_tx` (chip cannot) |
| `<base>/<router>/util/<band>/driver` | WiFi driver, e.g. `ath9k`, `mt7915e` |
| `<base>/<router>/util/<band>/own_sta` | own traffic measured via the connected devices, % |
| `<base>/<router>/util/<band>/rx_own`, `…/rx_other` | received from own devices / other networks, % (drivers without BSS receive time) |
| `<base>/scan/<band>/recommendation` | WiFi scan: channel recommendation, e.g. `Kanal 6` |
| `<base>/scan/<band>/channels` | WiFi scan: occupancy per channel as JSON, e.g. `{"1":12.5,"6":30.1,…}` |

`<band>` is `2g`, `5g` or `6g`. If a router has two radios in the same
band, the radio name (`phy0`, `phy1`, …) is used instead. Values the driver
does not report are not published.
- Automatic storage limitation (GDPR): device-related data expires after
  `privacy.retention_days` (default 7 days), a MAC-free long-term statistic
  is kept for trend analysis, immediate erasure of individual devices via
  `POST /api/erase`.

## Architecture

- `src/mesh_roaming_pi.py` — the service: polls all routers via SSH (one
  background thread per router), combines the results and serves the live
  page plus `/config.json`/`/data.json` over HTTP.
- `src/mesh-lageplan-live.html` — the live page itself. Contains **no**
  network-specific data, loads everything from the server.
- `examples/config.example.json` / `examples/config.template.json` —
  example and placeholder configuration as a starting point for your own
  `config.json`.
- `systemd/mesh-roaming.service` — systemd unit for continuous operation
  on Raspbian/Debian.
- `openwrt/mesh-roaming/` — OpenWrt package source (procd init script, UCI
  configuration schema, UCI→JSON bridge `mesh-roaming-uci2json`) for
  running directly on a mesh router instead of a separate Pi.
- `openwrt/luci-app-mesh-roaming/` — optional LuCI configuration pages for
  the OpenWrt package (basic settings, routers, SSID colours).
- `openwrt/build-ipk.sh` — builds installable `.ipk` files from both
  package sources (without the OpenWrt SDK).
- `packages/` — ready-built packages of the current version.

Requirement on the routers: OpenWrt with `usteer` and `hostapd` (the
default in most current mesh setups).

## Quick start (OpenWrt, directly on a mesh router)

**Important — first check which package manager the router uses**
(`opkg --version` or `apk --version`): since OpenWrt 25.12, `apk`
(Alpine style) is the default on many targets instead of `opkg` — a
different package format, not just a different command. An `.ipk` cannot
be installed with `apk`.

### Ready-built packages (no build needed)

The [`packages/`](packages/) directory contains ready-built packages of
the current version (architecture `all`, run on any target):

| File | for |
|---|---|
| `mesh-roaming_2.1-r1_all.apk` | service, OpenWrt 25.12+ (`apk`) |
| `luci-app-mesh-roaming_2.1-r1_all.apk` | LuCI pages, OpenWrt 25.12+ (`apk`) |
| `mesh-roaming_2.1-r1_all.ipk` | service, OpenWrt up to 24.10 (`opkg`) |
| `luci-app-mesh-roaming_2.1-r1_all.ipk` | LuCI pages, OpenWrt up to 24.10 (`opkg`) |

```sh
# on the PC: copy the packages to the router (-O: Dropbear has no SFTP)
scp -O packages/*_2.1-r1_all.apk packages/SHA256SUMS root@<router-ip>:/tmp/

# on the router (apk, OpenWrt 25.12+)
cd /tmp
grep apk SHA256SUMS | sha256sum -c -   # optional: packages intact?
apk update
apk add --allow-untrusted ./mesh-roaming_2.1-r1_all.apk ./luci-app-mesh-roaming_2.1-r1_all.apk

# or on the router (opkg, up to OpenWrt 24.10)
opkg update
opkg install ./mesh-roaming_2.1-r1_all.ipk ./luci-app-mesh-roaming_2.1-r1_all.ipk
```

The package manager fetches the dependencies (`python3`, `python3-sqlite3`,
`openssh-client-utils`, `luci-base`, `rpcd`) from the OpenWrt package
feeds itself, so run `apk update` or `opkg update` first.
`--allow-untrusted` is required because the packages are not signed with
an OpenWrt key. The `.apk` files are built in APK v2 format and tested on
OpenWrt 25.12.6 (x86/64), the `.ipk` files on OpenWrt 23.05.6 (x86/64).
Then **log out of LuCI and log in again** (LuCI caches the menu per login
in the browser; without a new login the new entry, possibly even the whole
*Services* menu, is missing) and add your routers under
*Services → Mesh Roaming Dashboard*. The LuCI pages are in German. The
router itself is already entered as "Dieser Router" (this router; name and
IP from hostname and LAN), so the service runs right after installation.
If there is no router entry at all, it is added again on the next start.
To hide it from the map, set it to "Deaktiviert" (disabled).

When upgrading, `opkg` may report under "Collected errors"
`resolve_conffiles: Existing conffile /etc/config/mesh-roaming is different
…`. This is not an error: your configuration is kept, the template from the
new package is placed at `/etc/config/mesh-roaming-opkg` (with `apk`:
`mesh-roaming.apk-new`) and can be deleted.

### Building yourself

```sh
cd openwrt
./build-ipk.sh
# -> openwrt/dist/mesh-roaming_<version>_all.ipk
# -> openwrt/dist/luci-app-mesh-roaming_<version>_all.ipk   (optional, LuCI pages)

./build-apk.sh   # ONLY for apk routers: additionally converts the .ipk files to .apk
```

Then copy to the router with `scp` and install with `opkg install` (or
`apk add --allow-untrusted` for `.apk`). Full instructions (package
manager detection, `.apk` conversion incl. APK v2/v3, configuration via
LuCI or UCI, SSH keys, uninstalling), in German:
[`docs/deployment-openwrt.md`](docs/deployment-openwrt.md).

## Quick start (Raspbian/Debian, e.g. alongside openHAB)

See [`docs/deployment-raspbian-openhab.md`](docs/deployment-raspbian-openhab.md)
(in German) for the full instructions (service user, configuration, SSH
keys, systemd).

Short version for trying it out locally:

```sh
cp examples/config.example.json /tmp/config.json
# edit /tmp/config.json: enter your own routers/IPs/SSIDs
MESH_ROAMING_CONFIG=/tmp/config.json python3 src/mesh_roaming_pi.py
```

Then open in the browser: **http://localhost:8765/** (or, when running on
the Pi: `http://<ip-or-hostname-of-the-pi>:8765/` — port 8765 can be
changed in `config.json` under `http.port`).

`openwrt/feed-makefiles/` contains templates for a possible later
submission to the official `openwrt/packages` feed. This has not been done
yet — among other things because the current licence (PolyForm
Noncommercial, see below) is probably not compatible with the licence
requirements of the official feed, which is also redistributed in
commercial firmware images.

## Extra tool: WLAN Analyzer (Windows)

[`tools/WlanAnalyzer/`](tools/WlanAnalyzer/) contains a standalone Windows
client (C#, Visual Studio 2022 / .NET 8) that uses the PC's own WiFi adapter
to read all networks in range and shows the spectrum, channel utilization
(own vs. foreign networks) and signal history — without router access and
without InfluxDB. Details (in German):
[`tools/WlanAnalyzer/README.md`](tools/WlanAnalyzer/README.md).

## License

[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0) —
see [`LICENSE`](LICENSE). Private, scientific, charitable and other
non-commercial use, modification and redistribution are freely permitted.
**Commercial licences available on request.**

This makes the project *source-available*, but not open source as defined by
the OSI, because commercial use is excluded. Anyone passing on copies or
modified versions must include the licence and the line `Required Notice:
Copyright Benjamin Johann (mesh-roaming-dashboard)`. For this, the packages in
`packages/` contain `LICENSE` and `THIRD-PARTY-NOTICES.md` under
`/usr/share/licenses/<package>/`; for the Raspberry Pi variant both are copied
to `/opt/mesh-roaming/` (see the
[guide](docs/deployment-raspbian-openhab.md), in German).

**Third-party software:** The only third-party code included in the dashboard
is the MIT-licensed tool `openwrt-ipk2apk` (in `openwrt/tools/`). All other
programs used (Python, OpenWrt, LuCI …) are not shipped. Details and licence
texts: [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).

The WLAN Analyzer in `tools/WlanAnalyzer/` is a separate program with its own
[`LICENSE`](tools/WlanAnalyzer/LICENSE) (also PolyForm Noncommercial) and its
own [third-party notices](tools/WlanAnalyzer/THIRD-PARTY-NOTICES.md).

## Versions

| Program | Version | Shown in |
|---|---|---|
| Service `mesh_roaming_pi.py`, live page, `mesh-roaming-uci2json`, `mesh-roaming-status`, LuCI pages, systemd unit, build scripts | 2.1 | `--version`, live page header, LuCI page title, `/config.json` |
| Raspberry Pi variant (`src/`, `systemd/`) | 2.1 | `python3 /opt/mesh-roaming/mesh_roaming_pi.py --version`, live page header |
| OpenWrt packages `mesh-roaming`, `luci-app-mesh-roaming` | 2.1-r1 | `apk info -v` or `opkg list-installed` |
| WLAN Analyzer | 1.1.1 | title bar, *Info*, `--version`, EXE file properties |

Changes per version: [`CHANGELOG.md`](CHANGELOG.md). All version strings of
the dashboard carry the marker `MESH_ROAMING_VERSION`; `openwrt/build-ipk.sh`
aborts if one of them does not match the version in `control/control`.
