# Mesh Roaming Dashboard

A self-hosted, live dashboard for OpenWrt-based WiFi mesh networks (usteer):
a floor-plan map showing which router each client is connected to, roaming
history, signal strength and per-radio channel utilization — in your
browser, updated in real time. No cloud, no app, just one Python service
polling your routers over SSH.

Runs as a small Python 3 (standard-library only) service, either directly
on a Raspberry Pi (e.g. alongside openHAB — see
[`docs/deployment-raspbian-openhab.md`](docs/deployment-raspbian-openhab.md))
or on OpenWrt itself. Everything network-specific (routers, IPs, SSIDs,
floor-plan layout, thresholds) lives in one `config.json` — the service and
the web page stay the same for any mesh. See
[`examples/config.example.json`](examples/config.example.json) for the
format.

Two deployment variants are available: Raspbian/Debian (openHAB-friendly,
see above) and an OpenWrt-router-hosted variant that runs directly on a
mesh router instead of a separate Pi, with an optional LuCI configuration
page — see
[`docs/deployment-openwrt.md`](docs/deployment-openwrt.md) and the
[`openwrt/`](openwrt) directory.

**⚠ Privacy / GDPR notice:** this tool tracks, for every device on your
network, which router/room it is near and when it moves between them,
and stores that history persistently. If devices are tied to individuals
(phones usually are), this is personal movement-profile data about real
people — not just about "your network". Operating this requires a legal
basis under the GDPR/DSGVO (and any other applicable law) for everyone
whose devices appear, not only the operator. See the German section
"Datenschutz-Hinweis (DSGVO)" below for the full explanation — this is
not legal advice.

The documentation below is in German, matching the project's origin; code
comments are German throughout.

---

## Was ist das?

Eine selbst gehostete Live-Karte für ein OpenWrt-Mesh-Netzwerk (usteer):
zeigt auf einem Grundriss, an welchem Router jeder Client gerade hängt,
Roaming-Verlauf, Signalstärke und Kanalauslastung je Funkband – im Browser,
in Echtzeit. Keine Cloud, keine App, nur ein Python-Dienst, der die eigenen
Router per SSH abfragt.

Läuft als kleiner Python-3-Dienst (reine Standardbibliothek) – entweder auf
einem Raspberry Pi (z. B. neben openHAB, siehe
[`docs/deployment-raspbian-openhab.md`](docs/deployment-raspbian-openhab.md))
oder direkt auf OpenWrt. Alles Netzwerkspezifische (Router, IPs, SSIDs,
Kartenlayout, Schwellwerte) steckt in einer `config.json` – Dienst und
Webseite bleiben für jedes Mesh identisch gleich.

![Beispiel-Ansicht des Dashboards mit vier Routern, Clients, Roaming-Log und Kanalauslastung](docs/images/dashboard-beispiel.png)

*Beispielansicht mit frei erfundenen Testdaten (Router, Clients und Werte
aus `examples/config.example.json`) – keine echten Netzwerkdaten.*

## ⚠ Datenschutz-Hinweis (DSGVO): Dieses Tool erstellt ein personenbezogenes Bewegungsprofil

**Dieser Abschnitt ist kein Zubehör, sondern Voraussetzung für den Einsatz.**
Bitte vollständig lesen, bevor dieses Tool im eigenen Netzwerk installiert
wird – insbesondere, wenn im Netzwerk auch Geräte anderer Personen
(Familie, Mitbewohner, Mieter, Gäste, Besuch, ggf. Mitarbeitende) laufen.

### Was dieses Tool tatsächlich erfasst

Für jedes Gerät, das sich mit einem der überwachten Router verbindet,
zeichnet der Dienst laufend auf:

- an welchem Router/Access Point (und damit an welchem Ort/Raum, sofern
  die Router-Karte entsprechend eingerichtet ist) das Gerät aktuell
  verbunden ist,
- an welchen weiteren Access Points es zusätzlich empfangbar ist
  (inklusive Signalstärke – ein Näherungsmaß für die Entfernung),
