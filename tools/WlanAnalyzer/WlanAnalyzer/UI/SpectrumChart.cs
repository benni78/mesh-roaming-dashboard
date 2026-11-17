using WlanAnalyzer.Wlan;

namespace WlanAnalyzer.UI;

/// <summary>
/// Spektrum eines Bandes: jedes Netz als Trapez ueber seiner belegten
/// Bandbreite, Hoehe = Signalstaerke. Eigene Netze kraeftig, fremde blass.
/// </summary>
internal sealed class SpectrumChart : ChartBase
{
    private const int MinDbm = -100;
    private const int MaxDbm = -20;

    public WifiBand Band { get; set; }
    public IReadOnlyList<BssInfo> Networks { get; set; } = Array.Empty<BssInfo>();
    public Func<BssInfo, bool> IsOwn { get; set; } = _ => false;
    public string? SelectedBssid { get; set; }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        Theme.Prepare(g);
        DrawTitle(g, $"Spektrum {WifiChannels.Name(Band)}", "Signalstärke und belegte Bandbreite je Netz · ★ = eigenes Netz");

        var plot = new Rectangle(S(48), S(46), Width - S(48) - S(14), Height - S(46) - S(30));
        if (plot.Width < 60 || plot.Height < 40)
            return;

        var (fMin, fMax) = WifiChannels.Range(Band);
        float X(double mhz) => plot.Left + (float)((mhz - fMin) / (fMax - fMin) * plot.Width);
        float Y(double dbm) => plot.Bottom - (float)((Math.Clamp(dbm, MinDbm, MaxDbm) - MinDbm) / (MaxDbm - MinDbm) * plot.Height);

        using var dimBrush = new SolidBrush(Theme.TextDim);
        using var gridPen = new Pen(Theme.Grid);
        using var axisPen = new Pen(Theme.Axis);

        if (Band == WifiBand.Band5)
        {
            // DFS-Bereich (Kanal 52-144): Radarerkennung, AP kann den Kanal wechseln muessen
            float x1 = X(5250), x2 = X(5730);
            using var dfs = new SolidBrush(Theme.DfsBand);
            g.FillRectangle(dfs, x1, plot.Top, x2 - x1, plot.Height);
            g.DrawString("DFS", Theme.Small, dimBrush, x1 + 4, plot.Top + 2);
        }

        using (var right = new StringFormat { Alignment = StringAlignment.Far, LineAlignment = StringAlignment.Center })
        {
            for (int d = MinDbm; d <= MaxDbm; d += 10)
            {
                float y = Y(d);
                g.DrawLine(gridPen, plot.Left, y, plot.Right, y);
                g.DrawString(d.ToString(), Theme.Small, dimBrush, new RectangleF(0, y - 8, plot.Left - 4, 16), right);
            }
        }
        g.DrawString("dBm", Theme.Small, dimBrush, plot.Left + S(3), plot.Top + S(2));

        using (var center = new StringFormat { Alignment = StringAlignment.Center })
        {
            float lastLabel = float.MinValue;
            foreach (int ch in WifiChannels.Channels(Band))
            {
                float x = X(WifiChannels.FrequencyOf(Band, ch));
                g.DrawLine(axisPen, x, plot.Bottom, x, plot.Bottom + 4);
                if (x - lastLabel < S(22))
                    continue;
                g.DrawString(ch.ToString(), Theme.Small, dimBrush, x, plot.Bottom + 5, center);
                lastLabel = x;
            }
        }
        g.DrawLine(axisPen, plot.Left, plot.Bottom, plot.Right, plot.Bottom);

        var nets = Networks.Where(n => n.Band == Band)
            .OrderBy(n => IsOwn(n))           // fremde zuerst, eigene oben drueber
            .ThenBy(n => n.Bssid == SelectedBssid)
            .ThenBy(n => n.Rssi)
            .ToList();
        if (nets.Count == 0)
        {
            DrawEmpty(g, plot, $"Keine Netze im {WifiChannels.Name(Band)}-Band gefunden");
            return;
        }

        g.SetClip(new Rectangle(plot.Left, 0, plot.Width, plot.Bottom));
        foreach (var n in nets)
        {
            bool own = IsOwn(n);
            bool selected = n.Bssid == SelectedBssid;
            var color = Theme.ColorFor(n.Ssid, own);
            float x1 = X(n.LowMhz), x2 = X(n.HighMhz), top = Y(n.Rssi), bottom = plot.Bottom;
            float slope = Math.Min((x2 - x1) * 0.18f, S(14));
            var shape = new[]
            {
                new PointF(x1, bottom), new PointF(x1 + slope, top),
                new PointF(x2 - slope, top), new PointF(x2, bottom),
            };

            using (var fill = new SolidBrush(Color.FromArgb(own ? 80 : 28, color)))
                g.FillPolygon(fill, shape);
            using (var pen = new Pen(selected ? Color.White : Color.FromArgb(own ? 255 : 170, color),
                       selected ? 2.5f : own ? 2f : 1f))
                g.DrawLines(pen, shape);
        }
        DrawLabels(g, nets, plot, X, Y);
        g.ResetClip();
    }

    // Namen nach Wichtigkeit setzen (ausgewaehlt, eigene, dann staerkste fremde).
    // Fremde Netze, fuer die kein freier Platz mehr ist, bleiben unbeschriftet -
    // Details stehen in der Liste darunter.
    private void DrawLabels(Graphics g, List<BssInfo> nets, Rectangle plot, Func<double, float> x, Func<double, float> y)
    {
        var placed = new List<RectangleF>();
        var drawn = new HashSet<(string, int)>();
        var ordered = nets
            .OrderByDescending(n => n.Bssid == SelectedBssid)
            .ThenByDescending(IsOwn)
            .ThenByDescending(n => n.Rssi);
        foreach (var n in ordered)
        {
            bool own = IsOwn(n);
            bool selected = n.Bssid == SelectedBssid;
            // dieselbe SSID auf demselben Kanal (mehrere APs/BSSIDs) nur einmal beschriften
            if (!selected && !drawn.Add((n.Ssid, n.CenterFrequencyMhz)))
                continue;

            string text = (own ? "★ " : "") + n.DisplaySsid;
            var font = own || selected ? Theme.Bold : Theme.Small;
            var size = g.MeasureString(text, font);
            float cx = (x(n.LowMhz) + x(n.HighMhz)) / 2;
            float top = y(n.Rssi);
            var rect = new RectangleF(cx - size.Width / 2, top - size.Height - 1, size.Width, size.Height);
            rect.X = Math.Clamp(rect.X, plot.Left, Math.Max(plot.Left, plot.Right - rect.Width));

            bool free = false;
            for (int tries = 0; tries < 6; tries++)
            {
                if (rect.Y >= S(24) && !placed.Any(r => r.IntersectsWith(rect)))
                {
                    free = true;
                    break;
                }
                rect.Y -= size.Height;
            }
            if (!free)
            {
                if (!own && !selected)
                    continue;
                rect.Y = top + 2; // wichtige Netze notfalls in die eigene Flaeche schreiben
            }
            placed.Add(rect);
            var color = selected ? Color.White : Theme.ColorFor(n.Ssid, own);
            using var brush = new SolidBrush(own || selected ? color : Color.FromArgb(220, color));
            g.DrawString(text, font, brush, rect.Location);
        }
    }
}
