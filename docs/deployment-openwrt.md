# Einrichtung auf OpenWrt (direkt auf einem Mesh-Router)

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
(ohne OpenWrt-SDK, nur mit `ar`/`tar`/`gzip` – siehe Kommentar im Skript).
Fertige `.ipk`-Dateien liegen nach dem Bauen in `openwrt/dist/`.

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

## 1. `.ipk`-Dateien bauen

```sh
cd openwrt
./build-ipk.sh
# -> openwrt/dist/mesh-roaming_<version>_all.ipk
# -> openwrt/dist/luci-app-mesh-roaming_<version>_all.ipk
```

## 2. Auf den Router übertragen und installieren

```sh
scp openwrt/dist/mesh-roaming_*_all.ipk root@<router-ip>:/tmp/
scp openwrt/dist/luci-app-mesh-roaming_*_all.ipk root@<router-ip>:/tmp/   # optional

ssh root@<router-ip>
opkg update
opkg install /tmp/mesh-roaming_*_all.ipk
opkg install /tmp/luci-app-mesh-roaming_*_all.ipk   # optional, für die LuCI-Oberfläche
```

`mesh-roaming` wird dabei automatisch aktiviert und gestartet (`postinst`
ruft `/etc/init.d/mesh-roaming enable && start` auf).

## 3. Konfiguration

Zwei gleichwertige Wege – je nachdem, ob `luci-app-mesh-roaming` installiert
ist:

### a) Über LuCI (wenn installiert)

*Dienste → Mesh Roaming Dashboard* in der LuCI-Oberfläche:

- **Grundeinstellungen** – Bind-Adresse/Port, SSH-Zugangsdaten, Schwellwerte,
  Kartenlayout, Standard-SSID-Farbreihenfolge, MQTT (optional).
- **Router** – pro Router: `ID` (frei wählbar, z. B. `router-wohnzimmer`,
  danach nicht mehr ändern), `Name` (Überschrift auf der Karte), `Raum`
  (kleiner Untertitel), `IP-Adresse`, Kartenposition, optional
  Mesh-Management-IPs, Flags „Dieser Router" und „Deaktiviert".
- **SSID-Farben** – optional feste Farbe je SSID-Name statt automatischer
  Zuweisung.

Nach dem Speichern & Anwenden übersetzt `/usr/libexec/mesh-roaming-uci2json`
die UCI-Konfiguration (`/etc/config/mesh-roaming`) automatisch in die
`config.json`, die der Dienst tatsächlich liest; der Dienst wird dabei neu
geladen.

**Hinweis:** Die LuCI-Formulare wurden in dieser Umgebung nicht gegen eine
echte LuCI-Laufzeitumgebung getestet (hier steht kein OpenWrt/LuCI zur
Verfügung) – JSON-Syntax und UCI-Parsing sind geprüft, das tatsächliche
Rendering in LuCI aber nicht. Nach der Installation einmal durchklicken und
bei Auffälligkeiten ein Issue im Repository melden.

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
