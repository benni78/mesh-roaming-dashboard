using System.Drawing.Drawing2D;
using WlanAnalyzer.Analysis;
using WlanAnalyzer.Wlan;

namespace WlanAnalyzer.UI;

/// <summary>
/// Verlauf der Kanalauslastung eines Bandes:
///   oben   Heatmap Kanal x Zeit (Farbe = Gesamtauslastung, schraffiert = geschaetzt),
///   unten  fuer den gewaehlten Kanal die Aufteilung eigen/fremd ueber die Zeit.
/// Ein Klick auf eine Zeile der Heatmap waehlt den Kanal.
/// </summary>
internal sealed class LoadHistoryChart : ChartBase
{
    // Farbverlauf 0 % -> 100 % (dunkel -> hell, eigene Skala unabhaengig von eigen/fremd)
    private static readonly Color[] RampStops =
        new[] { "#24203f", "#5c2a6e", "#a83869", "#e2604b", "#f6b44b", "#fbe89c" }
        .Select(ColorTranslator.FromHtml).ToArray();

    private readonly ToolTip _toolTip = new() { InitialDelay = 200, ReshowDelay = 100 };
    private Dictionary<ScanSnapshot, IReadOnlyList<ChannelLoad>> _cache = new();
    private string? _cacheKey;

    // Layout des letzten Zeichnens fuer Maus-Treffer
    private Rectangle _heat, _detail;
    private List<int> _rows = new();
    private float _rowHeight;
    private readonly List<(float X0, float X1, DateTime Time, IReadOnlyList<ChannelLoad> Loads)> _cells = new();
    private int _detailChannel;
    private string? _lastTip;

    public WifiBand Band { get; set; }
    public IReadOnlyList<ScanSnapshot> Snapshots { get; set; } = Array.Empty<ScanSnapshot>();
    public Func<BssInfo, bool> IsOwn { get; set; } = _ => false;

    /// <summary>Aendert sich, wenn sich die Zuordnung eigen/fremd aendert (leert den Cache).</summary>
    public string OwnKey { get; set; } = "";

    /// <summary>Vom Nutzer gewaehlter Kanal; null = automatisch (verbundenes bzw. eigenes Netz).</summary>
    public int? SelectedChannel { get; set; }

    public event Action<int>? ChannelClicked;

    private IReadOnlyList<ChannelLoad> LoadsOf(ScanSnapshot s, Dictionary<ScanSnapshot, IReadOnlyList<ChannelLoad>> next)
    {
        if (!_cache.TryGetValue(s, out var loads))
            loads = ChannelAnalysis.Compute(Band, s.Networks, IsOwn);
        next[s] = loads;
        return loads;
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        Theme.Prepare(g);
        _cells.Clear();
        _rows = new List<int>();
        var window = NetworkTracker.LoadHistoryWindow;
        DrawTitle(g, $"Auslastungsverlauf {WifiChannels.Name(Band)}",
            $"letzte {window.TotalMinutes:0} min · Klick auf einen Kanal zeigt eigen/fremd");
        DrawLegend(g);

        string key = Band + "|" + OwnKey;
        if (key != _cacheKey)
        {
            _cache = new();
            _cacheKey = key;
        }
        var next = new Dictionary<ScanSnapshot, IReadOnlyList<ChannelLoad>>();
        var samples = Snapshots.OrderBy(s => s.Time).Select(s => (s.Time, Loads: LoadsOf(s, next), s.Networks)).ToList();
        _cache = next; // nur noch vorhandene Scans behalten

        int left = S(46), right = S(14);
        var area = new Rectangle(left, S(48), Width - left - right, Height - S(48) - S(22));
        if (area.Width < 80 || area.Height < 80)
            return;
        if (samples.Count == 0)
        {
            DrawEmpty(g, area, "Noch keine Messwerte");
            return;
        }

        var channels = WifiChannels.Channels(Band);
        // Zeilen: nur Kanaele, die im Zeitraum belegt waren (6 GHz hat sonst 59 Zeilen)
        var used = Enumerable.Range(0, channels.Count)
            .Where(i => samples.Any(s => s.Loads[i].TotalPct > 0.5))
            .Select(i => channels[i])
            .ToList();
        if (used.Count == 0)
        {
            DrawEmpty(g, area, $"Keine Belegung im {WifiChannels.Name(Band)}-Band");
            return;
        }
        _rows = used;
        _detailChannel = ResolveDetailChannel(samples[^1].Networks, samples[^1].Loads, channels);
        if (!_rows.Contains(_detailChannel))
        {
            _rows.Add(_detailChannel);
            _rows.Sort();
        }

        int detailHeight = Math.Max(S(70), (int)(area.Height * 0.36));
        _heat = new Rectangle(area.Left, area.Top, area.Width, area.Height - detailHeight - S(24));
        _detail = new Rectangle(area.Left, _heat.Bottom + S(24), area.Width, detailHeight);
        _rowHeight = _heat.Height / (float)_rows.Count;

        var now = DateTime.Now;
        float X(DateTime t) => area.Right - (float)((now - t).TotalSeconds / window.TotalSeconds * area.Width);

        // Zellenbreite: bis zum naechsten Scan, Luecken (Pause) aber nicht ueberbruecken
        double step = samples.Count > 1
            ? samples.Zip(samples.Skip(1), (a, b) => (b.Time - a.Time).TotalSeconds).OrderBy(d => d).ElementAt((samples.Count - 1) / 2)
            : 10;
        var maxGap = TimeSpan.FromSeconds(Math.Max(15, step * 2.5));
        for (int i = 0; i < samples.Count; i++)
        {
            var t = samples[i].Time;
            var end = i + 1 < samples.Count ? samples[i + 1].Time : now;
            if (end - t > maxGap)
                end = t + maxGap;
            float x0 = Math.Max(area.Left, X(t)), x1 = Math.Min(area.Right, X(end) + 0.5f);
            if (x1 > x0)
                _cells.Add((x0, x1, t, samples[i].Loads));
        }

        DrawHeatmap(g, channels);
        DrawDetail(g, channels);
        DrawTimeAxis(g, area, now, window, X);
    }

