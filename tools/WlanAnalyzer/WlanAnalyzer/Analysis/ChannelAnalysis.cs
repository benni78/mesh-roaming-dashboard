using WlanAnalyzer.Wlan;

namespace WlanAnalyzer.Analysis;

/// <summary>Belegung eines 20-MHz-Kanals.</summary>
public sealed class ChannelLoad
{
    public required int Channel { get; init; }
    public required int FrequencyMhz { get; init; }
    public bool Dfs { get; init; }

    /// <summary>
    /// Von einem AP auf diesem Kanal gemeldete Belegung (BSS Load, hoechster Wert),
    /// sonst null.
    /// </summary>
    public double? MeasuredPct { get; init; }

    /// <summary>Schaetzung aus Anzahl und Signalstaerke der Netze (0-100).</summary>
    public double EstimatedPct { get; init; }

    /// <summary>Anteil der eigenen Netze an der Belegung (0-1).</summary>
    public double OwnShare { get; init; }

    public int OwnCount { get; init; }
    public int ForeignCount { get; init; }

    /// <summary>Gemessener Wert, sonst die Schaetzung.</summary>
    public double TotalPct => MeasuredPct ?? EstimatedPct;
    public double OwnPct => TotalPct * OwnShare;
    public double ForeignPct => TotalPct - OwnPct;
}

public sealed record ChannelRecommendation(string Text, IReadOnlySet<int> Channels);

/// <summary>
/// Kanalauslastung je 20-MHz-Kanal, aufgeteilt in eigene und fremde Netze.
///
/// Gemessen: Viele APs senden im Beacon das Element "BSS Load" mit der selbst
/// gemessenen Belegung ihres Kanals (Anteil der Zeit, in der der Kanal belegt
/// war - durch alle Netze, eigene wie fremde) und der Zahl verbundener
/// Geraete. Der PC kann die Belegung selbst nicht messen; er sieht nur, was
/// die APs melden.
///
/// Aufteilung eigen/fremd: im Verhaeltnis der verbundenen Geraete der
/// beteiligten APs (aus BSS Load), ohne diese Angabe im Verhaeltnis der
/// signalgewichteten Netzanzahl.
///
/// Geschaetzt (ohne BSS Load): Jedes Netz, das den Kanal ueberlappt, zaehlt
/// mit einem Gewicht von 5-100 % je nach Signalstaerke (-95 dBm ... -50 dBm)
/// und traegt damit bis zu 20 Prozentpunkte bei. Das ist ein Belegungsindex,
/// keine Messung.
/// </summary>
public static class ChannelAnalysis
{
    private const double PointsPerNetwork = 20.0;

    public static double SignalWeight(int rssi) => Math.Clamp((rssi + 95) / 45.0, 0.05, 1.0);

    public static List<ChannelLoad> Compute(WifiBand band, IEnumerable<BssInfo> networks, Func<BssInfo, bool> isOwn)
    {
        var nets = networks.Where(n => n.Band == band).ToList();
        var result = new List<ChannelLoad>();
        foreach (int ch in WifiChannels.Channels(band))
        {
            int f = WifiChannels.FrequencyOf(band, ch);
            var overlapping = nets.Where(n => n.Overlaps(f - 10, f + 10)).ToList();

            double ownWeight = 0, foreignWeight = 0;
            int ownStations = 0, foreignStations = 0, ownCount = 0, foreignCount = 0;
            foreach (var n in overlapping)
            {
                bool own = isOwn(n);
                double w = SignalWeight(n.Rssi);
                if (own) { ownWeight += w; ownCount++; ownStations += n.StationCount ?? 0; }
                else { foreignWeight += w; foreignCount++; foreignStations += n.StationCount ?? 0; }
            }

            // Messwert: APs, deren belegter Bereich die Kanalmitte einschliesst
            double? measured = overlapping
                .Where(n => n.UtilizationPct.HasValue && n.Covers(f))
                .Select(n => n.UtilizationPct!.Value)
                .DefaultIfEmpty(double.NaN)
                .Max();
            if (double.IsNaN(measured.Value))
                measured = null;

            double ownShare;
            if (measured.HasValue && ownStations + foreignStations > 0)
                ownShare = (double)ownStations / (ownStations + foreignStations);
            else if (ownWeight + foreignWeight > 0)
                ownShare = ownWeight / (ownWeight + foreignWeight);
            else
                ownShare = 0;

            result.Add(new ChannelLoad
            {
                Channel = ch,
                FrequencyMhz = f,
                Dfs = WifiChannels.IsDfs(band, ch),
                MeasuredPct = measured,
                EstimatedPct = Math.Min(100, (ownWeight + foreignWeight) * PointsPerNetwork),
                OwnShare = ownShare,
                OwnCount = ownCount,
                ForeignCount = foreignCount,
            });
        }
        return result;
    }

    /// <summary>
    /// Kanal mit der geringsten Belegung durch FREMDE Netze. 2,4 GHz: 1/6/11
    /// (ueberlappungsfrei). 5/6 GHz: 80-MHz-Bloecke, bewertet nach dem Mittel
    /// ihrer vier 20-MHz-Kanaele.
    /// </summary>
    public static ChannelRecommendation Recommend(WifiBand band, IReadOnlyList<ChannelLoad> loads)
    {
        var byChannel = loads.ToDictionary(l => l.Channel);
        if (band == WifiBand.Band24)
        {
            int best = new[] { 1, 6, 11 }
                .OrderBy(c => byChannel.TryGetValue(c, out var l) ? l.ForeignPct : 0)
                .ThenBy(c => c)
                .First();
            return new ChannelRecommendation($"Kanal {best}", new HashSet<int> { best });
        }

        var blocks = band == WifiBand.Band5
            ? new[] { 36, 52, 100, 116, 132, 149 }
            : Enumerable.Range(0, 14).Select(i => 1 + i * 16).ToArray();
        var scored = blocks
            .Select(start => Enumerable.Range(0, 4).Select(i => start + i * 4).ToArray())
            .Where(block => block.All(byChannel.ContainsKey))
            .Select(block => (Block: block, Score: block.Average(c => byChannel[c].ForeignPct)))
            // bei Gleichstand: Nicht-DFS-Bloecke bevorzugen (kein Radar-Abschalten)
            .OrderBy(b => Math.Round(b.Score, 1))
            .ThenBy(b => byChannel[b.Block[0]].Dfs)
            .ThenBy(b => b.Block[0])
            .ToList();
        if (scored.Count == 0)
            return new ChannelRecommendation("–", new HashSet<int>());
        var bestBlock = scored[0].Block;
        string dfs = byChannel[bestBlock[0]].Dfs ? ", DFS" : "";
        return new ChannelRecommendation(
            $"Kanal {bestBlock[0]}–{bestBlock[^1]} (80 MHz{dfs})", new HashSet<int>(bestBlock));
    }
}
