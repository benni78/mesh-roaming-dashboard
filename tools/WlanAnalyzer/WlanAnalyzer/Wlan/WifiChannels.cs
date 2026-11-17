namespace WlanAnalyzer.Wlan;

public enum WifiBand
{
    Band24,
    Band5,
    Band6,
}

/// <summary>Kanal- und Frequenzraster der WLAN-Baender (Europa).</summary>
public static class WifiChannels
{
    public static readonly WifiBand[] AllBands = { WifiBand.Band24, WifiBand.Band5, WifiBand.Band6 };

    private static readonly int[] Channels24 = Enumerable.Range(1, 13).ToArray();

    private static readonly int[] Channels5 =
        Enumerable.Range(0, 8).Select(i => 36 + i * 4)              // 36-64  (UNII-1/2)
        .Concat(Enumerable.Range(0, 12).Select(i => 100 + i * 4))   // 100-144 (UNII-2e)
        .Concat(Enumerable.Range(0, 5).Select(i => 149 + i * 4))    // 149-165 (UNII-3)
        .ToArray();

    private static readonly int[] Channels6 = Enumerable.Range(0, 59).Select(i => 1 + i * 4).ToArray();

    public static WifiBand? BandOf(int mhz) => mhz switch
    {
        >= 2400 and < 2500 => WifiBand.Band24,
        >= 5150 and < 5925 => WifiBand.Band5,
        >= 5925 and < 7200 => WifiBand.Band6,
        _ => null,
    };

    public static int ChannelOf(int mhz)
    {
        if (mhz == 2484) return 14;
        if (mhz >= 2412 && mhz <= 2472) return (mhz - 2407) / 5;
        if (mhz >= 5150 && mhz < 5925) return (mhz - 5000) / 5;
        if (mhz >= 5925 && mhz < 7200) return (mhz - 5950) / 5;
        return 0;
    }

    public static int FrequencyOf(WifiBand band, int channel) => band switch
    {
        WifiBand.Band24 => channel == 14 ? 2484 : 2407 + 5 * channel,
        WifiBand.Band5 => 5000 + 5 * channel,
        _ => 5950 + 5 * channel,
    };

    public static IReadOnlyList<int> Channels(WifiBand band) => band switch
    {
        WifiBand.Band24 => Channels24,
        WifiBand.Band5 => Channels5,
        _ => Channels6,
    };

    /// <summary>Darstellungsbereich der Spektrum-Ansicht in MHz.</summary>
    public static (double Min, double Max) Range(WifiBand band) => band switch
    {
        WifiBand.Band24 => (2399, 2487),
        WifiBand.Band5 => (5165, 5840),
        _ => (5940, 7130),
    };

    /// <summary>5-GHz-Kanaele mit Radarerkennung (DFS) in Europa.</summary>
    public static bool IsDfs(WifiBand band, int channel) => band == WifiBand.Band5 && channel >= 52 && channel <= 144;

    public static string Name(WifiBand band) => band switch
    {
        WifiBand.Band24 => "2,4 GHz",
        WifiBand.Band5 => "5 GHz",
        _ => "6 GHz",
    };
}
