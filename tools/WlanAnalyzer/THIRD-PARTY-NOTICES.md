# Hinweise zu Software Dritter – WLAN-Analyzer

*English summary: The WLAN Analyzer is licensed under the PolyForm
Noncommercial License 1.0.0 (see [`LICENSE`](LICENSE)). It contains no
third-party source code and uses no NuGet packages. It runs on .NET 8 and
Windows Forms (MIT) and uses the Windows Native WiFi API.*

Gilt für: WLAN-Analyzer (`tools/WlanAnalyzer/`). Stand: Version 1.1.1.

## 1. Enthaltene Software Dritter

Keine. Der Quellcode ist vollständig selbst geschrieben, es werden keine
NuGet-Pakete verwendet.

## 2. Genutzte Software

| Software | Wofür | Lizenz |
|---|---|---|
| .NET 8 Runtime | Laufzeit | MIT, © .NET Foundation and Contributors |
| Windows Forms | Oberfläche | MIT, © .NET Foundation and Contributors |
| Windows Native WiFi API (`wlanapi.dll`) | WLAN-Scan | Bestandteil von Windows, Microsoft-Lizenzbedingungen |

Beim normalen Build (abhängig von einer installierten .NET-Laufzeit) wird
keine dieser Komponenten mitgeliefert.

**Eigenständige EXE:** Wird der Analyzer mit
`dotnet publish --self-contained` veröffentlicht, enthält die EXE die
.NET-Laufzeit und Windows Forms. Dann gehören zur Weitergabe zusätzlich deren
Lizenz (MIT) und die Drittanbieter-Hinweise von .NET:

- <https://github.com/dotnet/runtime/blob/main/LICENSE.TXT>
- <https://github.com/dotnet/runtime/blob/main/THIRD-PARTY-NOTICES.TXT>
- <https://github.com/dotnet/winforms/blob/main/LICENSE.TXT>
- <https://github.com/dotnet/winforms/blob/main/THIRD-PARTY-NOTICES.TXT>

### Schriften

Der Analyzer verwendet die Windows-Systemschriften Segoe UI und Consolas.
Sie werden nicht mitgeliefert.

## 3. Marken

Windows, Visual Studio und .NET sind Marken der Microsoft Corporation. Wi-Fi,
Wi-Fi 6, Wi-Fi 6E und Wi-Fi 7 sind Marken der Wi-Fi Alliance. Sie werden hier
nur beschreibend verwendet. Dieses Projekt steht in keiner Verbindung zu
diesen Inhabern und wird von ihnen nicht unterstützt.
