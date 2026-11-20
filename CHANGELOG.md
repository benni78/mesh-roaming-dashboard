# Änderungen / Changelog

## Mesh Roaming Dashboard

### 1.3 (Pakete 1.3-r1)

- **Messpunkte** (Issue #5): Router mit der Rolle „Messpunkt“
  (`"role": "sensor"`, LuCI: Router → Rolle) messen nur die Kanalauslastung
  ihrer Funkkarten, z. B. ein Router, der nur als WLAN-Client im Netz hängt.
  Von ihnen werden keine Client-Listen, DHCP-Leases oder ARP-Tabellen
  abgefragt. Auf der Karte erscheinen sie als Raute ohne Signal-Ringe.
- Kanalauslastung je Funkkarte statt je AP-Interface: Der Dienst wählt auf
  jedem Router selbst ein Interface je Funkkarte (AP, Client, Mesh oder
  Monitor). Das Band ergibt sich aus der Frequenz.
- Treiber ohne `channel BSS receive time` (z. B. ath9k: AR9340, AR9580)
  zeigen jetzt Senden/Empfang/Störung/frei statt „nicht verfügbar“.
- Zu jedem Band werden Kanal, Gesamtbelegung und Rauschen angezeigt, bei
  Client-Interfaces auch das verbundene WLAN. Nach einem Kanalwechsel
  beginnt die Messung neu, statt über zwei Kanäle zu mitteln.
- MQTT: Auslastung je Router und Band unter
  `<base>/<router>/util/<band>/…` (busy, own/foreign bzw. rx/tx/other,
  free, noise, channel). Siehe README, Abschnitt „MQTT-Topics“.
- Raspberry Pi: `"role"` in der `config.json`; zum Übernehmen die Dateien
  wie unter „Aktualisieren“ in der Pi-Anleitung ersetzen.

### 1.2 (Pakete 1.2-r3)

- OpenWrt 23.05 (opkg): Bei der Installation erscheint nicht mehr
  `Command failed: ubus call service delete … (Not found)`. Die Meldung war
  harmlos: `postinst`/`prerm` haben einen noch nicht registrierten Dienst
  gestoppt.
- Ohne eingetragene Router startet der Dienst nicht mehr. Bisher hat er
  sich sofort beendet, procd hat ihn alle 5 Sekunden neu gestartet und
  jedes Mal einen Fehler ins Log geschrieben. Jetzt steht einmal
  „Keine Router konfiguriert“ im Log; nach dem Speichern in LuCI startet
  der Dienst.
- `.ipk`-Pakete auf OpenWrt 23.05.6 getestet (Erstinstallation, Upgrade
  von 1.2-r2, Neuinstallation, Deinstallation, LuCI-Zugriffe über rpcd),
  `.apk`-Pakete weiterhin auf 25.12.6.
- Raspberry Pi: Die systemd-Unit begrenzt Neustarts auf 5 innerhalb von
  2 Minuten. Bisher hat systemd den Dienst bei einem Konfigurationsfehler
  endlos alle 5 Sekunden neu gestartet. Danach `systemctl reset-failed` und
  `restart` (siehe Pi-Anleitung). Zum Übernehmen die Unit neu kopieren
  (Abschnitt „Aktualisieren“).
- Programmcode unverändert.

### 1.2 (Pakete 1.2-r2)

- Copyright-Inhaber: Benjamin Johann.
- Hinweise zu Software Dritter nur noch für das Dashboard (OpenWrt und
  Raspberry Pi); der WLAN-Analyzer hat eigene.
- Raspberry-Pi-Variante: Lizenz und Hinweise werden mit nach
  `/opt/mesh-roaming/` kopiert, neuer Abschnitt „Aktualisieren“ in der
  Anleitung, Versionsangabe in der systemd-Unit.
- `build-ipk.sh` prüft die Versionsangaben auch in `src/` und `systemd/`.
- Programmcode unverändert gegenüber 1.2-r1.

### 1.2 (Pakete 1.2-r1)

- Versionsnummer in allen Programmen: `--version` für Dienst,
  `mesh-roaming-uci2json` und `mesh-roaming-status`. Außerdem steht sie in der
  Kopfzeile der Live-Seite, in den LuCI-Seitentiteln und in `/config.json`.
  Laufen Seite und Dienst in verschiedenen Versionen, zeigt die Live-Seite
  beide an.
- Pakete enthalten `LICENSE` und `THIRD-PARTY-NOTICES.md` unter
  `/usr/share/licenses/<paket>/`.
- `build-ipk.sh` prüft, ob alle Versionsangaben zur Paketversion passen und
  ob die Kopien unter `src/` identisch sind.
- Nach einem Paket-Upgrade startet der Dienst neu (vorher lief der alte Code
  weiter).
- Neu: `THIRD-PARTY-NOTICES.md` mit allen genutzten Fremdkomponenten.

### 1.1 (Pakete 1.1-r1)

- Mesh-Management-IPs korrigiert (Issues #1, #2).
- Datenschutz: CSRF-Schutz für POST, Dateirechte 0600, `secure_delete`,
  weniger Daten in `/data.json`, keine extern geladenen Schriften.
- Fertige `.apk`-/`.ipk`-Pakete im Repository.

## WLAN-Analyzer (Windows)

### 1.1.1

- Eigene `LICENSE` und eigene Hinweise zu Software Dritter (nur .NET,
  Windows Forms, Windows-WLAN-API); keine Angaben des Dashboards mehr im
  Info-Dialog.
- Copyright-Inhaber: Benjamin Johann.

### 1.1.0

- Auslastungsverlauf: Heatmap Kanal × Zeit (30 min) und eigen/fremd je Kanal.
- Versionsnummer in Titelleiste, Info-Dialog, `--version` und EXE.
- Info-Dialog mit Lizenz und Hinweisen zu Software Dritter.

### 1.0.0

- Erste Version: Spektrum, Kanalauslastung eigen/fremd, Kanalempfehlung,
  AP-Liste, Signalverlauf, CSV-Export, Demo-Modus.
