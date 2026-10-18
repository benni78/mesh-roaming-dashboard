# Einrichtung auf Raspbian/Debian (z. B. neben openHAB)

Live-Karte aller Mesh-Router mit Roaming-Verfolgung, Ereignis-Log und
Kanalauslastung – als eigener systemd-Dienst auf einem Raspberry Pi mit
Raspbian/Debian (läuft problemlos neben openHAB auf demselben Gerät).

## Enthaltene Dateien

- `src/mesh_roaming_pi.py` – der Dienst selbst (reine Python-3-
  Standardbibliothek, keine Zusatzpakete nötig).
- `src/mesh-lageplan-live.html` – die Live-Seite. Enthält **keine**
  netzwerkspezifischen Daten, lädt alles aus `/config.json`/`/data.json`.
- `examples/config.example.json` – Beispielkonfiguration mit fiktiven
  Werten zum Nachvollziehen des Formats.
- `examples/config.template.json` – Vorlage mit Platzhaltern in spitzen
  Klammern (`<...>`), die vor dem Start ersetzt werden müssen.
- `systemd/mesh-roaming.service` – systemd-Unit für den Dauerbetrieb.

## 1. Voraussetzungen auf dem Pi

```sh
sudo apt update
sudo apt install -y python3 openssh-client
```

(Auf Raspbian/Debian ist das normalerweise schon vorhanden.)

## 2. Dienst-Nutzer und Verzeichnisse

```sh
sudo useradd --system --home /opt/mesh-roaming --shell /usr/sbin/nologin mesh-roaming
sudo mkdir -p /opt/mesh-roaming /etc/mesh-roaming
sudo chown mesh-roaming:mesh-roaming /opt/mesh-roaming /etc/mesh-roaming
```

`src/mesh_roaming_pi.py` und `src/mesh-lageplan-live.html` nach
`/opt/mesh-roaming/` kopieren.

## 3. Konfiguration

`examples/config.template.json` (oder `config.example.json` als Vorlage)
nach `/etc/mesh-roaming/config.json` kopieren und ausfüllen:

- `network.label` – Anzeigename dieses Netzwerks (erscheint im Seitenkopf).
- `routers` – ein Eintrag je Router: `id` (frei wählbar, z. B. `router-1`),
  `ip` (Client-LAN-IP, über die der Pi die Router erreicht), `name`
  (**Überschrift** auf der Karte/in allen Listen), `room` (Ort, wird nur
  als Untertitel angezeigt), `map_x`/`map_y` (Position auf der
  900×600-Karte, grob nach echtem Grundriss verteilen), `mgmt_ips` (nur
  nötig, wenn die Router sich per usteer/batman gegenseitig sehen und das
  auf der Karte sichtbar sein soll – sonst leeres Array lassen).
- `ap_ifnames` – Vorlage geht vom bekannten OpenWrt-Schema `phy0-ap0..3`/
  `phy1-ap0..3` aus. Auf einem der Router per `ubus list | grep hostapd`
  gegenprüfen, falls das eigene Netz ein anderes Chipsatz-/Namensschema hat.
- `map.ssid_colors_by_name` – optional: feste Farbe je SSID-Name (sonst
  bekommt jede SSID automatisch eine Farbe nach Entdeckungsreihenfolge).

Alles andere (Schwellwerte, Kanalauslastung-Intervall/-Farben, Ports, Pfade)
hat sinnvolle Defaults und muss nur bei Bedarf angepasst werden.

**Namenskonvention:** Überall, wo ein Router benannt wird, ist `name` die
Überschrift und `room` nur ein kleiner Untertitel darunter – nicht
umgekehrt.

## 4. SSH-Schlüssel

```sh
sudo -u mesh-roaming ssh-keygen -t ed25519 -f /etc/mesh-roaming/id_ed25519 -N ""
```

Den öffentlichen Schlüssel (`id_ed25519.pub`) auf **jedem** Router an
`/etc/dropbear/authorized_keys` (OpenWrt/Dropbear) bzw.
`~/.ssh/authorized_keys` (OpenSSH) **anhängen** – nicht überschreiben,
falls dort schon andere Schlüssel stehen.

## 5. Dienst installieren und starten

```sh
sudo cp systemd/mesh-roaming.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mesh-roaming
```

Log im laufenden Betrieb: `journalctl -u mesh-roaming -f`

## 6. Aufrufen

`http://<pi-ip>:8765/` von jedem Gerät im eigenen Netz.

## Was die Seite automatisch mitbringt

- Live-Karte mit Roaming-Pfeilen, Signalstärke-Radar, Detail-Panel je Client.
- Zentrales Ereignis-Log (Connect/Roam/Disconnect) in SQLite auf dem Pi –
  konsistent für alle Betrachter, überlebt einen Dienst-Neustart.
- Kanalauslastung je Router/Band (eigene/fremde Nutzung/Rest), neu berechnet
  als gleitende 10-Sekunden-Differenz aus `iw dev <ifname> survey dump` –
  funktioniert automatisch, sobald die Router das unterstützen (ältere
  Chipsätze liefern ggf. kein `channel BSS receive time`; die Anzeige zeigt
  dafür sauber „nicht verfügbar" statt falscher Werte).
- Client-Punkte: voller Punkt = 5 GHz, Ring = 2,4 GHz.

## Für ein weiteres Netz

Dieselben Dateien, eigene `config.json` unter einem anderen Pfad, eigener
SSH-Schlüssel, eigene systemd-Unit mit angepasstem `MESH_ROAMING_CONFIG` und
ggf. anderem `http.port` – Skript und HTML-Datei bleiben unverändert.
