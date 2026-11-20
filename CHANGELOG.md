# Änderungen / Changelog

## Mesh Roaming Dashboard

### 2.1 (Pakete 2.1-r1)

- **Spektrum mit Netznamen** (Issue #14): Über den Balkendiagrammen der
  Nachbarkanäle je ein Spektrum für 2,4 und 5 GHz wie im WLAN-Analyzer:
  jedes Netz als Fläche über seiner belegten Bandbreite, Höhe =
  Signalstärke, Netzname darüber; eigene Netze (★) kräftig in kühlen,
  fremde blass in warmen Farben, Farbe fest je SSID. Namen ohne
  Überlappung nach Wichtigkeit; wer über der Fläche keinen Platz findet,
  wird – anders als im Analyzer – auch in der eigenen Fläche beschriftet.
  Gleiche Kanalachse wie das Balkendiagramm.
- `data.json`: `scan.bands.<band>.networks` (SSID, Signal, Frequenzbereich,
  Primärkanal, eigen/fremd; keine BSSIDs).

### 2.0 (Pakete 2.0-r1)

- **Nachbarkanäle aus dem WLAN-Scan** (Issue #13): Die Router werten
  zyklisch (Standard alle 60 s) die gefundenen WLANs aus
  (`iw dev <if> scan dump`); die Live-Seite zeigt zwei Diagramme für 2,4 und
  5 GHz: Belegung je 20-MHz-Kanal, getrennt nach eigenen und fremden Netzen,
  gemessen (BSS Load der APs) oder geschätzt (schraffiert), Netzanzahl,
  DFS-Bereich und Kanalempfehlung. Gleiche Logik wie der WLAN-Analyzer
  (Windows), aber ohne Verlauf; bei der Aufteilung eigen/fremd zählt die
  Geräteanzahl nur, wenn alle beteiligten Netze sie melden.
- Aktiver Scan einstellbar: nur Client-Interfaces (Standard), alle
  Interfaces (auch Access Points, kurze Unterbrechung) oder aus. Eigene
  Netze werden über die SSIDs/BSSIDs der eigenen APs automatisch erkannt,
  weitere SSIDs einstellbar. LuCI: Grundeinstellungen → neuer Reiter
  „WLAN-Scan“; `config.json`: Abschnitt `scan`.
- Neue MQTT-Werte `…/scan/<band>/recommendation` und `…/scan/<band>/channels`
  (JSON).
- Live-Seite: Das Panel „Nachbarkanäle“ steht unter dem Grundriss.
- Raspberry-Pi-Variante: gleicher Dienst und gleiche Seite;
  `examples/config.*.json` um `scan` ergänzt.

### 1.4 (Pakete 1.4-r1)

- **LuCI zeigt die installierte Version** (Issue #9): Die Seitentitel nennen
  die tatsächlich installierte Paketversion (z. B. „1.4-r1“) statt einer in
  den JS-Dateien fest eingetragenen. Hinweise erscheinen, wenn die Seite
  noch aus dem Browser-Cache stammt („Veraltete Seite – Strg+F5“) oder der
  Dienst nach einem Upgrade noch mit der alten Version läuft. Neu:
  `/usr/libexec/mesh-roaming-version`, `/api/status` liefert die Version
  des laufenden Dienstes.
- **OpenWrt 25.12 (apk): Dienst startet nach einem Upgrade neu.** Bisher
  hat `apk` beim Upgrade die `postinst` nicht ausgeführt (apk ruft dafür
  `.post-upgrade` auf), der Dienst lief mit dem alten Code weiter. Die
  `.apk`-Pakete enthalten jetzt beide Skripte (lokale Änderung 3 am
  übernommenen `openwrt-ipk2apk`).
- **Kanalauslastung: Fähigkeit des WLAN-Chips sichtbar** (Issue #10): Je
  Funkband steht der Treiber und ob er eigenen und fremden Verkehr trennen
  kann. Bei Chips ohne BSS-Empfangszeit (ath9k) heißt der Empfangsanteil
  jetzt „Empfang (alle WLANs auf dem Kanal)“ statt „eigenes Netz +
  Nachbarn“, bei Client-Interfaces heißt der eigene Anteil „verbundenes
  Netz“. Kurze Erklärungen unter der Legende. Neue MQTT-Werte
  `…/util/<band>/mode` und `…/driver`.
- **Eigener Verkehr über die verbundenen Geräte gemessen** (Issue #11):
  Der Dienst summiert die Sende-/Empfangszeit aller verbundenen Geräte
  (`iw station dump`, `rx/tx duration`) und zeigt sie je Band als Abgleich
  zur Kanalauslastung. Bei ath9k teilt das den Empfang auf in „eigene
  Geräte (gemessen)“ und „übrige WLANs“. MAC-Adressen dienen nur intern
  der Differenzbildung und werden weder gespeichert noch angezeigt. Neue
  MQTT-Werte `…/own_sta`, `…/rx_own`, `…/rx_other`.
- **Rauschen und Signal für Laien bewertet** (Issue #12): Neben dem
  Rauschwert steht „gut“ (bis −90 dBm), „mittel“ (−89 bis −80 dBm) oder
  „schlecht“, mit Erklärung im Tooltip. Bei Client-Interfaces zusätzlich
  Signal des verbundenen AP und Signal-Rausch-Abstand mit Einstufung
  (sehr gut / gut / ausreichend / schlecht). Neue MQTT-Werte `…/signal`,
  `…/snr`.
- Raspberry-Pi-Variante: gleiche Live-Seite und gleicher Dienst, keine
  weiteren Änderungen.

### 1.3 (Pakete 1.3-r2)

- Der eigene Router wird automatisch als „Dieser Router“ eingetragen
  (Issue #8), wenn es noch keinen einzigen Router-Eintrag gibt: bei
  Installation, Upgrade und vor jedem Start des Dienstes. Name und ID aus
  dem Hostnamen, IP-Adresse des LAN-Interfaces, Abfrage lokal ohne SSH. Der
  Dienst läuft damit direkt nach der Installation, statt wegen fehlender
  Router nicht zu starten. Vorhandene Router und eine von Hand gepflegte
  `config.json` bleiben unangetastet.
- Doku: Nach der Installation in LuCI ab- und wieder anmelden, sonst fehlt
  der Menüeintrag (LuCI speichert das Menü pro Anmeldung im Browser).
- Getestet auf OpenWrt 23.05.6 (opkg) und 25.12.6 (apk): Erstinstallation,
  Upgrade von 1.2-r3 ohne Router und von 1.3-r1 mit Routern, alle Router
  gelöscht, nur deaktivierter Router, `config.json` ohne UCI.
- Programmcode (`mesh_roaming_pi.py`) und Raspberry-Pi-Variante unverändert.

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