- jeden Wechsel des Access Points samt Zeitpunkt (Connect-/Roam-/
  Disconnect-Ereignisse, zentral protokolliert in einer SQLite-Datenbank,
  die einen Dienst-Neustart überlebt),
- optional einen vom Betreiber vergebenen Klarnamen/Nickname pro Gerät,
  der die Zuordnung Gerät → Person ausdrücklich herstellt,
- aus den DHCP-Leases und der ARP-Tabelle der Router Hostname und IP-Adresse
  **aller** Geräte im Netz, auch kabelgebundener. Hostnamen enthalten oft
  schon einen Personennamen („Annas-iPhone“). Gespeichert werden sie nur für
  die Aufbewahrungsfrist; an die Weboberfläche gehen nur die Hostnamen der
  Geräte, die die Karte tatsächlich anzeigt, IP-Adressen gar nicht.

**Seit v22 ist das standardmäßig zeitlich begrenzt, nicht mehr
unbegrenzt:** Die Konfigurationsoption `privacy.retention_days` (Default:
7 Tage, per UCI/LuCI unter dem Reiter „Datenschutz" einstellbar) löscht
alle geräte­bezogenen Daten (MAC-Adresse, Name, IP, Nickname,
Roaming-Log-Einträge) eines Geräts automatisch und endgültig aus der
SQLite-Datenbank, sobald es so viele Tage nicht mehr beobachtet wurde –
nicht nur aus der Anzeige. Zusätzlich führt der Dienst (abschaltbar über
`privacy.anonymous_stats_enabled`) eine stündliche, **MAC-freie**
Zusammenfassung (Ereignisanzahl + Ø-Signalstärke je Router/Band) fort, die
unbegrenzt aufbewahrt wird. **Achtung:** In einem kleinen Haushalt ist diese
Statistik nicht zuverlässig anonym – wohnt dort nur eine Person, zeigt
„Connect um 23 Uhr am Router Schlafzimmer“ auch ohne MAC-Adresse, wann
diese Person wo war (siehe „Bekannte Grenzen“ unten). Über `POST /api/erase {"mac": "..."}` lässt sich
die Löschung für ein einzelnes Gerät jederzeit sofort auslösen (Art. 17
DSGVO), unabhängig von der Frist. Das ändert nichts an den folgenden
Abschnitten: **während der Aufbewahrungsfrist** entsteht weiterhin ein
personenbezogenes Bewegungsprofil, und die Rechtsgrundlage dafür (s. u.)
braucht es trotzdem.

### Warum das ein personenbezogenes Bewegungsprofil ist

WLAN-fähige Geräte (vor allem Smartphones) befinden sich im Alltag
praktisch ständig bei genau einer Person. Die Kombination aus "welches
Gerät ist wann an welchem Access Point/Ort", fortlaufend über die Zeit
gespeichert, ergibt damit faktisch ein Bewegungs- und Aufenthaltsprofil
der Person, der das Gerät gehört – unabhängig davon, ob ein Klarname
hinterlegt ist: Schon eine über die Zeit stabile Geräte-MAC-Adresse macht
eine Person im Sinne der DSGVO re-identifizierbar, ein hinterlegter
Nickname stellt diesen Bezug zusätzlich ausdrücklich her. Das Dashboard
ist technisch genau für diesen Zweck gebaut (Sichtbarmachen, wo sich
welches Gerät/welche Person im überwachten Bereich gerade aufhält und wie
es sich dort bewegt) – das ist kein Nebeneffekt, sondern die Kernfunktion.

Das betrifft nicht nur die Person, die das Tool installiert: **jede
Person, deren Gerät sich mit dem überwachten WLAN verbindet**, wird
erfasst – auch ohne eigenes Wissen oder eigene Zustimmung, sofern nicht
ausdrücklich dafür gesorgt wird. Das schließt Familienmitglieder,
Mitbewohner, Mieter separater Einheiten im selben Mesh, Gäste, Besuch und
– bei Einsatz außerhalb eines rein privaten Haushalts – auch Kunden oder
Mitarbeitende ein.

### Rechtliche Einordnung (Überblick, keine Rechtsberatung)

- Standort-/Bewegungsdaten einer identifizierbaren natürlichen Person sind
  personenbezogene Daten im Sinne von Art. 4 Nr. 1 DSGVO. Werden sie dazu
  verwendet, Aufenthalts- oder Bewegungsmuster einer Person zu analysieren
  oder vorherzusagen, kann das zusätzlich als Profiling nach Art. 4 Nr. 4
  DSGVO einzuordnen sein.
- Jede Verarbeitung braucht eine Rechtsgrundlage nach Art. 6 DSGVO. In
  einem gemeinsam genutzten Netzwerk mit mehreren Personen kommt dafür in
  der Praxis meist nur eine informierte Einwilligung aller betroffenen
  Personen in Betracht (Art. 6 Abs. 1 lit. a DSGVO) – ein überwiegendes
  berechtigtes Interesse des Betreibers (Art. 6 Abs. 1 lit. f DSGVO) wird
  bei einem derart detaillierten, dauerhaft gespeicherten Bewegungsprofil
  anderer Personen regelmäßig schwer zu begründen sein.
- Die sogenannte Haushaltsausnahme (Art. 2 Abs. 2 lit. c DSGVO) gilt nur
  für die Verarbeitung durch eine natürliche Person zu ausschließlich
  persönlichen oder familiären Zwecken – sie entfällt, sobald das Tool
  Personen außerhalb dieses engen Kreises erfasst (z. B. Mieter einer
  separaten Wohneinheit, Gäste, oder jeglicher Einsatz in einem
  geschäftlichen/beruflichen Kontext).
- Werden betroffene Personen informiert, greifen zusätzlich die
  Transparenzpflichten aus Art. 13/14 DSGVO (wer wird worüber informiert)
  sowie die Grundsätze der Datenminimierung und Speicherbegrenzung
  (Art. 5 DSGVO) und die Betroffenenrechte (u. a. Auskunft, Löschung,
  Art. 15/17 DSGVO).
- Bei Einsatz im Beschäftigungskontext sind zusätzlich § 26 BDSG und ggf.
  Mitbestimmungsrechte der Arbeitnehmervertretung zu prüfen.
- Eine heimliche, nicht offengelegte Standortüberwachung von Personen
  ohne deren Kenntnis (z. B. von Mietern oder Mitbewohnern) kann je nach
  Ausgestaltung und Rechtsordnung über das Datenschutzrecht hinaus auch
  strafrechtlich relevant sein.

### Praktische Empfehlungen (freiwillig, aber dringend angeraten)

- Alle Personen, deren Geräte das überwachte WLAN nutzen (könnten), vor
  Inbetriebnahme aktiv informieren und – wo möglich – deren Einwilligung
  einholen; keine heimliche Überwachung.
- Zugriff auf das Dashboard einschränken: Der Dienst hat **keine
  Anmeldung** (siehe „Bekannte Grenzen“). Den Port (Standard 8765) nur aus
  dem vertrauenswürdigen Netz erreichbar machen, z. B. `http.bind` bzw.
  UCI `bind` auf die LAN-IP setzen statt `0.0.0.0` und sicherstellen, dass
  Gast-WLAN/IoT-Netze per Firewall keinen Zugriff auf den Router bzw. Pi
  haben. Für mehr Schutz einen Reverse-Proxy mit Authentifizierung
  vorschalten.
- Speicherdauer aktiv begrenzen: `privacy.retention_days` (Default 7
  Tage) löscht geräte­bezogene Daten automatisch aus der SQLite-Datenbank,
  nicht nur aus der Anzeige – anders als `log_max_entries`, das weiterhin
  nur eine Anzahl-Sicherheitsgrenze ist, keine Zeitgrenze. Frist so kurz
  wie für den eigenen Zweck (z. B. Fehlersuche) nötig wählen.
- In kleinen Haushalten `privacy.anonymous_stats_enabled` abschalten, wenn
  keine Langzeit-Trends gebraucht werden.
- Bei aktivem MQTT auch die Aufbewahrung in openHAB/InfluxDB begrenzen
  (Retention Policy), denn dort landet die Client-Anzahl je Router
  dauerhaft – und damit, wer wann in welchem Raum war.
- Auf die Nickname/Umbenennen-Funktion verzichten, wenn eine
  ausdrückliche Re-Identifizierung von Personen vermieden werden soll.
- Betrieb auf den tatsächlich benötigten Personenkreis und Zeitraum
  beschränken statt dauerhaft alle Geräte zu erfassen.
- Bei jedem Einsatz außerhalb eines rein privaten, familiären Haushalts
  (siehe Haushaltsausnahme oben) vorab rechtlichen Rat (Datenschutz-
  beauftragte/r, Rechtsanwalt/Rechtsanwältin) einholen.

### Technische Schutzmaßnahmen (Stand 1.1)

- **Speicherbegrenzung:** geräte­bezogene Daten werden nach
  `privacy.retention_days` ohne Beobachtung aus der Datenbank gelöscht,
  einzelne Geräte sofort über `POST /api/erase`. SQLite läuft mit
  `secure_delete`, gelöschte Daten bleiben also nicht als Reste in der
  Datei stehen.
- **Dateirechte:** Datenbank, `config.json` (enthält ggf. das
  MQTT-Passwort), `known_hosts` und die MQTT-Optionsdatei sind nur für den
  Dienst lesbar (0600).
- **Keine Drittanbieter:** Die Weboberfläche lädt keine externen Schriften,
  Skripte oder CDNs – der Browser der Betrachter spricht nur mit dem
  Dienst selbst.
- **Datenminimierung in der Ausgabe:** `/data.json` enthält keine
  IP-Adressen und Hostnamen nur für Geräte, die auf der Karte erscheinen.
  `/config.json` und `/api/status` (Statusspalte in LuCI) enthalten keine
  Gerätedaten.
- **Schutz gegen fremde Webseiten (CSRF):** `POST /api/rename` und
  `/api/erase` nehmen nur Anfragen mit `Content-Type: application/json`
  und passender Herkunft an. Eine fremde Webseite, die jemand im Heimnetz
  aufruft, kann also keine Geräte umbenennen oder Daten löschen.
  Kommandozeile: `curl -H 'Content-Type: application/json' -d
  '{"mac":"aa:bb:cc:dd:ee:ff"}' http://<host>:8765/api/erase`.
- **MQTT:** übertragen werden nur Summen (Clients je Router, Länge des
  Ereignis-Logs), keine MAC-Adressen oder Namen. Zugangsdaten stehen nicht
  in der Prozessliste; TLS ist möglich und bei einem Broker außerhalb des
  Routers/Pis empfohlen.
- **Keine Zugriffsprotokolle:** Der Webserver protokolliert keine Aufrufe
  (keine IP-Adressen der Betrachter im Log).

### Bekannte Grenzen

- **Keine Anmeldung:** Wer den Port erreicht, sieht live, welches Gerät in
  welchem Raum ist, und kann Geräte umbenennen oder ihre Daten löschen.
  Schutz nur über Netzwerk/Firewall bzw. Reverse-Proxy (siehe oben).
- **Anonyme Statistik:** wird unbegrenzt aufbewahrt und ist in kleinen
  Haushalten auf einzelne Personen rückführbar.
- **Löschen eines verbundenen Geräts:** `POST /api/erase` löscht die
  gespeicherten Daten, ein weiterhin verbundenes Gerät wird beim nächsten
  Abruf aber wieder erfasst. Dauerhaft hilft nur, das Gerät aus dem
  überwachten WLAN zu nehmen.
- **Router-Zugang:** Der Dienst meldet sich per SSH als `root` mit einem
  Schlüssel an allen Routern an. Wer den Schlüssel hat, hat die Router –
  Datei nur für root lesbar halten (`chmod 600`).

**Dieser Abschnitt ersetzt keine Rechtsberatung.** Die tatsächliche
datenschutzrechtliche Bewertung hängt vom konkreten Einzelfall ab
(Einsatzkontext, betroffene Personen, anwendbares nationales Recht). Im
Zweifel vor dem Einsatz fachkundigen Rat einholen.

## Funktionsumfang

- Live-Karte mit Routern, Clients und Roaming-Pfeilen auf einem frei
  positionierbaren Grundriss (SVG, 900×600).
- Signalstärke-Radar je Client (Ringe bei konfigurierbaren dBm-Schwellen).
- Zentrales Ereignis-Log (Connect/Roam/Disconnect) in SQLite – konsistent
  für alle Betrachter, überlebt einen Dienst-Neustart.
- Detail-Panel je Client: Verlauf, aktuelle Verbindung, an welchen weiteren
  Routern das Gerät ebenfalls empfangbar ist.
- Kanalauslastung je Router/Funkband (eigene Nutzung / fremde Nutzung /
  ungenutzte Kapazität), aus `iw dev <ifname> survey dump`.
- Client-Punkte: voller Punkt = 5 GHz, Ring = 2,4 GHz.
- Clients lassen sich im UI umbenennen (Nickname), bleibt dauerhaft
  gespeichert.
- Optional: Zusammenfassungs-Metriken per MQTT (z. B. für InfluxDB/Grafana),
  wahlweise mit Benutzername/Passwort und TLS.
- Automatische Speicherbegrenzung (DSGVO): geräte­bezogene Daten verfallen
  nach `privacy.retention_days` (Default 7 Tage), eine MAC-freie
  Langzeit-Statistik bleibt für Trend-Analysen erhalten, Sofort-Löschung
  einzelner Geräte über `POST /api/erase`.

## Architektur

- `src/mesh_roaming_pi.py` – der Dienst: pollt alle Router per SSH (ein
  Hintergrund-Thread je Router), fasst die Ergebnisse zusammen und liefert
  per HTTP die Live-Seite sowie `/config.json`/`/data.json`.
- `src/mesh-lageplan-live.html` – die Live-Seite selbst. Enthält **keine**
  netzwerkspezifischen Daten, lädt alles vom Server.
- `examples/config.example.json` / `examples/config.template.json` –
  Beispiel- bzw. Platzhalter-Konfiguration als Startpunkt für die eigene
  `config.json`.
- `systemd/mesh-roaming.service` – systemd-Unit für den Dauerbetrieb auf
  Raspbian/Debian.
- `openwrt/mesh-roaming/` – OpenWrt-Paketquelle (procd-Init-Skript, UCI-
  Konfigurationsschema, UCI→JSON-Brücke `mesh-roaming-uci2json`) für den
  Betrieb direkt auf einem Mesh-Router statt auf einem separaten Pi.
- `openwrt/luci-app-mesh-roaming/` – optionales LuCI-Konfigurationsformular
  für das OpenWrt-Paket (Grundeinstellungen, Router, SSID-Farben).
- `openwrt/build-ipk.sh` – baut aus beiden Paketquellen installierbare
  `.ipk`-Dateien (ohne OpenWrt-SDK).

Voraussetzung auf den Routern: OpenWrt mit `usteer` und `hostapd`
(Standard bei den meisten aktuellen Mesh-Setups).

## Schnellstart (OpenWrt, direkt auf einem Mesh-Router)

**Wichtig – zuerst prüfen, welchen Paketmanager der Router hat**
(`opkg --version` bzw. `apk --version`): Seit OpenWrt 25.12 ist `apk`
(Alpine-Stil) auf vielen Targets der Standard statt `opkg` – ein anderes
Paketformat, nicht nur ein anderer Befehl. Ein `.ipk` lässt sich bei `apk`
grundsätzlich nicht installieren.

### Fertige Pakete (ohne selbst zu bauen)

Im Ordner [`packages/`](packages/) liegen fertig gebaute Pakete der
aktuellen Version (Architektur `all`, laufen auf jedem Target):

| Datei | für |
|---|---|
| `mesh-roaming_1.1-r1_all.apk` | Dienst, OpenWrt 25.12+ (`apk`) |
| `luci-app-mesh-roaming_1.1-r1_all.apk` | LuCI-Oberfläche, OpenWrt 25.12+ (`apk`) |
| `mesh-roaming_1.1-r1_all.ipk` | Dienst, OpenWrt bis 24.10 (`opkg`) |
| `luci-app-mesh-roaming_1.1-r1_all.ipk` | LuCI-Oberfläche, OpenWrt bis 24.10 (`opkg`) |

```sh
# auf dem PC: Pakete auf den Router kopieren (-O: Dropbear hat kein SFTP)
scp -O packages/*_1.1-r1_all.apk packages/SHA256SUMS root@<router-ip>:/tmp/

# auf dem Router (apk, OpenWrt 25.12+)
cd /tmp
grep apk SHA256SUMS | sha256sum -c -   # optional: Pakete unbeschädigt?
apk update
apk add --allow-untrusted ./mesh-roaming_1.1-r1_all.apk ./luci-app-mesh-roaming_1.1-r1_all.apk

# bzw. auf dem Router (opkg, bis OpenWrt 24.10)
opkg update
opkg install ./mesh-roaming_1.1-r1_all.ipk ./luci-app-mesh-roaming_1.1-r1_all.ipk
```

Abhängigkeiten (`python3`, `python3-sqlite3`, `openssh-client-utils`,
`luci-base`, `rpcd`) holt der Paketmanager selbst aus den
OpenWrt-Paketquellen, deshalb vorher `apk update` bzw. `opkg update`.
`--allow-untrusted` ist nötig, weil die Pakete nicht mit einem
OpenWrt-Schlüssel signiert sind. Die `.apk`-Dateien sind im Format APK v2
gebaut und auf OpenWrt 25.12.6 (x86/64) getestet; die `.ipk`-Dateien
wurden nicht gegen ein echtes `opkg` getestet. Danach in LuCI unter
*Dienste → Mesh Roaming* die Router eintragen.

### Selbst bauen

```sh
cd openwrt
./build-ipk.sh
# -> openwrt/dist/mesh-roaming_<version>_all.ipk
# -> openwrt/dist/luci-app-mesh-roaming_<version>_all.ipk   (optional, LuCI-Formular)

./build-apk.sh   # NUR bei apk-Routern: wandelt die .ipk-Dateien zusätzlich in .apk um
```

Danach per `scp`/`opkg install` (bzw. `apk add --allow-untrusted` für
`.apk`) auf den Router übertragen. Vollständige Anleitung (Paketmanager-
Erkennung, `.apk`-Umwandlung inkl. APK v2/v3, Konfiguration über LuCI oder
UCI, SSH-Schlüssel, Deinstallation):
[`docs/deployment-openwrt.md`](docs/deployment-openwrt.md).

## Schnellstart (Raspbian/Debian, z. B. neben openHAB)

Siehe [`docs/deployment-raspbian-openhab.md`](docs/deployment-raspbian-openhab.md)
für die vollständige Anleitung (Dienst-Nutzer, Konfiguration, SSH-Schlüssel,
systemd).

Kurzform zum lokalen Ausprobieren:

```sh
cp examples/config.example.json /tmp/config.json
# /tmp/config.json anpassen: eigene Router/IPs/SSIDs eintragen
MESH_ROAMING_CONFIG=/tmp/config.json python3 src/mesh_roaming_pi.py
```

Danach im Browser öffnen: **http://localhost:8765/** (bzw. bei echtem
Betrieb auf dem Pi: `http://<ip-oder-hostname-des-pi>:8765/` – der Port
8765 lässt sich in der `config.json` unter `http.port` ändern).

`openwrt/feed-makefiles/` enthält Vorlagen für eine mögliche spätere
Veröffentlichung im offiziellen `openwrt/packages`-Feed. Das ist noch nicht
umgesetzt – unter anderem, weil die aktuelle Lizenz (PolyForm Noncommercial,
siehe unten) mit den Lizenzanforderungen des offiziellen Feeds vermutlich
nicht vereinbar ist, da dieser auch in kommerziellen Firmware-Images
mitverteilt wird.

## Lizenz

[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0) –
siehe [`LICENSE`](LICENSE). Private, wissenschaftliche, gemeinnützige und
sonstige nicht-kommerzielle Nutzung, Veränderung und Weitergabe sind damit
frei möglich. **Kommerzielle Lizenzen auf Anfrage.**
