using WlanAnalyzer.Wlan;

namespace WlanAnalyzer.Scanning;

public sealed record ScanResult(
    IReadOnlyList<BssInfo> Networks,
    string? ConnectedSsid,
    string? ConnectedBssid,
    DateTime Time,
    bool FreshScan);

/// <summary>Liefert WLAN-Scans - vom echten Adapter oder simuliert.</summary>
public interface IScanSource : IDisposable
{
    bool IsDemo { get; }

    IReadOnlyList<WlanInterfaceInfo> GetInterfaces();

    /// <summary>Scannt (blockierend, einige Sekunden) und liefert alle sichtbaren APs.</summary>
    ScanResult Scan(Guid interfaceId);
}
