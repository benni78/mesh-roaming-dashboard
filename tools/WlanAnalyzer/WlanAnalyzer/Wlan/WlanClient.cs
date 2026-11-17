using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

namespace WlanAnalyzer.Wlan;

public sealed record WlanInterfaceInfo(Guid Id, string Description, bool Connected);

/// <summary>Ein Eintrag aus WlanGetNetworkBssList, noch ohne Auswertung.</summary>
public sealed record RawBss(
    string Ssid, string Bssid, int PhyType, int Rssi, int LinkQuality,
    int FrequencyMhz, byte[] InformationElements);

/// <summary>
/// Windows verweigert den WLAN-Scan (seit Windows 11 24H2 ohne
/// Standortfreigabe fuer Desktop-Apps).
/// </summary>
public sealed class WlanAccessDeniedException : Exception
{
    public WlanAccessDeniedException()
        : base("Windows verweigert den Zugriff auf die WLAN-Scanergebnisse (Standortfreigabe fehlt).") { }
}

/// <summary>Duenne Huelle um die Native WiFi API.</summary>
internal sealed class WlanClient : IDisposable
{
    // Layout der Strukturen (Offsets in Byte), siehe wlanapi.h / windot11.h:
    //   WLAN_INTERFACE_INFO_LIST: DWORD dwNumberOfItems, DWORD dwIndex, dann Eintraege
    //   WLAN_INTERFACE_INFO (532): GUID(16) | WCHAR[256] Beschreibung | DWORD State
    //   WLAN_BSS_LIST:             DWORD dwTotalSize, DWORD dwNumberOfItems, dann Eintraege
    //   WLAN_BSS_ENTRY (360):      0 DOT11_SSID (ULONG Laenge + 32 Byte) | 36 uPhyId |
    //                              40 BSSID (6) | 48 BssType | 52 PhyType | 56 lRssi |
    //                              60 uLinkQuality | 64 bInRegDomain | 66 usBeaconPeriod |
    //                              72 ullTimestamp | 80 ullHostTimestamp | 88 usCapability |
    //                              92 ulChCenterFrequency (kHz) | 96 WLAN_RATE_SET (256) |
    //                              352 ulIeOffset | 356 ulIeSize
    //   WLAN_AVAILABLE_NETWORK (628): 0 Profilname WCHAR[256] | 512 DOT11_SSID |
    //                              608 bSecurityEnabled | 612 dot11DefaultAuthAlgorithm |
    //                              620 dwFlags
    //   WLAN_CONNECTION_ATTRIBUTES: 520 DOT11_SSID | 560 BSSID (6)
    private const int InterfaceInfoSize = 532;
    private const int BssEntrySize = 360;
    private const int AvailableNetworkSize = 628;

    private IntPtr _handle;
    private readonly WlanNative.WlanNotificationCallback _callback; // Referenz halten (GC)
    private readonly object _lock = new();
    private readonly Dictionary<Guid, ManualResetEventSlim> _scanDone = new();

    public WlanClient()
    {
        Check(WlanNative.WlanOpenHandle(2, IntPtr.Zero, out _, out _handle), "WlanOpenHandle");
        _callback = OnNotification;
        WlanNative.WlanRegisterNotification(_handle, WlanNative.NotificationSourceAcm, true,
            _callback, IntPtr.Zero, IntPtr.Zero, out _);
    }

    public void Dispose()
    {
        if (_handle == IntPtr.Zero)
            return;
        WlanNative.WlanRegisterNotification(_handle, 0, true, null, IntPtr.Zero, IntPtr.Zero, out _);
        WlanNative.WlanCloseHandle(_handle, IntPtr.Zero);
        _handle = IntPtr.Zero;
        lock (_lock)
        {
            foreach (var ev in _scanDone.Values)
                ev.Dispose();
            _scanDone.Clear();
        }
    }

    private void OnNotification(IntPtr data, IntPtr context)
    {
        // WLAN_NOTIFICATION_DATA: DWORD Source | DWORD Code | GUID InterfaceGuid | ...
        uint source = (uint)Marshal.ReadInt32(data, 0);
        uint code = (uint)Marshal.ReadInt32(data, 4);
        if (source != WlanNative.NotificationSourceAcm ||
            (code != WlanNative.AcmScanComplete && code != WlanNative.AcmScanFail))
            return;
        var guid = Marshal.PtrToStructure<Guid>(data + 8);
        lock (_lock)
        {
            if (_scanDone.TryGetValue(guid, out var ev))
                ev.Set();
        }
    }

    public IReadOnlyList<WlanInterfaceInfo> GetInterfaces()
    {
        Check(WlanNative.WlanEnumInterfaces(_handle, IntPtr.Zero, out var list), "WlanEnumInterfaces");
        try
        {
            int count = Marshal.ReadInt32(list, 0);
            var result = new List<WlanInterfaceInfo>(count);
            for (int i = 0; i < count; i++)
            {
                IntPtr p = list + 8 + i * InterfaceInfoSize;
                var id = Marshal.PtrToStructure<Guid>(p);
                string description = Marshal.PtrToStringUni(p + 16) ?? "";
                int state = Marshal.ReadInt32(p, 16 + 512);
                result.Add(new WlanInterfaceInfo(id, description, state == 1));
            }
            return result;
        }
        finally
        {
            WlanNative.WlanFreeMemory(list);
        }
    }

