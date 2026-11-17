using System.Text.Json;

namespace WlanAnalyzer;

/// <summary>Einstellungen in %APPDATA%\WlanAnalyzer\settings.json.</summary>
public sealed class AppSettings
{
    /// <summary>SSIDs, die als eigene Netze gelten.</summary>
    public List<string> OwnSsids { get; set; } = new();

    /// <summary>Das Netz, mit dem der PC verbunden ist, automatisch als eigenes werten.</summary>
    public bool ConnectedIsOwn { get; set; } = true;

    public int IntervalSeconds { get; set; } = 10;

    public string? AdapterId { get; set; }

    private static readonly string FilePath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "WlanAnalyzer", "settings.json");

    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    public static AppSettings Load()
    {
        try
        {
            if (File.Exists(FilePath))
                return JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(FilePath)) ?? new AppSettings();
        }
        catch (Exception)
        {
            // defekte Datei: mit Standardwerten weitermachen
        }
        return new AppSettings();
    }

    public void Save()
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
            File.WriteAllText(FilePath, JsonSerializer.Serialize(this, JsonOptions));
        }
        catch (Exception)
        {
            // Einstellungen sind nicht kritisch
        }
    }
}