    /// <summary>Gewaehlter Kanal, sonst Kanal des verbundenen/eigenen Netzes, sonst der vollste.</summary>
    private int ResolveDetailChannel(IReadOnlyList<BssInfo> latest, IReadOnlyList<ChannelLoad> loads, IReadOnlyList<int> channels)
    {
        if (SelectedChannel is int sel && channels.Contains(sel))
            return sel;
        var inBand = latest.Where(n => n.Band == Band).ToList();
        var connected = inBand.FirstOrDefault(n => n.IsConnected);
        if (connected is not null && channels.Contains(connected.Channel))
            return connected.Channel;
        var own = inBand.Where(IsOwn).OrderByDescending(n => n.Rssi).FirstOrDefault();
        if (own is not null && channels.Contains(own.Channel))
            return own.Channel;
        return _rows.OrderByDescending(ch => loads[IndexOf(channels, ch)].TotalPct).First();
    }

    private static int IndexOf(IReadOnlyList<int> channels, int ch)
    {
        for (int i = 0; i < channels.Count; i++)
            if (channels[i] == ch)
                return i;
        return -1;
    }

    private void DrawHeatmap(Graphics g, IReadOnlyList<int> channels)
    {
        using (var bg = new SolidBrush(Theme.Raised))
            g.FillRectangle(bg, _heat);

        var brushes = new Dictionary<(int Level, bool Estimated), Brush>();
        try
        {
            Brush BrushFor(double pct, bool estimated)
            {
                int level = (int)Math.Round(Math.Clamp(pct, 0, 100) / 5); // 21 Stufen
                if (!brushes.TryGetValue((level, estimated), out var b))
                {
                    var c = Ramp(level / 20.0);
                    b = estimated
                        ? new HatchBrush(HatchStyle.WideUpwardDiagonal, c, Color.FromArgb(255, c.R / 3, c.G / 3, c.B / 3))
                        : new SolidBrush(c);
                    brushes[(level, estimated)] = b;
                }
                return b;
            }

            for (int r = 0; r < _rows.Count; r++)
            {
                int idx = IndexOf(channels, _rows[r]);
                float y = _heat.Top + r * _rowHeight;
                foreach (var cell in _cells)
                {
                    var load = cell.Loads[idx];
                    if (load.TotalPct <= 0.5)
                        continue;
                    g.FillRectangle(BrushFor(load.TotalPct, !load.MeasuredPct.HasValue),
                        cell.X0, y, cell.X1 - cell.X0, Math.Max(1, _rowHeight - 1));
                }
            }
        }
        finally
        {
            foreach (var b in brushes.Values)
                b.Dispose();
        }

        // Kanalbeschriftung links; ★ = eigenes Netz im letzten Scan auf/ueber dem Kanal
        var latest = _cells.Count > 0 ? _cells[^1].Loads : null;
        using var dim = new SolidBrush(Theme.TextDim);
        using var warn = new SolidBrush(Theme.Warn);
        using var text = new SolidBrush(Theme.Text);
        using var rightAlign = new StringFormat { Alignment = StringAlignment.Far, LineAlignment = StringAlignment.Center };
        float lastY = float.MinValue;
        for (int r = 0; r < _rows.Count; r++)
        {
            int ch = _rows[r];
            float cy = _heat.Top + r * _rowHeight + _rowHeight / 2;
            bool selected = ch == _detailChannel;
            if (selected)
            {
                using var pen = new Pen(Color.White, 1.5f);
                g.DrawRectangle(pen, _heat.Left - 1, _heat.Top + r * _rowHeight - 1, _heat.Width + 1, _rowHeight + 1);
            }
            if (!selected && cy - lastY < S(11))
                continue; // zu eng: nicht jede Zeile beschriften
            int idx = IndexOf(channels, ch);
            bool own = latest is not null && latest[idx].OwnCount > 0;
            var brush = selected ? text : WifiChannels.IsDfs(Band, ch) ? warn : dim;
            g.DrawString((own ? "★ " : "") + ch, selected ? Theme.Bold : Theme.Small, brush,
                new RectangleF(0, cy - S(8), _heat.Left - S(4), S(16)), rightAlign);
            lastY = cy;
        }
    }

