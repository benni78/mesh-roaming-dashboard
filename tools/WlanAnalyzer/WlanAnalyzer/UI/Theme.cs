using System.Drawing.Drawing2D;
using System.Drawing.Text;

namespace WlanAnalyzer.UI;

/// <summary>Farben und Schriften, angelehnt an die Live-Karte des Dashboards.</summary>
internal static class Theme
{
    public static readonly Color Background = ColorTranslator.FromHtml("#0d1317");
    public static readonly Color Raised = ColorTranslator.FromHtml("#121a1f");
    public static readonly Color Grid = ColorTranslator.FromHtml("#22313a");
    public static readonly Color Axis = ColorTranslator.FromHtml("#3a4c57");
    public static readonly Color Text = ColorTranslator.FromHtml("#d7e1e8");
    public static readonly Color TextDim = ColorTranslator.FromHtml("#7f919e");
    public static readonly Color Own = ColorTranslator.FromHtml("#2ec4b6");
    public static readonly Color Foreign = ColorTranslator.FromHtml("#f4a261");
    public static readonly Color Good = ColorTranslator.FromHtml("#3aa655");
    public static readonly Color Warn = ColorTranslator.FromHtml("#e9c46a");
    public static readonly Color DfsBand = ColorTranslator.FromHtml("#16212a");

    // Eigene Netze in kuehlen, fremde in warmen Farben - je SSID immer dieselbe.
    private static readonly Color[] OwnPalette =
        new[] { "#2ec4b6", "#4ea8de", "#80ed99", "#48cae4", "#90be6d" }.Select(ColorTranslator.FromHtml).ToArray();

    private static readonly Color[] ForeignPalette =
        new[] { "#f4a261", "#e76f51", "#e9c46a", "#f28482", "#b388eb", "#d4a373", "#ff99c8", "#adb5bd" }
        .Select(ColorTranslator.FromHtml).ToArray();

    public static readonly Font Small = new("Segoe UI", 8f);
    public static readonly Font Normal = new("Segoe UI", 9f);
    public static readonly Font Bold = new("Segoe UI", 9f, FontStyle.Bold);
    public static readonly Font Title = new("Segoe UI Semibold", 10f);

    public static Color ColorFor(string ssid, bool own)
    {
        var palette = own ? OwnPalette : ForeignPalette;
        return palette[Fnv1a(ssid) % (uint)palette.Length];
    }

    public static void Prepare(Graphics g)
    {
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;
    }

    // Stabiler Hash (string.GetHashCode ist je Programmstart zufaellig).
    private static uint Fnv1a(string s)
    {
        uint h = 2166136261;
        foreach (char c in s)
        {
            h ^= c;
            h *= 16777619;
        }
        return h;
    }
}

/// <summary>Grundlage aller Diagramme: doppelt gepuffert, dunkler Hintergrund.</summary>
internal abstract class ChartBase : Control
{
    protected ChartBase()
    {
        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint |
                 ControlStyles.UserPaint | ControlStyles.ResizeRedraw, true);
        BackColor = Theme.Background;
        ForeColor = Theme.Text;
    }

    /// <summary>Logische Pixel (96 dpi) in Geraetepixel.</summary>
    protected int S(int px) => LogicalToDeviceUnits(px);

    protected void DrawTitle(Graphics g, string title, string? subtitle = null)
    {
        using var brush = new SolidBrush(Theme.Text);
        g.DrawString(title, Theme.Title, brush, S(8), S(6));
        if (subtitle is null)
            return;
        float x = S(8) + g.MeasureString(title, Theme.Title).Width + S(6);
        using var dim = new SolidBrush(Theme.TextDim);
        g.DrawString(subtitle, Theme.Small, dim, x, S(8));
    }

    protected void DrawEmpty(Graphics g, Rectangle area, string text)
    {
        using var brush = new SolidBrush(Theme.TextDim);
        using var format = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
        g.DrawString(text, Theme.Normal, brush, area, format);
    }

    protected static void DrawLegendItem(Graphics g, ref float x, float y, Brush swatch, string text, Font font)
    {
        g.FillRectangle(swatch, x, y + 3, 10, 10);
        g.DrawRectangle(Pens.Black, x, y + 3, 10, 10);
        x += 14;
        using var brush = new SolidBrush(Theme.TextDim);
        g.DrawString(text, font, brush, x, y);
        x += g.MeasureString(text, font).Width + 10;
    }
}
