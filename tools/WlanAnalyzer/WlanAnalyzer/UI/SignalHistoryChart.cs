using WlanAnalyzer.Analysis;
using WlanAnalyzer.Wlan;

namespace WlanAnalyzer.UI;

/// <summary>Signalverlauf der Netze eines Bandes ueber die letzten Minuten.</summary>
internal sealed class SignalHistoryChart : ChartBase
{
    private const int MinDbm = -100;
    private const int MaxDbm = -20;

    public WifiBand Band { get; set; }
    public IReadOnlyCollection<TrackedNetwork> Networks { get; set; } = Array.Empty<TrackedNetwork>();
    public Func<BssInfo, bool> IsOwn { get; set; } = _ => false;
    public string? SelectedBssid { get; set; }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        Theme.Prepare(g);
        var window = NetworkTracker.HistoryWindow;
        DrawTitle(g, $"Signalverlauf {WifiChannels.Name(Band)}", $"letzte {window.TotalMinutes:0} min");

        var plot = new Rectangle(S(44), S(30), Width - S(44) - S(96), Height - S(30) - S(24));
        if (plot.Width < 60 || plot.Height < 30)
            return;

        var now = DateTime.Now;
        float X(DateTime t) => plot.Right - (float)((now - t).TotalSeconds / window.TotalSeconds * plot.Width);
        float Y(double dbm) => plot.Bottom - (float)((Math.Clamp(dbm, MinDbm, MaxDbm) - MinDbm) / (MaxDbm - MinDbm) * plot.Height);

        using var dimBrush = new SolidBrush(Theme.TextDim);
        using var gridPen = new Pen(Theme.Grid);
        using (var right = new StringFormat { Alignment = StringAlignment.Far, LineAlignment = StringAlignment.Center })
        {
            for (int d = MinDbm; d <= MaxDbm; d += 20)
            {
                float y = Y(d);
                g.DrawLine(gridPen, plot.Left, y, plot.Right, y);
                g.DrawString(d.ToString(), Theme.Small, dimBrush, new RectangleF(0, y - 8, plot.Left - 4, 16), right);
            }
        }
        using (var center = new StringFormat { Alignment = StringAlignment.Center })
        {
            for (int m = 0; m <= window.TotalMinutes; m += 2)
            {
                float x = X(now.AddMinutes(-m));
                g.DrawLine(gridPen, x, plot.Top, x, plot.Bottom);
                g.DrawString(m == 0 ? "jetzt" : $"-{m} min", Theme.Small, dimBrush, x, plot.Bottom + 3, center);
            }
        }

        var nets = Networks.Where(n => n.Latest.Band == Band && n.History.Count > 0)
            .OrderBy(n => IsOwn(n.Latest))
            .ThenBy(n => n.Latest.Bssid == SelectedBssid)
            .ToList();
        if (nets.Count == 0)
        {
            DrawEmpty(g, plot, "Noch keine Messwerte");
            return;
        }

        g.SetClip(new Rectangle(plot.Left, plot.Top - S(8), plot.Width + S(96), plot.Height + S(16)));
        var labelYs = new List<float>();
        foreach (var n in nets)
        {
            bool own = IsOwn(n.Latest);
            bool selected = n.Latest.Bssid == SelectedBssid;
            var color = selected ? Color.White : Theme.ColorFor(n.Latest.Ssid, own);
            using var pen = new Pen(Color.FromArgb(own || selected ? 255 : 120, color), selected ? 2.5f : own ? 2f : 1f);
            var points = n.History.Select(h => new PointF(X(h.Time), Y(h.Rssi))).ToArray();
            if (points.Length == 1)
            {
                using var dot = new SolidBrush(pen.Color);
                g.FillEllipse(dot, points[0].X - 2, points[0].Y - 2, 4, 4);
            }
            else
                g.DrawLines(pen, points);

            if (!(own || selected) || !n.Present)
                continue;
            // Beschriftung am rechten Rand fuer eigene/ausgewaehlte Netze
            float y = points[^1].Y - 7;
            while (labelYs.Any(l => Math.Abs(l - y) < 13))
                y += 13;
            labelYs.Add(y);
            using var brush = new SolidBrush(color);
            string label = $"{n.Latest.DisplaySsid} {n.Latest.Rssi}";
            g.DrawString(label, Theme.Small, brush, plot.Right + 4, y);
        }
        g.ResetClip();
    }
}
