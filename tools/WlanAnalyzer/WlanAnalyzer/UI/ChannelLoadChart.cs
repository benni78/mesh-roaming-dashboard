using WlanAnalyzer.Analysis;
using WlanAnalyzer.Wlan;

namespace WlanAnalyzer.UI;

/// <summary>Was ein <see cref="ChannelLoadChart"/> zeigt.</summary>
internal enum ChannelChartMode
{
    /// <summary>Anzahl der Netze je Kanal, gestapelt eigen/fremd.</summary>
    Networks,

    /// <summary>Von den APs gemeldete Auslastung (BSS Load) - nur echte Messwerte.</summary>
    Utilization,
}

/// <summary>
/// Je 20-MHz-Kanal ein Balken - entweder die Anzahl der Netze (eigen unten,
/// fremd oben, massstaeblich zur groessten Anzahl) oder die von Access Points
/// gemeldete Auslastung (BSS Load). Eine geschaetzte Auslastung wird bewusst
/// NICHT in Prozent angezeigt: Meldet kein AP seine Auslastung, laesst sie
/// sich mit einem PC-WLAN-Adapter nicht messen.
/// </summary>
internal sealed class ChannelLoadChart : ChartBase
{
    // Einzelne Datenreihe "gemessene Auslastung" - gegen eigen/fremd und den
    // dunklen Hintergrund auf Unterscheidbarkeit (auch bei Farbsehschwaeche) geprueft
    private static readonly Color UtilColor = ColorTranslator.FromHtml("#9a7fe0");

    private readonly ToolTip _toolTip = new() { InitialDelay = 200, ReshowDelay = 100 };
    private readonly List<(RectangleF Hit, ChannelLoad Load)> _hits = new();
    private ChannelLoad? _hovered;

    public ChannelChartMode Mode { get; set; } = ChannelChartMode.Networks;
    public WifiBand Band { get; set; }
    public IReadOnlyList<ChannelLoad> Loads { get; set; } = Array.Empty<ChannelLoad>();
    public ChannelRecommendation? Recommendation { get; set; }

    /// <summary>Klick auf einen Balken (z. B. um dessen Verlauf zu zeigen).</summary>
    public event Action<int>? ChannelClicked;

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        Theme.Prepare(g);
        _hits.Clear();
        bool networks = Mode == ChannelChartMode.Networks;
        DrawTitle(g,
            networks ? $"Netze je Kanal {WifiChannels.Name(Band)}" : $"Gemessene Auslastung {WifiChannels.Name(Band)}",
            networks
                ? (Recommendation is null ? null : "Empfehlung (wenig fremde Belegung): " + Recommendation.Text)
                : "von Access Points gemeldet (BSS Load)");
        DrawLegend(g);

        var plot = new Rectangle(S(48), S(50), Width - S(48) - S(14), Height - S(50) - S(36));
        if (plot.Width < 60 || plot.Height < 30 || Loads.Count == 0)
            return;

        if (!networks && !Loads.Any(l => l.MeasuredPct.HasValue))
        {
            DrawEmpty(g, plot, $"Kein Access Point im {WifiChannels.Name(Band)}-Band meldet seine Auslastung (BSS Load) – " +
                               "in % nicht messbar. Anhaltspunkt: Anzahl der Netze je Kanal.");
            return;
        }

        // y-Achse: Anzahl (ganzzahlig, bis zur groessten Anzahl) bzw. 0-100 %
        int maxCount = Loads.Max(l => l.OwnCount + l.ForeignCount);
        int step = maxCount <= 5 ? 1 : maxCount <= 10 ? 2 : maxCount <= 25 ? 5 : 10;
        double yMax = networks ? Math.Max(1, (int)Math.Ceiling(maxCount / (double)step) * step) : 100;
        double tick = networks ? step : 25;

        using var dimBrush = new SolidBrush(Theme.TextDim);
        using var gridPen = new Pen(Theme.Grid);
        using (var right = new StringFormat { Alignment = StringAlignment.Far, LineAlignment = StringAlignment.Center })
        {
            for (double v = 0; v <= yMax + 0.001; v += tick)
            {
                float y = plot.Bottom - (float)(v / yMax) * plot.Height;
                g.DrawLine(gridPen, plot.Left, y, plot.Right, y);
                g.DrawString(networks ? v.ToString("0") : v.ToString("0") + " %", Theme.Small, dimBrush,
                    new RectangleF(0, y - 8, plot.Left - 4, 16), right);
            }
        }

        float slot = plot.Width / (float)Loads.Count;
        float barWidth = Math.Max(3, slot * 0.64f);
        float lastLabel = float.MinValue;
        using var center = new StringFormat { Alignment = StringAlignment.Center };
        using var ownBrush = new SolidBrush(Theme.Own);
        using var foreignBrush = new SolidBrush(Theme.Foreign);
        using var utilBrush = new SolidBrush(UtilColor);
        using var goodBrush = new SolidBrush(Theme.Good);
        using var warnBrush = new SolidBrush(Theme.Warn);
        using var textBrush = new SolidBrush(Theme.Text);

