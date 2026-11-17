using WlanAnalyzer.Scanning;
using WlanAnalyzer.UI;
using WlanAnalyzer.Wlan;

namespace WlanAnalyzer;

internal static class Program
{
    // Aufruf:
    //   WlanAnalyzer.exe                   echte Daten vom WLAN-Adapter des PCs
    //   WlanAnalyzer.exe --demo            simulierte Netze (zum Ausprobieren ohne WLAN)
    //   WlanAnalyzer.exe --band 24|5|6     mit diesem Band-Reiter starten (Standard: 5)
    //   WlanAnalyzer.exe --view signal|load  unten Signal- oder Auslastungsverlauf zeigen
    //   WlanAnalyzer.exe --version         Versionsnummer anzeigen
    //   WlanAnalyzer.exe --screenshot x.png  nach dem ersten Scan Fenster als Bild speichern
    //                                        und beenden (fuer Doku-Screenshots)
    //
    // Copyright Benjamin Johann (WLAN-Analyzer)
    // SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
    [STAThread]
    private static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();

        if (args.Contains("--version", StringComparer.OrdinalIgnoreCase))
        {
            // WinExe hat keine Konsole - Version als Meldung zeigen
            MessageBox.Show($"WLAN-Analyzer {AboutForm.AppVersion}\nCopyright Benjamin Johann (WLAN-Analyzer)\n" +
                            "Lizenz: PolyForm Noncommercial 1.0.0", "WLAN-Analyzer");
            return;
        }

        bool demo = args.Contains("--demo", StringComparer.OrdinalIgnoreCase);
        string? screenshot = Option(args, "--screenshot");
        var band = Option(args, "--band") switch
        {
            "24" or "2.4" => WifiBand.Band24,
            "6" => WifiBand.Band6,
            _ => WifiBand.Band5,
        };

        bool loadView = string.Equals(Option(args, "--view"), "load", StringComparison.OrdinalIgnoreCase);

        IScanSource source;
        try
        {
            source = demo ? new DemoScanSource() : new WlanScanSource();
        }
        catch (Exception ex)
        {
            // Kein WLAN-Dienst (z. B. Server ohne "WLAN AutoConfig") - Demo anbieten.
            var answer = MessageBox.Show(
                "Der WLAN-Dienst von Windows ist nicht verfügbar:\n" + ex.Message +
                "\n\nMit simulierten Demo-Daten starten?",
                "WLAN-Analyzer", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
            if (answer != DialogResult.Yes)
                return;
            source = new DemoScanSource();
        }

        using (source)
            Application.Run(new MainForm(source, band, screenshot, loadView));
    }

    private static string? Option(string[] args, string name)
    {
        int idx = Array.FindIndex(args, a => a.Equals(name, StringComparison.OrdinalIgnoreCase));
        return idx >= 0 && idx + 1 < args.Length ? args[idx + 1] : null;
    }
}
