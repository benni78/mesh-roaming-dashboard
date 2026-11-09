# Einrichtung auf OpenWrt (direkt auf einem Mesh-Router)

> **⚠ Vor der Installation lesen:** Dieses Tool erfasst und speichert
> dauerhaft, welches Gerät sich wann mit welchem Router verbindet (inkl.
> Roaming-Verlauf) – das kann ein personenbezogenes Bewegungsprofil der
> Nutzer dieses Netzwerks darstellen. Betrieb nur unter Beachtung
> geltender Datenschutzvorschriften (insb. DSGVO) zulässig. Ausführliche
> Erklärung: [`README.md`, Abschnitt „Datenschutz-Hinweis
> (DSGVO)"](../README.md).

Dieselbe Live-Karte wie in der
[Raspbian/Debian-Variante](deployment-raspbian-openhab.md), aber als
OpenWrt-Paket: läuft direkt auf einem der Mesh-Router statt auf einem
separaten Pi, inklusive optionaler LuCI-Oberfläche zur Konfiguration.

## Enthaltene Pakete

- **`mesh-roaming`** – der Dienst selbst (identischer Python-Code wie die
  Raspbian-Variante) plus procd-Init-Skript. Funktioniert eigenständig mit
  einer von Hand gepflegten `/etc/mesh-roaming/config.json` – **kein**
  UCI/LuCI nötig.
- **`luci-app-mesh-roaming`** – optionale LuCI-Oberfläche: Grundeinstellungen,
  Router (anlegen/bearbeiten/entfernen) und SSID-Farben als Formular statt
  JSON-Datei. Setzt `mesh-roaming` voraus.

Beide Pakete liegen als Quelle unter [`openwrt/`](../openwrt) und werden mit
[`openwrt/build-ipk.sh`](../openwrt/build-ipk.sh) zu `.ipk`-Dateien gebaut
(ohne OpenWrt-SDK, nur mit `tar`/`gzip`). Für Router mit `apk` statt `opkg`
(Standard seit OpenWrt 25.12, s. Schritt 0/1b unten) wandelt zusätzlich
[`openwrt/build-apk.sh`](../openwrt/build-apk.sh) diese `.ipk`-Dateien in
das dafür nötige `.apk`-Format um. Fertige Dateien liegen nach dem Bauen in
`openwrt/dist/`.

**Wichtiger Hinweis zu den Python-Abhängigkeiten:** `mesh_roaming_pi.py`
nutzt ausschließlich die Python-3-Standardbibliothek (u. a. `sqlite3`,
`http.server`; SSH läuft extern über den Systembefehl `ssh`). Welche
Python-Pakete auf OpenWrt tatsächlich als eigene `opkg`-Pakete vorliegen,
unterscheidet sich je nach Zielplattform und OpenWrt-Release – z. B.
`python3` als Gesamtpaket auf manchen Targets, `python3-light` plus
einzelne Module wie `python3-sqlite3` auf anderen, knapperen Targets. Die
`control`-Datei von `mesh-roaming` setzt auf `python3, python3-sqlite3,
openssh-client-utils`; falls das Ziel-Target diese Paketnamen nicht genau so
kennt, vor der Installation mit `opkg list | grep python3` auf dem Router
nachschauen und ggf. die passenden Teilpakete von Hand nachinstallieren.
Auf sehr flashknappen Geräten (wenig freier Speicher) kann das insgesamt
mehrere MB zusätzlich belegen – vorher mit `df` prüfen.

## 0. Welchen Paketmanager hat der Router – `opkg` oder `apk`?

**Das zuerst klären, nicht raten.** Seit OpenWrt 25.12 ist auf vielen
Targets `apk` (Alpine-Stil) der Standard-Paketmanager statt `opkg` – und
das ist nicht nur ein anderer Befehl, sondern ein **komplett anderes
Paketformat**. Ein `.ipk` lässt sich bei `apk` grundsätzlich nicht
installieren, selbst wenn es völlig korrekt gebaut ist – `apk add`/
`apk install` bricht dann mit `file format is invalid or inconsistent` ab.
Auf dem Router prüfen:

```sh
opkg --version    # vorhanden -> opkg-Router, weiter mit Schritt 1
apk --version     # vorhanden -> apk-Router, weiter mit Schritt 1 UND 1b
```

## 1. `.ipk`-Dateien bauen

Auf einem gewöhnlichen Linux-Rechner ausführen (eigener PC/Laptop, VM,
WSL) oder hier im Repository:

```sh
cd openwrt
./build-ipk.sh
# -> openwrt/dist/mesh-roaming_<version>_all.ipk
# -> openwrt/dist/luci-app-mesh-roaming_<version>_all.ipk
```

Ein `.ipk` ist dabei **kein** `ar`-Archiv (anders als ein Debian-`.deb`,
dem es oberflächlich ähnelt), sondern ein einzelner gzip-komprimierter
tar-Stream mit `./debian-binary`, `./data.tar.gz` und `./control.tar.gz`
darin – exakt das Format und die Reihenfolge aus OpenWrts eigenem
`ipkg-build`-Skript. `build-ipk.sh` baut es so; für reinen `opkg`-Betrieb
reicht das bereits.

### 1b. Nur für `apk`-Router: zusätzlich nach `.apk` umwandeln

Ein für `opkg` korrektes `.ipk` ist für `apk` trotzdem das falsche Format
– es muss zusätzlich in APK v2 und (meist) APK v3 umgewandelt werden.
`build-apk.sh` erledigt das:

```sh
./build-apk.sh
# -> openwrt/dist/mesh-roaming_<version>_all.apk        (APK v2 oder v3,
# -> openwrt/dist/luci-app-mesh-roaming_<version>_all.apk je nach dem, ob
#                                                           apk-tools >= 3.0
#                                                           lokal verfügbar ist)
```

Ist auf dem Build-Rechner kein `apk` mit `apk mkpkg` (apk-tools ≥ 3.0)
installiert – üblich, da das kein Standardpaket vieler Linux-Distributionen
ist –, baut das Skript nur die APK-v2-Zwischenstufe und gibt am Ende genau
die Befehle aus, um den letzten Schritt (v2 → v3) nachzuholen.

**Kein Docker nötig:** apk-tools ≥ 3.0 ist ein ganz normales Meson/C-Projekt
und baut direkt auf jeder gängigen Linux-Distribution (Ubuntu, Debian,
Fedora, …) – auch ohne OpenWrt-Buildsystem/SDK:

```sh
sudo apt install -y git meson ninja-build pkg-config liblua5.3-dev \
                     libssl-dev libzstd-dev
git clone https://gitlab.alpinelinux.org/alpine/apk-tools.git
cd apk-tools
meson setup build
meson compile -C build
```

Danach den frisch gebauten Binary vor den `build-apk.sh`-Aufruf stellen –
das Skript findet `apk mkpkg` dann automatisch und baut gleich bis APK v3:

```sh
PATH="$PWD/apk-tools/build/src:$PATH" ./openwrt/build-apk.sh
```

(Wer bereits ein volles OpenWrt-Buildsystem/SDK ausgecheckt hat: apk-tools
*innerhalb* dieses Buildroots als Host-Tool zu bauen ist laut
OpenWrt-Forum eher fehleranfällig, u. a. wegen Lua-Versionskonflikten
zwischen `lua5.1`/`lua5.3` je nach Branch – der obige direkte Weg gegen
den Upstream-Quellcode ist einfacher und vom OpenWrt-Checkout unabhängig.)

Alternativ, falls auf dem eigenen Rechner aus anderen Gründen kein
Compiler/Meson installiert werden soll, geht es auch kurz über einen
Alpine-Edge-Container (enthält apk-tools 3.0+ bereits fertig gebaut):

```sh
docker run --rm -v "$PWD":/w -w /w alpine:edge sh -c '
  apk add --no-cache apk-tools bash util-linux gzip tar coreutils findutils fakeroot &&
  fakeroot openwrt/tools/openwrt-ipk2apk/convert-apk-v2-to-v3.sh openwrt/dist/*.apk
'
```

**Ob der eigene Router APK v2 oder v3 braucht, lässt sich nicht pauschal
vorhersagen** – am günstigsten einfach erst die (billigere) v2-Datei
ausprobieren (Schritt 2); kommt dieselbe Fehlermeldung wie beim `.ipk`,
fehlt der v3-Schritt.

Die beiden Umwandlungswerkzeuge (`openwrt-ipk2apk.py`, reines Python,
keine Zusatzpakete; `convert-apk-v2-to-v3.sh`, braucht `apk-tools` ≥ 3.0)
liegen unter [`openwrt/tools/openwrt-ipk2apk/`](../openwrt/tools/openwrt-ipk2apk)
– unverändert übernommen vom MIT-lizenzierten Projekt
[rychly/openwrt-ipk2apk](https://github.com/rychly/openwrt-ipk2apk)
(siehe `README-vendored.md` dort für Details/Herkunft). Diese beiden
Dateien stehen unter der MIT-Lizenz, nicht unter der PolyForm-Lizenz
dieses Repositories.

## 2. Auf den Router übertragen und installieren

**Bei `opkg`:**

```sh
scp openwrt/dist/mesh-roaming_*_all.ipk root@<router-ip>:/tmp/
scp openwrt/dist/luci-app-mesh-roaming_*_all.ipk root@<router-ip>:/tmp/   # optional

ssh root@<router-ip>
opkg update
opkg install /tmp/mesh-roaming_*_all.ipk
opkg install /tmp/luci-app-mesh-roaming_*_all.ipk   # optional, für die LuCI-Oberfläche
```

**Bei `apk`** (siehe Schritt 1b):

```sh
scp openwrt/dist/mesh-roaming_*_all.apk root@<router-ip>:/tmp/
scp openwrt/dist/luci-app-mesh-roaming_*_all.apk root@<router-ip>:/tmp/   # optional

ssh root@<router-ip>
apk add --allow-untrusted /tmp/mesh-roaming_*_all.apk
apk add --allow-untrusted /tmp/luci-app-mesh-roaming_*_all.apk   # optional
```

`--allow-untrusted` ist nötig, weil das Paket nicht mit einem auf dem
Router hinterlegten Schlüssel signiert ist (es kommt ja nicht aus einem
offiziellen Feed). Schlägt der Befehl mit `file format is invalid or
inconsistent` fehl, war die installierte `.apk`-Datei noch APK v2 statt
v3 – Schritt 1b (v2→v3-Umwandlung) nachholen.

`mesh-roaming` wird dabei automatisch aktiviert und gestartet (`postinst`
ruft `/etc/init.d/mesh-roaming enable && start` auf).

## 3. Konfiguration

Zwei gleichwertige Wege – je nachdem, ob `luci-app-mesh-roaming` installiert
ist:

### a) Über LuCI (wenn installiert)

*Dienste → Mesh Roaming Dashboard* in der LuCI-Oberfläche:

- **Grundeinstellungen** – Bind-Adresse/Port, SSH-Zugangsdaten, Schwellwerte,
  Kartenlayout, Standard-SSID-Farbreihenfolge, MQTT (optional, siehe unten).
- **Router** – Liste aller Router (eine „Instanz“ je Router, Aufbau wie
  *VPN → OpenVPN*): Name, Raum, IP-Adresse, die Flags „Dieser Router“
  (nur bei einem Router möglich) und „Deaktiviert“ direkt in der Liste
  umschaltbar, dazu der aktuelle Status aus dem laufenden Dienst. Neue
  Router über das Namensfeld unter der Liste + „Hinzufügen“; alles Weitere
  über „Bearbeiten“: `ID` (wird aus dem Namen vorgeschlagen, nach dem
  Speichern nicht mehr änderbar), Position horizontal/vertikal auf der Karte
  (erlaubter Bereich = Kartengröße aus den Grundeinstellungen, Standard
  900 × 600 px, 0/0 = oben links), optional Mesh-Management-IPs (siehe
  unten).

Die **Mesh-Management-IPs** dienen nur der Anzeige „zwischen Stationen“:
usteer meldet je Client, welche anderen Router ihn ebenfalls empfangen, und
benennt deren Interfaces `<IP>#hostapd.<ifname>`. Über die IP vor dem `#`
ordnet die Karte den Eintrag einem Router zu. Ohne Eintrag wird dafür die
normale IP-Adresse des Routers verwendet – das Feld ist also nur nötig, wenn
usteer über ein anderes Netz (z. B. ein eigenes Management-VLAN) läuft. Die
richtige IP zeigt `ubus call usteer remote_info` auf einem anderen Router.
Ohne WLAN und usteer (z. B. in einer VM) bleibt diese Anzeige leer.
- **SSID-Farben** – optional feste Farbe je SSID-Name statt automatischer
  Zuweisung.

Nach dem Speichern & Anwenden übersetzt `/usr/libexec/mesh-roaming-uci2json`
die UCI-Konfiguration (`/etc/config/mesh-roaming`) automatisch in die
`config.json`, die der Dienst tatsächlich liest; der Dienst wird dabei neu
geladen.

#### MQTT (optional)

Im Tab *MQTT* der Grundeinstellungen (UCI-Optionen in `config global 'main'`):

| UCI-Option | Bedeutung |
| --- | --- |
| `mqtt_broker` | Hostname/IP des Brokers – leer = MQTT aus |
| `mqtt_port` | leer = Standardport (1883, mit TLS 8883) |
| `mqtt_base_topic`, `mqtt_publish_interval_sec` | Basis-Topic, Intervall in Sekunden |
| `mqtt_username`, `mqtt_password` | optional; leer = anonyme Verbindung |
| `mqtt_tls` | `1` = verschlüsselt über TLS |
| `mqtt_tls_cafile` | optional: CA-Datei (PEM) für selbst signierte Zertifikate; leer = System-Zertifikate aus `/etc/ssl/certs` |
| `mqtt_tls_insecure` | `1` = Hostnamen im Zertifikat nicht prüfen (nur zum Testen) |

Veröffentlicht wird über `mosquitto_pub`, das nicht automatisch mitinstalliert
wird: `apk add mosquitto-client-ssl` (bzw. `opkg install
mosquitto-client-ssl`; die `-nossl`-Variante reicht nur ohne TLS). Für TLS
ohne eigene CA-Datei zusätzlich `ca-certificates`.

Zum Passwort: Es steht im Klartext in `/etc/config/mesh-roaming` (wie bei
allen OpenWrt-Diensten) und in der daraus erzeugten `config.json`, die nur
für root lesbar geschrieben wird (`0600`). An `mosquitto_pub` wird es nicht
als Argument übergeben (wäre sonst in `ps` sichtbar), sondern über eine
Optionsdatei im Laufzeitverzeichnis (`<runtime_dir>/mqtt/mosquitto_pub`,
ebenfalls `0600`). Ohne TLS geht es unverschlüsselt über das Netz.
Verbindungsfehler (z. B. „not authorised“) erscheinen höchstens einmal pro
Minute in `logread`.

### b) Von Hand (ohne LuCI)

Entweder direkt UCI editieren:

```sh
uci set mesh-roaming.main.port='8765'
uci set mesh-roaming.r1=router
uci set mesh-roaming.r1.id='router-wohnzimmer'
uci set mesh-roaming.r1.name='Wohnzimmer'
uci set mesh-roaming.r1.ip='192.168.1.2'
uci commit mesh-roaming
/etc/init.d/mesh-roaming reload
```

Oder eine `config.json` nach dem Format aus
[`examples/config.example.json`](../examples/config.example.json) direkt
unter `/etc/mesh-roaming/config.json` ablegen (solange `/etc/config/mesh-roaming`
keine `config global`-Sektion enthält, lässt der Init-Dienst diese Datei
unangetastet).

## 4. SSH-Schlüssel zu den übrigen Routern

Genau wie in der [Raspbian-Variante](deployment-raspbian-openhab.md#4-ssh-schlüssel):

```sh
ssh-keygen -t ed25519 -f /etc/mesh-roaming/id_ed25519 -N ""
```

Den öffentlichen Schlüssel (`id_ed25519.pub`) auf **jedem weiteren** Router
an `/etc/dropbear/authorized_keys` **anhängen** (nicht überschreiben). Der
Router, auf dem `mesh-roaming` selbst läuft, braucht sich nicht per SSH
selbst zu erreichen – dafür ist der Router-Eintrag mit `local` markiert
(LuCI: Flag „Dieser Router"; UCI: `option local '1'`).

## 5. Aufrufen

**`http://<router-ip>:8765/`**

Port `8765` ist der Default (`option port` in UCI bzw. `http.port` in
`config.json`) und lässt sich dort ändern.

## 6. Deinstallation

```sh
opkg remove luci-app-mesh-roaming   # falls installiert
opkg remove mesh-roaming
```

`prerm` stoppt und deaktiviert den Dienst automatisch vor der Entfernung.
Die UCI-Konfiguration (`/etc/config/mesh-roaming`) ist als `conffile`
deklariert und bleibt bei einem Upgrade erhalten.