    private void DrawDetail(Graphics g, IReadOnlyList<int> channels)
    {
        int idx = IndexOf(channels, _detailChannel);
        var current = _cells.Count > 0 ? _cells[^1].Loads[idx] : null;
        using var textBrush = new SolidBrush(Theme.Text);
        using var dim = new SolidBrush(Theme.TextDim);
        string head = $"Kanal {_detailChannel}" + (WifiChannels.IsDfs(Band, _detailChannel) ? " (DFS)" : "") + " – eigen/fremd";
        g.DrawString(head, Theme.Bold, textBrush, _detail.Left - S(2), _detail.Top - S(20));
        if (current is not null)
        {
            float x = _detail.Left - S(2) + g.MeasureString(head, Theme.Bold).Width + S(4);
            string now = $"jetzt {current.TotalPct:0} % {(current.MeasuredPct.HasValue ? "gemeldet" : "geschätzt")} · " +
                         $"eigen {current.OwnPct:0} · fremd {current.ForeignPct:0}";
            g.DrawString(now, Theme.Small, dim, x, _detail.Top - S(18));
        }

        using var grid = new Pen(Theme.Grid);
        using var rightAlign = new StringFormat { Alignment = StringAlignment.Far, LineAlignment = StringAlignment.Center };
        for (int p = 0; p <= 100; p += 50)
        {
            float y = _detail.Bottom - p / 100f * _detail.Height;
            g.DrawLine(grid, _detail.Left, y, _detail.Right, y);
            g.DrawString(p + " %", Theme.Small, dim, new RectangleF(0, y - S(8), _detail.Left - S(4), S(16)), rightAlign);
        }

        using var ownSolid = new SolidBrush(Color.FromArgb(210, Theme.Own));
        using var foreignSolid = new SolidBrush(Color.FromArgb(210, Theme.Foreign));
        using var ownHatch = new HatchBrush(HatchStyle.WideUpwardDiagonal, Theme.Own, Color.FromArgb(40, Theme.Own));
        using var foreignHatch = new HatchBrush(HatchStyle.WideUpwardDiagonal, Theme.Foreign, Color.FromArgb(40, Theme.Foreign));
        foreach (var cell in _cells)
        {
            var load = cell.Loads[idx];
            bool measured = load.MeasuredPct.HasValue;
            float w = cell.X1 - cell.X0;
            float ownH = (float)(Math.Min(100, load.OwnPct) / 100 * _detail.Height);
            float foreignH = (float)(Math.Min(100 - Math.Min(100, load.OwnPct), load.ForeignPct) / 100 * _detail.Height);
            if (ownH > 0)
                g.FillRectangle(measured ? ownSolid : ownHatch, cell.X0, _detail.Bottom - ownH, w, ownH);
            if (foreignH > 0)
                g.FillRectangle(measured ? foreignSolid : foreignHatch, cell.X0, _detail.Bottom - ownH - foreignH, w, foreignH);
        }
    }

    private void DrawTimeAxis(Graphics g, Rectangle area, DateTime now, TimeSpan window, Func<DateTime, float> x)
    {
        using var grid = new Pen(Color.FromArgb(90, Theme.Axis));
        using var dim = new SolidBrush(Theme.TextDim);
        using var center = new StringFormat { Alignment = StringAlignment.Center };
        for (int m = 0; m <= window.TotalMinutes; m += 5)
        {
            float px = x(now.AddMinutes(-m));
            g.DrawLine(grid, px, _heat.Top, px, _heat.Bottom);
            g.DrawLine(grid, px, _detail.Top, px, _detail.Bottom);
            g.DrawString(m == 0 ? "jetzt" : $"-{m} min", Theme.Small, dim, px, _detail.Bottom + S(3), center);
        }
    }

