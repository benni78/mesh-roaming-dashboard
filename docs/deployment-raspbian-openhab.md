# Einrichtung auf Raspbian/Debian (z. B. neben openHAB)

> **⚠ Vor der Installation lesen:** Dieses Tool erfasst und speichert
> dauerhaft, welches Gerät sich wann mit welchem Router verbindet (inkl.
> Roaming-Verlauf) – das kann ein personenbezogenes Bewegungsprofil der
> Nutzer dieses Netzwerks darstellen. Betrieb nur unter Beachtung
> geltender Datenschutzvorschriften (insb. DSGVO) zulässig. Ausführliche
> Erklärung: [`README.md`, Abschnitt „Datenschutz-Hinweis
> (DSGVO)"](../README.md).

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
- `LICENSE` und `THIRD-PARTY-NOTICES.md` (im Hauptordner) – Lizenz und
  Hinweise zu genutzter Software Dritter. Gehören bei jeder Installation
  und Weitergabe dazu.

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

Programm, Live-Seite, Lizenz und Hinweise nach `/opt/mesh-roaming/` kopieren
(aus dem Hauptordner des Projekts):

```sh
sudo cp src/mesh_roaming_pi.py src/mesh-lageplan-live.html \
        LICENSE THIRD-PARTY-NOTICES.md /opt/mesh-roaming/
python3 /opt/mesh-roaming/mesh_roaming_pi.py --version
```

Die letzte Zeile zeigt die installierte Version, z. B.
`mesh_roaming_pi.py (mesh-roaming-dashboard) 1.2`.

## 3. Konfiguration

`examples/config.template.json` (oder `config.example.json` als Vorlage)
nach `/etc/mesh-roaming/config.json` kopieren und ausfüllen:

- `network.label` – Anzeigename dieses Netzwerks (erscheint im Seitenkopf).
- `routers` – ein Eintrag je Router: `id` (frei wählbar, z. B. `router-1`),
  `ip` (Client-LAN-IP, über die der Pi die Router erreicht), `name`
  (**Überschrift** auf der Karte/in allen Listen), `room` (Ort, wird nur
  als Untertitel angezeigt), `map_x`/`map_y` (Position auf der
  900×600-Karte, grob nach echtem Grundriss verteilen), `mgmt_ips` (IPs, unter
  denen andere Router diesen Router im usteer-Netz sehen – Teil vor dem `#`
  in `ubus call usteer remote_info`; nur nötig, wenn das nicht schon `ip`
  ist, sonst leeres Array lassen). Optional `role`: `"ap"` (Standard) oder
  `"sensor"` für einen **Messpunkt** – einen Router, der nur als WLAN-Client
  im Netz hängt und nur die Kanalauslastung seiner Funkkarten misst (siehe
  README, Abschnitt „Kanalauslastung“).
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

Bei einem Fehler in der `config.json` (z. B. keine Router eingetragen)
beendet sich der Dienst sofort. systemd versucht es fünfmal innerhalb von
2 Minuten und gibt dann auf (`systemctl status mesh-roaming` zeigt `failed`,
die Ursache steht im Journal). Nach dem Korrigieren der Konfiguration:

```sh
sudo systemctl reset-failed mesh-roaming
sudo systemctl restart mesh-roaming
```

## 6. Aufrufen

Von jedem Gerät im eigenen Netz im Browser öffnen:

**`http://<pi-ip-oder-hostname>:8765/`**

`<pi-ip-oder-hostname>` durch die tatsächliche IP-Adresse oder den
Hostnamen des Pi ersetzen (z. B. `http://192.168.1.50:8765/` oder
`http://raspberrypi.local:8765/`). Der Port `8765` ist der Default aus
`http.port` in der `config.json` und kann dort bei Bedarf geändert werden –
dann entsprechend anpassen.

## 7. Aktualisieren

Bei jeder neuen Version dieselben Dateien wie in Schritt 2 ersetzen, die Unit
übernehmen und den Dienst neu starten:

```sh
sudo cp src/mesh_roaming_pi.py src/mesh-lageplan-live.html \
        LICENSE THIRD-PARTY-NOTICES.md /opt/mesh-roaming/
sudo cp systemd/mesh-roaming.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart mesh-roaming
python3 /opt/mesh-roaming/mesh_roaming_pi.py --version
```

Die Version steht auch rechts oben auf der Live-Seite. Zeigt sie zusätzlich
„Dienst x.y“, laufen Seite und Dienst in verschiedenen Ständen, meist weil
der Neustart fehlt. Änderungen je Version: [`CHANGELOG.md`](../CHANGELOG.md).

## Was die Seite automatisch mitbringt

- Live-Karte mit Roaming-Pfeilen, Signalstärke-Radar, Detail-Panel je Client.
- Zentrales Ereignis-Log (Connect/Roam/Disconnect) in SQLite auf dem Pi –
  konsistent für alle Betrachter, überlebt einen Dienst-Neustart.
- Kanalauslastung je Router und Funkkarte, neu berechnet als gleitende
  10-Sekunden-Differenz aus `iw dev <ifname> survey dump`. Treiber mit
  `channel BSS receive time` (z. B. mt76) zeigen eigenes/fremdes Netz,
  ältere wie ath9k Senden/Empfang/Störung/frei; je Band steht, was der
  Treiber kann. Dazu der eigene Verkehr über die verbundenen Geräte,
  Rauschen (und bei Messpunkten Signal/SNR) mit Bewertung gut/mittel/
  schlecht. Funktioniert auch mit Client-Interfaces (Messpunkte).
- Nachbarkanäle aus dem WLAN-Scan der Router: je ein Diagramm für 2,4 und
  5 GHz mit Spektrum (Netznamen über ihrer belegten Bandbreite),
  eigener/fremder Belegung und Kanalempfehlung (Einstellungen in
  der `config.json` unter `scan`, siehe README).
- Mit MQTT zusätzlich die Auslastungswerte je Router und Band, z. B. für
  openHAB → InfluxDB → Grafana (Topics: README, Abschnitt „MQTT-Topics“).
- Client-Punkte: voller Punkt = 5 GHz, Ring = 2,4 GHz.

## Für ein weiteres Netz

Dieselben Dateien, eigene `config.json` unter einem anderen Pfad, eigener
SSH-Schlüssel, eigene systemd-Unit mit angepasstem `MESH_ROAMING_CONFIG` und
ggf. anderem `http.port` – Skript und HTML-Datei bleiben unverändert.
