using WlanAnalyzer.Wlan;

namespace WlanAnalyzer.Analysis;

public sealed class TrackedNetwork
{
    public TrackedNetwork(BssInfo latest, DateTime now)
    {
        Latest = latest;
        FirstSeen = now;
        LastSeen = now;
    }

    public BssInfo Latest { get; set; }
    public DateTime FirstSeen { get; }
    public DateTime LastSeen { get; set; }

    /// <summary>Im letzten Scan enthalten.</summary>
    public bool Present { get; set; }

    public List<(DateTime Time, int Rssi)> History { get; } = new();
}

/// <summary>
/// Fuehrt die einzelnen Scans zu einer Liste von APs mit Signalverlauf zusammen.
/// Nur im Arbeitsspeicher - beim Beenden ist alles weg.
/// </summary>
public sealed class NetworkTracker
{
    public static readonly TimeSpan HistoryWindow = TimeSpan.FromMinutes(10);

    /// <summary>So lange bleibt ein nicht mehr gesehenes Netz (grau) in der Liste.</summary>
    public static readonly TimeSpan ForgetAfter = TimeSpan.FromMinutes(2);

    private readonly Dictionary<string, TrackedNetwork> _networks = new(StringComparer.OrdinalIgnoreCase);

    public IReadOnlyCollection<TrackedNetwork> All => _networks.Values;

    public IEnumerable<BssInfo> Present => _networks.Values.Where(n => n.Present).Select(n => n.Latest);

    public void Update(IEnumerable<BssInfo> scan, DateTime now)
    {
        foreach (var n in _networks.Values)
            n.Present = false;

        foreach (var bss in scan)
        {
            if (!_networks.TryGetValue(bss.Bssid, out var tracked))
            {
                tracked = new TrackedNetwork(bss, now);
                _networks[bss.Bssid] = tracked;
            }
            tracked.Latest = bss;
            tracked.LastSeen = now;
            tracked.Present = true;
            tracked.History.Add((now, bss.Rssi));
        }

        foreach (var key in _networks.Where(kv => now - kv.Value.LastSeen > ForgetAfter).Select(kv => kv.Key).ToList())
            _networks.Remove(key);
        foreach (var n in _networks.Values)
            n.History.RemoveAll(h => now - h.Time > HistoryWindow);
    }

    public void Clear() => _networks.Clear();
}
