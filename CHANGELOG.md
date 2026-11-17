# Änderungen / Changelog

## Mesh Roaming Dashboard

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

### 1.1.0

- Auslastungsverlauf: Heatmap Kanal × Zeit (30 min) und eigen/fremd je Kanal.
- Versionsnummer in Titelleiste, Info-Dialog, `--version` und EXE.
- Info-Dialog mit Lizenz und Hinweisen zu Software Dritter.

### 1.0.0

- Erste Version: Spektrum, Kanalauslastung eigen/fremd, Kanalempfehlung,
  AP-Liste, Signalverlauf, CSV-Export, Demo-Modus.
