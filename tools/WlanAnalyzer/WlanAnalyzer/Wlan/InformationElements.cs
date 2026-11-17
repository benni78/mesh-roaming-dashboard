namespace WlanAnalyzer.Wlan;

/// <summary>Ausgewertete Informationselemente (IEs) aus Beacon/Probe Response.</summary>
public sealed class IeInfo
{
    /// <summary>BSS Load (IE 11): Anzahl verbundener Stationen.</summary>
    public int? StationCount { get; set; }

    /// <summary>BSS Load (IE 11): vom AP gemessene Kanalbelegung 0-255.</summary>
    public int? ChannelUtilization { get; set; }

    public int Width { get; set; } = 20;

    /// <summary>Mittenkanal bei 40/80/160/320 MHz, sonst null.</summary>
    public int? CenterChannel { get; set; }

    public bool Ht { get; set; }
    public bool Vht { get; set; }
    public bool He { get; set; }
    public bool Eht { get; set; }
}

/// <summary>
/// Liest Kanalbreite und BSS Load aus den IEs (IEEE 802.11-2020, 9.4.2).
/// Die breiteste gefundene Angabe gewinnt (HT &lt; VHT &lt; HE-6GHz &lt; EHT).
/// </summary>
public static class InformationElements
{
    private const int IdBssLoad = 11;
    private const int IdHtOperation = 61;
    private const int IdVhtOperation = 192;
    private const int IdHtCapabilities = 45;
    private const int IdVhtCapabilities = 191;
    private const int IdExtension = 255;
    private const int ExtHeCapabilities = 35;
    private const int ExtHeOperation = 36;
    private const int ExtEhtOperation = 106;
    private const int ExtEhtCapabilities = 108;

    public static IeInfo Parse(byte[] ies)
    {
        var info = new IeInfo();
        int i = 0;
        while (i + 2 <= ies.Length)
        {
            int id = ies[i];
            int len = ies[i + 1];
            if (i + 2 + len > ies.Length)
                break;
            var d = new ReadOnlySpan<byte>(ies, i + 2, len);
            switch (id)
            {
                case IdBssLoad when len >= 5:
                    info.StationCount = d[0] | (d[1] << 8);
                    info.ChannelUtilization = d[2];
                    break;
                case IdHtCapabilities:
                    info.Ht = true;
                    break;
                case IdHtOperation when len >= 2:
                    info.Ht = true;
                    ParseHtOperation(d, info);
                    break;
                case IdVhtCapabilities:
                    info.Vht = true;
                    break;
                case IdVhtOperation when len >= 3:
                    info.Vht = true;
                    ParseVhtOperation(d[0], d[1], d[2], info);
                    break;
                case IdExtension when len >= 1:
                    ParseExtension(d[0], d[1..], info);
                    break;
            }
            i += 2 + len;
        }
        return info;
    }

    private static void ParseHtOperation(ReadOnlySpan<byte> d, IeInfo info)
    {
        int primary = d[0];
        int secondaryOffset = d[1] & 0x03;   // 1 = oberhalb, 3 = unterhalb
        bool anyWidth = (d[1] & 0x04) != 0;  // STA Channel Width: 40 MHz erlaubt
        if (anyWidth && secondaryOffset is 1 or 3)
            SetWidth(info, 40, secondaryOffset == 1 ? primary + 2 : primary - 2);
    }

    private static void ParseVhtOperation(int width, int ccfs0, int ccfs1, IeInfo info)
    {
        switch (width)
        {
            case 1 when ccfs1 == 0:
                SetWidth(info, 80, ccfs0);
                break;
            case 1 when Math.Abs(ccfs1 - ccfs0) == 8:
                SetWidth(info, 160, ccfs1);
                break;
            case 1:
            case 3:
                SetWidth(info, 80, ccfs0); // 80+80: nur das erste Segment darstellen
                break;
            case 2:
                SetWidth(info, 160, ccfs0); // veraltete Schreibweise fuer 160 MHz
                break;
        }
    }

    private static void ParseExtension(int extId, ReadOnlySpan<byte> d, IeInfo info)
    {
        switch (extId)
        {
            case ExtHeCapabilities:
                info.He = true;
                break;
            case ExtHeOperation:
                info.He = true;
                ParseHeOperation(d, info);
                break;
            case ExtEhtCapabilities:
                info.Eht = true;
                break;
            case ExtEhtOperation:
                info.Eht = true;
                ParseEhtOperation(d, info);
                break;
        }
    }

    private static void ParseHeOperation(ReadOnlySpan<byte> d, IeInfo info)
    {
        // HE Operation Parameters (3) | BSS Color (1) | Basic HE-MCS (2) |
        // [VHT Operation Info (3)] | [Max Co-Hosted BSSID (1)] | [6 GHz Operation Info (5)]
        if (d.Length < 6)
            return;
        int parameters = d[0] | (d[1] << 8) | (d[2] << 16);
        int idx = 6;
        if ((parameters & (1 << 14)) != 0)
        {
            if (d.Length >= idx + 3)
                ParseVhtOperation(d[idx], d[idx + 1], d[idx + 2], info);
            idx += 3;
        }
        if ((parameters & (1 << 15)) != 0)
            idx += 1;
        if ((parameters & (1 << 17)) != 0 && d.Length >= idx + 4)
        {
            // 6 GHz: Primary Channel | Control (Bit 0-1 Breite) | CCFS0 | CCFS1
            int w = d[idx + 1] & 0x03;
            int ccfs0 = d[idx + 2];
            int ccfs1 = d[idx + 3];
            switch (w)
            {
                case 1: SetWidth(info, 40, ccfs0); break;
                case 2: SetWidth(info, 80, ccfs0); break;
                case 3: SetWidth(info, 160, ccfs1 != 0 ? ccfs1 : ccfs0); break;
            }
        }
    }

    private static void ParseEhtOperation(ReadOnlySpan<byte> d, IeInfo info)
    {
        // EHT Operation Parameters (1) | Basic EHT-MCS (4) | [Control (1) | CCFS0 | CCFS1 ...]
        if (d.Length < 8 || (d[0] & 0x01) == 0)
            return;
        int w = d[5] & 0x07;
        int ccfs0 = d[6];
        int ccfs1 = d[7];
        switch (w)
        {
            case 3: SetWidth(info, 160, ccfs1 != 0 ? ccfs1 : ccfs0); break;
            case 4: SetWidth(info, 320, ccfs1 != 0 ? ccfs1 : ccfs0); break;
        }
    }

    private static void SetWidth(IeInfo info, int width, int center)
    {
        if (width <= info.Width || center <= 0)
            return;
        info.Width = width;
        info.CenterChannel = center;
    }
}