    private void DrawLegend(Graphics g)
    {
        float x = S(8), y = S(26);
        using var dim = new SolidBrush(Theme.TextDim);
        var bar = new RectangleF(x + g.MeasureString("0 %", Theme.Small).Width + S(2), y + 3, S(80), 10);
        g.DrawString("0 %", Theme.Small, dim, x, y);
        using (var gradient = new LinearGradientBrush(bar, RampStops[0], RampStops[^1], LinearGradientMode.Horizontal))
        {
            gradient.InterpolationColors = new ColorBlend
            {
                Colors = RampStops,
                Positions = Enumerable.Range(0, RampStops.Length).Select(i => i / (float)(RampStops.Length - 1)).ToArray(),
            };
            g.FillRectangle(gradient, bar);
        }
        x = bar.Right + S(3);
        g.DrawString("100 % Auslastung", Theme.Small, dim, x, y);
        x += g.MeasureString("100 % Auslastung", Theme.Small).Width + S(10);

        using var hatch = new HatchBrush(HatchStyle.WideUpwardDiagonal, Theme.TextDim, Theme.Background);
        using var own = new SolidBrush(Theme.Own);
        using var foreign = new SolidBrush(Theme.Foreign);
        DrawLegendItem(g, ref x, y, hatch, "geschätzt", Theme.Small);
        DrawLegendItem(g, ref x, y, own, "eigen", Theme.Small);
        DrawLegendItem(g, ref x, y, foreign, "fremd", Theme.Small);
    }

    private static Color Ramp(double t)
    {
        t = Math.Clamp(t, 0, 1) * (RampStops.Length - 1);
        int i = Math.Min((int)t, RampStops.Length - 2);
        double f = t - i;
        Color a = RampStops[i], b = RampStops[i + 1];
        return Color.FromArgb(
            (int)(a.R + (b.R - a.R) * f), (int)(a.G + (b.G - a.G) * f), (int)(a.B + (b.B - a.B) * f));
    }

    // ---- Maus ------------------------------------------------------------

    private (int Channel, (float X0, float X1, DateTime Time, IReadOnlyList<ChannelLoad> Loads) Cell)? HitTest(Point p)
    {
        int channel;
        if (_heat.Contains(p) && _rowHeight > 0)
        {
            int r = (int)((p.Y - _heat.Top) / _rowHeight);
            if (r < 0 || r >= _rows.Count)
                return null;
            channel = _rows[r];
        }
        else if (_detail.Contains(p))
            channel = _detailChannel;
        else
            return null;
        foreach (var cell in _cells)
            if (p.X >= cell.X0 && p.X < cell.X1)
                return (channel, cell);
        return null;
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        base.OnMouseMove(e);
        var hit = HitTest(e.Location);
        string? tip = null;
        if (hit is { } h)
        {
            var channels = WifiChannels.Channels(Band);
            var load = h.Cell.Loads[IndexOf(channels, h.Channel)];
            string source = load.MeasuredPct.HasValue
                ? $"Auslastung: {load.TotalPct:0} % (vom AP gemeldet, BSS Load)"
                : $"Belegungsindex: {load.TotalPct:0} % (geschätzt)";
            tip = $"Kanal {h.Channel} · {h.Cell.Time:HH:mm:ss}\n{source}\n" +
                  $"eigene Netze: {load.OwnPct:0} % ({load.OwnCount}), fremde: {load.ForeignPct:0} % ({load.ForeignCount})";
        }
        if (tip == _lastTip)
            return;
        _lastTip = tip;
        if (tip is null)
            _toolTip.Hide(this);
        else
            _toolTip.Show(tip, this, e.X + S(14), e.Y + S(14));
    }

    protected override void OnMouseClick(MouseEventArgs e)
    {
        base.OnMouseClick(e);
        if (e.Button != MouseButtons.Left || !_heat.Contains(e.Location) || _rowHeight <= 0)
            return;
        int r = (int)((e.Y - _heat.Top) / _rowHeight);
        if (r < 0 || r >= _rows.Count)
            return;
        SelectedChannel = _rows[r];
        ChannelClicked?.Invoke(_rows[r]);
        Invalidate();
    }

    protected override void OnMouseLeave(EventArgs e)
    {
        base.OnMouseLeave(e);
        _lastTip = null;
        _toolTip.Hide(this);
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
            _toolTip.Dispose();
        base.Dispose(disposing);
    }
}
