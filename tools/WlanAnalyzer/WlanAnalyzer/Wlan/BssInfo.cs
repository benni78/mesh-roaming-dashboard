namespace WlanAnalyzer.Wlan;

/// <summary>Ein Access Point (BSS) mit allen fuer die Anzeige noetigen Werten.</summary>
public sealed class BssInfo
{
    public required string Bssid { get; init; }
    public required string Ssid { get; init; }
    public required int Rssi { get; init; }
    public required int LinkQuality { get; init; }
    public required WifiBand Band { get; init; }
    public required int Channel { get; init; }
    public required int FrequencyMhz { get; init; }
    public required int Width { get; init; }
    public required int CenterFrequencyMhz { get; init; }
    public required string Standard { get; init; }
    public string Security { get; init; } = "";
    public int? StationCount { get; init; }

    /// <summary>Vom AP gemeldete Kanalbelegung in Prozent (BSS Load), sonst null.</summary>
    public double? UtilizationPct { get; init; }

    public bool IsConnected { get; init; }

    public string DisplaySsid => Ssid.Length == 0 ? "(versteckt)" : Ssid;

    /// <summary>
    /// Belegter Frequenzbereich. Klassische 20-MHz-Kanaele im 2,4-GHz-Band
    /// belegen spektral etwa 22 MHz (DSSS-Maske).
    /// </summary>
    public double LowMhz => CenterFrequencyMhz - HalfWidth;
    public double HighMhz => CenterFrequencyMhz + HalfWidth;
    private double HalfWidth => Band == WifiBand.Band24 && Width == 20 ? 11 : Width / 2.0;

    public bool Covers(double mhz) => mhz > LowMhz && mhz < HighMhz;

    public bool Overlaps(double low, double high) => LowMhz < high && HighMhz > low;

    /// <summary>Wandelt einen Roh-Eintrag der Windows-API um; null bei unbekannter Frequenz.</summary>
    public static BssInfo? FromRaw(RawBss raw, IReadOnlyDictionary<string, string> security, string? connectedBssid)
    {
        var band = WifiChannels.BandOf(raw.FrequencyMhz);
        if (band is null)
            return null;
        int channel = WifiChannels.ChannelOf(raw.FrequencyMhz);
        var ie = InformationElements.Parse(raw.InformationElements);

        int width = ie.Width;
        int centerChannel = ie.CenterChannel ?? channel;
        // Unplausible Angaben (Mittenkanal weit weg vom Primaerkanal) verwerfen.
        if (Math.Abs(centerChannel - channel) > 30)
        {
            width = 20;
            centerChannel = channel;
        }

        return new BssInfo
        {
            Bssid = raw.Bssid,
            Ssid = raw.Ssid,
            Rssi = raw.Rssi,
            LinkQuality = raw.LinkQuality,
            Band = band.Value,
            Channel = channel,
            FrequencyMhz = raw.FrequencyMhz,
            Width = width,
            CenterFrequencyMhz = WifiChannels.FrequencyOf(band.Value, centerChannel),
            Standard = StandardName(ie, raw.PhyType),
            Security = security.TryGetValue(raw.Ssid, out var sec) ? sec : "",
            StationCount = ie.StationCount,
            UtilizationPct = ie.ChannelUtilization is int u ? u * 100.0 / 255.0 : null,
            IsConnected = string.Equals(raw.Bssid, connectedBssid, StringComparison.OrdinalIgnoreCase),
        };
    }

    private static string StandardName(IeInfo ie, int phyType)
    {
        if (ie.Eht) return "Wi-Fi 7 (be)";
        if (ie.He) return "Wi-Fi 6 (ax)";
        if (ie.Vht) return "Wi-Fi 5 (ac)";
        if (ie.Ht) return "Wi-Fi 4 (n)";
        return phyType switch
        {
            4 => "802.11a",
            5 => "802.11b",
            6 => "802.11g",
            7 => "Wi-Fi 4 (n)",
            8 => "Wi-Fi 5 (ac)",
            10 => "Wi-Fi 6 (ax)",
            11 => "Wi-Fi 7 (be)",
            _ => "?",
        };
    }
}