        for (int i = 0; i < Loads.Count; i++)
        {
            var load = Loads[i];
            float cx = plot.Left + slot * i + slot / 2;
            float x = cx - barWidth / 2;
            float top = plot.Bottom;
            string? valueLabel = null;

            if (networks)
            {
                float ownH = (float)(load.OwnCount / yMax * plot.Height);
                float foreignH = (float)(load.ForeignCount / yMax * plot.Height);
                float gap = ownH > 0 && foreignH > 0 ? S(2) : 0;
                if (ownH > 0)
                    g.FillRectangle(ownBrush, x, plot.Bottom - ownH, barWidth, ownH);
                if (foreignH > 0)
                    g.FillRectangle(foreignBrush, x, plot.Bottom - ownH - gap - foreignH, barWidth, foreignH);
                top = plot.Bottom - ownH - gap - foreignH;
                int n = load.OwnCount + load.ForeignCount;
                if (n > 0)
                    valueLabel = n.ToString();
            }
            else if (load.MeasuredPct is double pct)
            {
                float h = Math.Max(1, (float)(pct / 100 * plot.Height));
                g.FillRectangle(utilBrush, x, plot.Bottom - h, barWidth, h);
                top = plot.Bottom - h;
                valueLabel = $"{pct:0}";
            }

            if (load == _hovered)
            {
                using var hover = new Pen(Color.White, 1.5f);
                g.DrawRectangle(hover, x - 2, plot.Top, barWidth + 4, plot.Height);
            }
            if (valueLabel is not null && slot >= S(16))
                g.DrawString(valueLabel, Theme.Small, dimBrush, cx, Math.Max(plot.Top - S(14), top - S(14)), center);

            bool recommended = networks && Recommendation?.Channels.Contains(load.Channel) == true;
            if (recommended)
                g.FillRectangle(goodBrush, x, plot.Bottom + 2, barWidth, 3);
            if (cx - lastLabel >= S(22) || recommended)
            {
                // fett = Kanal mit eigenen Netzen
                var labelBrush = recommended ? goodBrush : load.Dfs ? warnBrush : load.OwnCount > 0 ? textBrush : dimBrush;
                g.DrawString(load.Channel.ToString(), recommended || load.OwnCount > 0 ? Theme.Bold : Theme.Small,
                    labelBrush, cx, plot.Bottom + 6, center);
                lastLabel = cx;
            }
            _hits.Add((new RectangleF(cx - slot / 2, plot.Top, slot, plot.Height + S(24)), load));
        }
    }

    private void DrawLegend(Graphics g)
    {
        float x = S(8);
        float y = S(26);
        using var own = new SolidBrush(Theme.Own);
        using var foreign = new SolidBrush(Theme.Foreign);
        using var util = new SolidBrush(UtilColor);
        using var good = new SolidBrush(Theme.Good);
        using var warn = new SolidBrush(Theme.Warn);
        using var dim = new SolidBrush(Theme.TextDim);
        if (Mode == ChannelChartMode.Networks)
        {
            DrawLegendItem(g, ref x, y, own, "eigene Netze", Theme.Small);
            DrawLegendItem(g, ref x, y, foreign, "fremde Netze", Theme.Small);
            DrawLegendItem(g, ref x, y, good, "empfohlen", Theme.Small);
            if (Band == WifiBand.Band5)
                DrawLegendItem(g, ref x, y, warn, "DFS-Kanal", Theme.Small);
            g.DrawString("Anzahl der Netze auf/über dem Kanal · fett = eigenes Netz · Klick = Verlauf", Theme.Small, dim, x, y);
        }
        else
        {
            DrawLegendItem(g, ref x, y, util, "Auslastung in % (höchster gemeldeter Wert, alle Netze)", Theme.Small);
            g.DrawString("Kanäle ohne Meldung bleiben leer · Klick = Verlauf", Theme.Small, dim, x, y);
        }
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        base.OnMouseMove(e);
        var hit = _hits.FirstOrDefault(h => h.Hit.Contains(e.Location)).Load;
        if (hit == _hovered)
            return;
        _hovered = hit;
        Invalidate();
        if (hit is null)
        {
            _toolTip.Hide(this);
            return;
        }
        string measured = hit.MeasuredPct is double pct
            ? $"Auslastung: {pct:0} % (vom AP gemeldet, BSS Load)"
            : "Auslastung: keine Meldung (kein AP auf diesem Kanal sendet BSS Load)";
        string text =
            $"Kanal {hit.Channel} · {hit.FrequencyMhz} MHz{(hit.Dfs ? " · DFS" : "")}\n" +
            $"Netze auf/über dem Kanal: {hit.OwnCount} eigene, {hit.ForeignCount} fremde\n" +
            measured;
        _toolTip.Show(text, this, e.X + S(14), e.Y + S(14));
    }

    protected override void OnMouseClick(MouseEventArgs e)
    {
        base.OnMouseClick(e);
        var hit = _hits.FirstOrDefault(h => h.Hit.Contains(e.Location)).Load;
        if (e.Button == MouseButtons.Left && hit is not null)
            ChannelClicked?.Invoke(hit.Channel);
    }

    protected override void OnMouseLeave(EventArgs e)
    {
        base.OnMouseLeave(e);
        _hovered = null;
        _toolTip.Hide(this);
        Invalidate();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
            _toolTip.Dispose();
        base.Dispose(disposing);
    }
}
