using System.Drawing.Drawing2D;
using WlanAnalyzer.Analysis;
using WlanAnalyzer.Wlan;

namespace WlanAnalyzer.UI;

/// <summary>
/// Kanalauslastung je 20-MHz-Kanal als gestapelte Balken (eigen unten, fremd
/// oben). Volle Balken = vom AP gemeldet (BSS Load), schraffiert = geschaetzt.
/// </summary>
internal sealed class ChannelLoadChart : ChartBase
{
    private readonly ToolTip _toolTip = new() { InitialDelay = 200, ReshowDelay = 100 };
    private readonly List<(RectangleF Hit, ChannelLoad Load)> _hits = new();
    private ChannelLoad? _hovered;

    public WifiBand Band { get; set; }
    public IReadOnlyList<ChannelLoad> Loads { get; set; } = Array.Empty<ChannelLoad>();
    public ChannelRecommendation? Recommendation { get; set; }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        Theme.Prepare(g);
        _hits.Clear();
        DrawTitle(g, $"Kanalauslastung {WifiChannels.Name(Band)}",
            Recommendation is null ? null : "Empfehlung (wenig fremde Belegung): " + Recommendation.Text);
        DrawLegend(g);

        var plot = new Rectangle(S(48), S(50), Width - S(48) - S(14), Height - S(50) - S(36));
        if (plot.Width < 60 || plot.Height < 30 || Loads.Count == 0)
            return;

        using var dimBrush = new SolidBrush(Theme.TextDim);
        using var gridPen = new Pen(Theme.Grid);
        using (var right = new StringFormat { Alignment = StringAlignment.Far, LineAlignment = StringAlignment.Center })
        {
            for (int p = 0; p <= 100; p += 25)
            {
                float y = plot.Bottom - p / 100f * plot.Height;
                g.DrawLine(gridPen, plot.Left, y, plot.Right, y);
                g.DrawString(p + " %", Theme.Small, dimBrush, new RectangleF(0, y - 8, plot.Left - 4, 16), right);
            }
        }

        float slot = plot.Width / (float)Loads.Count;
        float barWidth = Math.Max(3, slot * 0.64f);
        float lastLabel = float.MinValue;
        using var center = new StringFormat { Alignment = StringAlignment.Center };
        using var ownSolid = new SolidBrush(Theme.Own);
        using var foreignSolid = new SolidBrush(Theme.Foreign);
        using var ownHatch = new HatchBrush(HatchStyle.WideUpwardDiagonal, Theme.Own, Color.FromArgb(40, Theme.Own));
        using var foreignHatch = new HatchBrush(HatchStyle.WideUpwardDiagonal, Theme.Foreign, Color.FromArgb(40, Theme.Foreign));
        using var goodBrush = new SolidBrush(Theme.Good);
        using var warnBrush = new SolidBrush(Theme.Warn);

        for (int i = 0; i < Loads.Count; i++)
        {
            var load = Loads[i];
            float cx = plot.Left + slot * i + slot / 2;
            float x = cx - barWidth / 2;
            bool measured = load.MeasuredPct.HasValue;
            float ownH = (float)(load.OwnPct / 100 * plot.Height);
            float foreignH = (float)(load.ForeignPct / 100 * plot.Height);

            if (ownH > 0)
                g.FillRectangle(measured ? ownSolid : ownHatch, x, plot.Bottom - ownH, barWidth, ownH);
            if (foreignH > 0)
                g.FillRectangle(measured ? foreignSolid : foreignHatch, x, plot.Bottom - ownH - foreignH, barWidth, foreignH);
            if (load == _hovered)
            {
                using var hover = new Pen(Color.White, 1.5f);
                g.DrawRectangle(hover, x - 2, plot.Top, barWidth + 4, plot.Height);
            }

            int networks = load.OwnCount + load.ForeignCount;
            if (networks > 0 && slot >= S(16))
            {
                float top = plot.Bottom - ownH - foreignH - S(14);
                g.DrawString(networks.ToString(), Theme.Small, dimBrush, cx, Math.Max(plot.Top - S(14), top), center);
            }

            bool recommended = Recommendation?.Channels.Contains(load.Channel) == true;
            if (recommended)
                g.FillRectangle(goodBrush, x, plot.Bottom + 2, barWidth, 3);
            if (cx - lastLabel >= S(22) || recommended)
            {
                var labelBrush = recommended ? goodBrush : load.Dfs ? warnBrush : dimBrush;
                g.DrawString(load.Channel.ToString(), recommended ? Theme.Bold : Theme.Small, labelBrush, cx, plot.Bottom + 6, center);
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
        using var hatch = new HatchBrush(HatchStyle.WideUpwardDiagonal, Theme.TextDim, Theme.Background);
        using var good = new SolidBrush(Theme.Good);
        using var warn = new SolidBrush(Theme.Warn);
        DrawLegendItem(g, ref x, y, own, "eigene Netze", Theme.Small);
        DrawLegendItem(g, ref x, y, foreign, "fremde Netze", Theme.Small);
        DrawLegendItem(g, ref x, y, hatch, "geschätzt (AP meldet keine Auslastung)", Theme.Small);
        DrawLegendItem(g, ref x, y, good, "empfohlen", Theme.Small);
        if (Band == WifiBand.Band5)
            DrawLegendItem(g, ref x, y, warn, "DFS-Kanal", Theme.Small);
        using var dim = new SolidBrush(Theme.TextDim);
        g.DrawString("Zahl = Netze auf/über dem Kanal", Theme.Small, dim, x, y);
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
        string source = hit.MeasuredPct.HasValue
            ? $"Auslastung: {hit.TotalPct:0} % (vom AP gemeldet, BSS Load)"
            : $"Belegungsindex: {hit.TotalPct:0} % (geschätzt aus Anzahl/Signal der Netze)";
        string text =
            $"Kanal {hit.Channel} · {hit.FrequencyMhz} MHz{(hit.Dfs ? " · DFS" : "")}\n" +
            source + "\n" +
            $"davon eigene Netze: {hit.OwnPct:0} %, fremde: {hit.ForeignPct:0} %\n" +
            $"Netze auf/über dem Kanal: {hit.OwnCount} eigene, {hit.ForeignCount} fremde";
        _toolTip.Show(text, this, e.X + S(14), e.Y + S(14));
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