    /// <summary>
    /// Loest einen aktiven Scan aus und wartet hoechstens <paramref name="timeout"/>
    /// auf dessen Ende. false = Scan nicht moeglich oder nicht rechtzeitig fertig;
    /// die BSS-Liste enthaelt dann die zuletzt von Windows gesehenen Netze.
    /// </summary>
    public bool ScanAndWait(Guid interfaceId, TimeSpan timeout)
    {
        ManualResetEventSlim ev;
        lock (_lock)
        {
            if (!_scanDone.TryGetValue(interfaceId, out ev!))
            {
                ev = new ManualResetEventSlim(false);
                _scanDone[interfaceId] = ev;
            }
            ev.Reset();
        }
        uint r = WlanNative.WlanScan(_handle, ref interfaceId, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
        if (r == WlanNative.ErrorAccessDenied)
            throw new WlanAccessDeniedException();
        if (r != WlanNative.ErrorSuccess)
            return false; // z. B. Adapter gerade beschaeftigt
        return ev.Wait(timeout);
    }

    public IReadOnlyList<RawBss> GetBssList(Guid interfaceId)
    {
        uint r = WlanNative.WlanGetNetworkBssList(_handle, ref interfaceId, IntPtr.Zero,
            WlanNative.Dot11BssTypeAny, false, IntPtr.Zero, out var list);
        if (r == WlanNative.ErrorAccessDenied)
            throw new WlanAccessDeniedException();
        Check(r, "WlanGetNetworkBssList");
        try
        {
            int count = Marshal.ReadInt32(list, 4);
            var result = new List<RawBss>(count);
            for (int i = 0; i < count; i++)
            {
                IntPtr e = list + 8 + i * BssEntrySize;
                string ssid = ReadSsid(e);
                string bssid = ReadMac(e + 40);
                int phy = Marshal.ReadInt32(e, 52);
                int rssi = Marshal.ReadInt32(e, 56);
                int quality = Marshal.ReadInt32(e, 60);
                int freqKhz = Marshal.ReadInt32(e, 92);
                int ieOffset = Marshal.ReadInt32(e, 352);
                int ieSize = Marshal.ReadInt32(e, 356);
                var ies = new byte[Math.Max(0, ieSize)];
                if (ieSize > 0)
                    Marshal.Copy(e + ieOffset, ies, 0, ieSize);
                result.Add(new RawBss(ssid, bssid, phy, rssi, quality, freqKhz / 1000, ies));
            }
            return result;
        }
        finally
        {
            WlanNative.WlanFreeMemory(list);
        }
    }

    /// <summary>Verschluesselung je SSID (aus der Liste der verfuegbaren Netze).</summary>
    public IReadOnlyDictionary<string, string> GetSecurityBySsid(Guid interfaceId)
    {
        var result = new Dictionary<string, string>(StringComparer.Ordinal);
        uint r = WlanNative.WlanGetAvailableNetworkList(_handle, ref interfaceId, 0, IntPtr.Zero, out var list);
        if (r != WlanNative.ErrorSuccess)
            return result;
        try
        {
            int count = Marshal.ReadInt32(list, 0);
            for (int i = 0; i < count; i++)
            {
                IntPtr p = list + 8 + i * AvailableNetworkSize;
                string ssid = ReadSsid(p + 512);
                bool secured = Marshal.ReadInt32(p, 608) != 0;
                int auth = Marshal.ReadInt32(p, 612);
                result.TryAdd(ssid, secured ? AuthName(auth) : "Offen");
            }
        }
        finally
        {
            WlanNative.WlanFreeMemory(list);
        }
        return result;
    }

    /// <summary>SSID und BSSID der aktuellen Verbindung, oder (null, null).</summary>
    public (string? Ssid, string? Bssid) GetCurrentConnection(Guid interfaceId)
    {
        uint r = WlanNative.WlanQueryInterface(_handle, ref interfaceId, WlanNative.IntfOpcodeCurrentConnection,
            IntPtr.Zero, out _, out var data, IntPtr.Zero);
        if (r != WlanNative.ErrorSuccess)
            return (null, null); // ERROR_INVALID_STATE = nicht verbunden
        try
        {
            return (ReadSsid(data + 520), ReadMac(data + 560));
        }
        finally
        {
            WlanNative.WlanFreeMemory(data);
        }
    }

    private static string ReadSsid(IntPtr dot11Ssid)
    {
        int len = Math.Clamp(Marshal.ReadInt32(dot11Ssid, 0), 0, 32);
        var bytes = new byte[len];
        Marshal.Copy(dot11Ssid + 4, bytes, 0, len);
        return Encoding.UTF8.GetString(bytes).TrimEnd('\0');
    }

    private static string ReadMac(IntPtr p)
    {
        var mac = new byte[6];
        Marshal.Copy(p, mac, 0, 6);
        return string.Join(":", mac.Select(b => b.ToString("x2")));
    }

    private static string AuthName(int auth) => auth switch
    {
        1 => "Offen",
        2 => "WEP",
        3 => "WPA-Enterprise",
        4 => "WPA-Personal",
        6 => "WPA2-Enterprise",
        7 => "WPA2-Personal",
        8 => "WPA3-Enterprise 192",
        9 => "WPA3-Personal",
        10 => "OWE",
        11 => "WPA3-Enterprise",
        _ => "Verschlüsselt",
    };

    private static void Check(uint result, string function)
    {
        if (result != WlanNative.ErrorSuccess)
            throw new Win32Exception((int)result, function + " fehlgeschlagen (" + result + ")");
    }
}
