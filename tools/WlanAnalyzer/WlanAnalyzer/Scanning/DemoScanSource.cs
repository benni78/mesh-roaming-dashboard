using WlanAnalyzer.Wlan;

namespace WlanAnalyzer.Scanning;

/// <summary>
/// Simulierte Umgebung (frei erfundene Netze) zum Ausprobieren der Oberflaeche
/// ohne WLAN-Adapter. Signal und Auslastung schwanken bei jedem Scan leicht,
/// die Auslastung zusaetzlich langsam ueber die Zeit (fuer den Verlauf).
/// </summary>
public sealed class DemoScanSource : IScanSource
{
    private sealed record DemoNet(
        string Ssid, string Bssid, WifiBand Band, int Channel, int Width, int CenterChannel,
        int Rssi, string Standard, string Security, int? Stations, double? Utilization);

    private static readonly DemoNet[] Nets =
    {
        // eigenes Mesh "Heimnetz" mit zwei Routern
        new("Heimnetz", "02:00:00:00:01:01", WifiBand.Band24, 1, 20, 1, -47, "Wi-Fi 6 (ax)", "WPA2-Personal", 4, 22),
        new("Heimnetz", "02:00:00:00:01:02", WifiBand.Band5, 36, 80, 42, -52, "Wi-Fi 6 (ax)", "WPA2-Personal", 6, 18),
        new("Heimnetz-Gast", "02:00:00:00:01:03", WifiBand.Band24, 1, 20, 1, -48, "Wi-Fi 6 (ax)", "WPA2-Personal", 1, 22),
        new("Heimnetz", "02:00:00:00:02:01", WifiBand.Band24, 6, 20, 6, -66, "Wi-Fi 6 (ax)", "WPA2-Personal", 2, 41),
        new("Heimnetz", "02:00:00:00:02:02", WifiBand.Band5, 100, 80, 106, -69, "Wi-Fi 6 (ax)", "WPA2-Personal", 3, 12),
        // Nachbarschaft
        new("Nachbar-WLAN", "02:00:00:00:10:01", WifiBand.Band24, 6, 40, 8, -71, "Wi-Fi 4 (n)", "WPA2-Personal", 5, 47),
        new("Nachbar-WLAN_5G", "02:00:00:00:10:02", WifiBand.Band5, 36, 80, 42, -77, "Wi-Fi 5 (ac)", "WPA2-Personal", 4, 38),
        new("WLAN-7F3A", "02:00:00:00:11:01", WifiBand.Band24, 11, 20, 11, -79, "Wi-Fi 6 (ax)", "WPA3-Personal", 3, 29),
        new("WLAN-7F3A", "02:00:00:00:11:02", WifiBand.Band5, 52, 80, 58, -82, "Wi-Fi 6 (ax)", "WPA3-Personal", 2, 9),
        new("Kabelbox-2G", "02:00:00:00:12:01", WifiBand.Band24, 11, 20, 11, -84, "Wi-Fi 4 (n)", "WPA2-Personal", null, null),
        new("DIRECT-Drucker", "02:00:00:00:13:01", WifiBand.Band24, 6, 20, 6, -74, "Wi-Fi 4 (n)", "WPA2-Personal", null, null),
        new("Buero-Nebenan", "02:00:00:00:14:01", WifiBand.Band24, 3, 20, 3, -87, "802.11g", "WPA2-Personal", null, null),
        new("Hotspot", "02:00:00:00:15:01", WifiBand.Band5, 149, 20, 149, -86, "Wi-Fi 5 (ac)", "Offen", 7, 25),
        new("", "02:00:00:00:16:01", WifiBand.Band24, 11, 20, 11, -89, "Wi-Fi 4 (n)", "WPA2-Personal", null, null),
        new("Nachbar-WiFi7", "02:00:00:00:17:01", WifiBand.Band6, 37, 160, 47, -81, "Wi-Fi 7 (be)", "WPA3-Personal", 1, 6),
    };

    private const string ConnectedBssid = "02:00:00:00:01:02";
    private readonly Random _random = new(42);

    public bool IsDemo => true;

    public IReadOnlyList<WlanInterfaceInfo> GetInterfaces() =>
        new[] { new WlanInterfaceInfo(Guid.Empty, "Demo-Adapter (simulierte Daten)", true) };

    public ScanResult Scan(Guid interfaceId)
    {
        Thread.Sleep(400);
        return SimulateAt(DateTime.Now);
    }

    /// <summary>Simulierte Scans der Vergangenheit (aelteste zuerst), damit die Verlaeufe sofort etwas zeigen.</summary>
    public IEnumerable<ScanResult> Backfill(TimeSpan span, TimeSpan step)
    {
        var now = DateTime.Now;
        for (var t = now - span + step; t < now; t += step)
            yield return SimulateAt(t);
    }

    private ScanResult SimulateAt(DateTime time)
    {
        double minutes = (time - DateTime.Today).TotalMinutes;
        var list = new List<BssInfo>();
        for (int k = 0; k < Nets.Length; k++)
        {
            var n = Nets[k];
            int rssi = n.Rssi + _random.Next(-3, 4);
            // schwaechste Netze tauchen nicht in jedem Scan auf
            if (rssi < -88 && _random.NextDouble() < 0.4)
                continue;
            double? util = n.Utilization is double u
                ? Math.Clamp(u + Drift(n, k, minutes) + _random.Next(-4, 5), 0, 100)
                : null;
            list.Add(new BssInfo
            {
                Bssid = n.Bssid,
                Ssid = n.Ssid,
                Rssi = rssi,
                LinkQuality = Math.Clamp(2 * (rssi + 100), 0, 100),
                Band = n.Band,
                Channel = n.Channel,
                FrequencyMhz = WifiChannels.FrequencyOf(n.Band, n.Channel),
                Width = n.Width,
                CenterFrequencyMhz = WifiChannels.FrequencyOf(n.Band, n.CenterChannel),
                Standard = n.Standard,
                Security = n.Security,
                StationCount = n.Stations,
                UtilizationPct = util,
                IsConnected = n.Bssid == ConnectedBssid,
            });
        }
        return new ScanResult(list, "Heimnetz", ConnectedBssid, time, true);
    }

    // Langsame Schwankung je Netz; "Nachbar-WLAN_5G" streamt alle 12 min fuer 4 min.
    private static double Drift(DemoNet n, int k, double minutes)
    {
        double wave = 10 * Math.Sin(2 * Math.PI * minutes / (7 + k) + k);
        if (n.Ssid == "Nachbar-WLAN_5G" && minutes % 12 < 4)
            wave += 40;
        return wave;
    }

    public void Dispose() { }
}
