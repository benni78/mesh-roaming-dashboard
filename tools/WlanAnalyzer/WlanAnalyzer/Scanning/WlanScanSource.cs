using WlanAnalyzer.Wlan;

namespace WlanAnalyzer.Scanning;

/// <summary>Echte Scans ueber den WLAN-Adapter des PCs.</summary>
public sealed class WlanScanSource : IScanSource
{
    // Ein aktiver Scan ueber alle Baender dauert je nach Treiber 2-4 s.
    private static readonly TimeSpan ScanTimeout = TimeSpan.FromSeconds(6);

    private readonly WlanClient _client = new();

    public bool IsDemo => false;

    public IReadOnlyList<WlanInterfaceInfo> GetInterfaces() => _client.GetInterfaces();

    public ScanResult Scan(Guid interfaceId)
    {
        bool fresh = _client.ScanAndWait(interfaceId, ScanTimeout);
        var raw = _client.GetBssList(interfaceId);
        var security = _client.GetSecurityBySsid(interfaceId);
        var (ssid, bssid) = _client.GetCurrentConnection(interfaceId);

        var networks = raw
            .Select(r => BssInfo.FromRaw(r, security, bssid))
            .Where(n => n is not null)
            .Cast<BssInfo>()
            .ToList();
        return new ScanResult(networks, ssid, bssid, DateTime.Now, fresh);
    }

    public void Dispose() => _client.Dispose();
}
