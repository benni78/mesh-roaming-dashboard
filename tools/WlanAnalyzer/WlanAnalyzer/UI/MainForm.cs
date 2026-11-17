using System.Diagnostics;
using System.Globalization;
using System.Text;
using WlanAnalyzer.Analysis;
using WlanAnalyzer.Scanning;
using WlanAnalyzer.Wlan;

namespace WlanAnalyzer.UI;

/// <summary>
/// Hauptfenster: oben je Band Spektrum + Kanalauslastung (Reiter), unten die
/// Liste aller APs und wahlweise Signal- oder Auslastungsverlauf.
/// </summary>
internal sealed class MainForm : Form
{
    private static readonly int[] Intervals = { 5, 10, 30, 60 };

    private readonly IScanSource _source;
    private readonly string? _screenshotPath;
    private readonly WifiBand _startBand;
    private readonly bool _startWithLoadHistory;
    private readonly AppSettings _settings = AppSettings.Load();
    private readonly NetworkTracker _tracker = new();
    private readonly Dictionary<WifiBand, (TabPage Page, SpectrumChart Spectrum, ChannelLoadChart Load)> _bands = new();
    private readonly Dictionary<WifiBand, ChannelRecommendation> _recommendations = new();

    private readonly ToolStripComboBox _adapterBox = new() { DropDownStyle = ComboBoxStyle.DropDownList, AutoSize = false, Width = 300 };
    private readonly ToolStripComboBox _intervalBox = new() { DropDownStyle = ComboBoxStyle.DropDownList, AutoSize = false, Width = 70 };
    private readonly ToolStripButton _scanButton = new("Jetzt scannen");
    private readonly ToolStripButton _pauseButton = new("Pause") { CheckOnClick = true };
    private readonly ToolStripButton _ownButton = new("Eigene Netze …");
    private readonly ToolStripButton _exportButton = new("CSV-Export …");
    private readonly ToolStripButton _aboutButton = new("Info") { Alignment = ToolStripItemAlignment.Right };
    private readonly Label _infoLabel = new() { Dock = DockStyle.Fill, AutoEllipsis = true, TextAlign = ContentAlignment.MiddleLeft };
    private readonly LinkLabel _locationLink = new()
    {
        Text = "Standort-Einstellungen öffnen",
        Dock = DockStyle.Right,
        AutoSize = true,
        TextAlign = ContentAlignment.MiddleRight,
        Visible = false,
    };
    private readonly TabControl _tabs = new() { Dock = DockStyle.Fill };
    private readonly ListView _list = new()
    {
        Dock = DockStyle.Fill,
        View = View.Details,
        FullRowSelect = true,
        MultiSelect = false,
        HideSelection = false,
    };
    private readonly SignalHistoryChart _history = new() { Dock = DockStyle.Fill };
    private readonly LoadHistoryChart _loadHistory = new() { Dock = DockStyle.Fill };
    private readonly TabControl _historyTabs = new() { Dock = DockStyle.Fill };
    private readonly Dictionary<WifiBand, int?> _selectedChannel = new();
    private readonly ToolStripStatusLabel _statusScan = new() { Spring = true, TextAlign = ContentAlignment.MiddleLeft };
    private readonly ToolStripStatusLabel _statusCount = new();
    private readonly System.Windows.Forms.Timer _timer = new();

    private ScanResult? _last;
    private bool _busy;
    private string? _selectedBssid;
    private int _sortColumn = 3;
    private bool _sortDescending = true;

    public MainForm(IScanSource source, WifiBand startBand, string? screenshotPath, bool startWithLoadHistory = false)
    {
        _startWithLoadHistory = startWithLoadHistory;
        _source = source;
        _screenshotPath = screenshotPath;
        _startBand = startBand;

        Text = $"WLAN-Analyzer {AboutForm.AppVersion} – Kanalnutzung" + (source.IsDemo ? " · DEMO-DATEN" : "");
        AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = new Size(1280, 900);
        MinimumSize = new Size(900, 640);
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 9f);

        BuildLayout();
        WireEvents();
    }

    // ---- Aufbau ----------------------------------------------------------

    private void BuildLayout()
    {
        var toolbar = new ToolStrip { GripStyle = ToolStripGripStyle.Hidden, Padding = new Padding(6, 2, 6, 2) };
        foreach (int s in Intervals)
            _intervalBox.Items.Add($"{s} s");
        toolbar.Items.AddRange(new ToolStripItem[]
        {
            new ToolStripLabel("Adapter:"), _adapterBox,
            new ToolStripSeparator(),
            new ToolStripLabel("Intervall:"), _intervalBox, _scanButton, _pauseButton,
            new ToolStripSeparator(),
            _ownButton, _exportButton, _aboutButton,
        });

        var infoPanel = new Panel { Dock = DockStyle.Top, Height = 30, Padding = new Padding(10, 0, 10, 0), BackColor = Theme.Raised };
        _infoLabel.ForeColor = Theme.Text;
        _locationLink.LinkColor = Theme.Warn;
        infoPanel.Controls.Add(_infoLabel);
        infoPanel.Controls.Add(_locationLink);

        foreach (var band in WifiChannels.AllBands)
        {
            var spectrum = new SpectrumChart { Dock = DockStyle.Fill, Band = band, IsOwn = IsOwn };
            var load = new ChannelLoadChart { Dock = DockStyle.Fill, Band = band };
            load.ChannelClicked += ch => ShowLoadHistory(band, ch);
            var grid = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 2, ColumnCount = 1, BackColor = Theme.Background, Margin = Padding.Empty };
            grid.RowStyles.Add(new RowStyle(SizeType.Percent, 55));
            grid.RowStyles.Add(new RowStyle(SizeType.Percent, 45));
            grid.Controls.Add(spectrum, 0, 0);
            grid.Controls.Add(load, 0, 1);
            var page = new TabPage(WifiChannels.Name(band)) { BackColor = Theme.Background, Padding = Padding.Empty };
            page.Controls.Add(grid);
            _tabs.TabPages.Add(page);
            _bands[band] = (page, spectrum, load);
        }
        _tabs.SelectedIndex = Array.IndexOf(WifiChannels.AllBands, _startBand);

        string[] columns =
        {
            "Eigen", "SSID", "BSSID", "Signal", "Qualität", "Band", "Kanal", "Breite",
            "Standard", "Sicherheit", "Geräte", "Auslastung", "Zuletzt gesehen",
        };
        int[] widths = { 46, 170, 125, 60, 60, 60, 52, 60, 100, 115, 56, 76, 100 };
        for (int i = 0; i < columns.Length; i++)
        {
            var align = i is 3 or 4 or 6 or 7 or 10 or 11 ? HorizontalAlignment.Right : HorizontalAlignment.Left;
            _list.Columns.Add(columns[i], widths[i], align);
        }
        _list.ContextMenuStrip = BuildContextMenu();

        _history.IsOwn = IsOwn;
        _loadHistory.IsOwn = IsOwn;
        _loadHistory.ChannelClicked += ch => _selectedChannel[_loadHistory.Band] = ch;
        var signalPage = new TabPage("Signalverlauf") { BackColor = Theme.Background, Padding = Padding.Empty };
        signalPage.Controls.Add(_history);
        var loadPage = new TabPage("Auslastungsverlauf") { BackColor = Theme.Background, Padding = Padding.Empty };
        loadPage.Controls.Add(_loadHistory);
        _historyTabs.TabPages.Add(signalPage);
        _historyTabs.TabPages.Add(loadPage);
        _historyTabs.SelectedIndex = _startWithLoadHistory ? 1 : 0;

        var bottom = new SplitContainer { Dock = DockStyle.Fill, Orientation = Orientation.Vertical };
        bottom.Panel1.Controls.Add(_list);
        bottom.Panel2.Controls.Add(_historyTabs);

        var main = new SplitContainer { Dock = DockStyle.Fill, Orientation = Orientation.Horizontal };
        main.Panel1.Controls.Add(_tabs);
        main.Panel2.Controls.Add(bottom);

        var status = new StatusStrip();
        status.Items.Add(_statusScan);
        status.Items.Add(_statusCount);

        Controls.Add(main);
        Controls.Add(infoPanel);
        Controls.Add(toolbar);
        Controls.Add(status);

        Load += (_, _) =>
        {
            main.SplitterDistance = (int)(main.Height * 0.62);
            bottom.SplitterDistance = (int)(bottom.Width * 0.62);
        };
    }

    private ContextMenuStrip BuildContextMenu()
    {
        var menu = new ContextMenuStrip();
        var toggleOwn = new ToolStripMenuItem();
        var copySsid = new ToolStripMenuItem("SSID kopieren");
        var copyBssid = new ToolStripMenuItem("BSSID kopieren");
        menu.Items.AddRange(new ToolStripItem[] { toggleOwn, new ToolStripSeparator(), copySsid, copyBssid });

        menu.Opening += (_, e) =>
        {
            var bss = SelectedNetwork();
            if (bss is null)
            {
                e.Cancel = true;
                return;
            }
            bool own = _settings.OwnSsids.Contains(bss.Ssid);
            toggleOwn.Text = own ? $"„{bss.DisplaySsid}“ nicht mehr als eigenes Netz werten" : $"„{bss.DisplaySsid}“ als eigenes Netz markieren";
            toggleOwn.Enabled = bss.Ssid.Length > 0;
        };
        toggleOwn.Click += (_, _) =>
        {
            var bss = SelectedNetwork();
            if (bss is null)
                return;
            if (!_settings.OwnSsids.Remove(bss.Ssid))
                _settings.OwnSsids.Add(bss.Ssid);
            _settings.Save();
            RefreshViews();
        };
        copySsid.Click += (_, _) => { if (SelectedNetwork() is { } b) Clipboard.SetText(b.DisplaySsid); };
        copyBssid.Click += (_, _) => { if (SelectedNetwork() is { } b) Clipboard.SetText(b.Bssid); };
        return menu;
    }

    private void WireEvents()
    {
        _timer.Tick += async (_, _) => await ScanAsync();
        _scanButton.Click += async (_, _) => await ScanAsync();
        _pauseButton.CheckedChanged += (_, _) =>
        {
            _timer.Enabled = !_pauseButton.Checked;
            _pauseButton.Text = _pauseButton.Checked ? "Fortsetzen" : "Pause";
        };
        _intervalBox.SelectedIndexChanged += (_, _) =>
        {
            _settings.IntervalSeconds = Intervals[Math.Max(0, _intervalBox.SelectedIndex)];
            _timer.Interval = _settings.IntervalSeconds * 1000;
            _settings.Save();
        };
        _adapterBox.SelectedIndexChanged += async (_, _) =>
        {
            if (_adapterBox.SelectedItem is AdapterItem item)
            {
                _settings.AdapterId = item.Info.Id.ToString();
                _settings.Save();
                _tracker.Clear();
                _selectedBssid = null;
                _selectedChannel.Clear();
                // Demo: mit 30 min simuliertem Verlauf starten, damit die Verlaeufe etwas zeigen
                if (_source is DemoScanSource demo)
                    foreach (var r in demo.Backfill(NetworkTracker.LoadHistoryWindow, TimeSpan.FromSeconds(_settings.IntervalSeconds)))
                        _tracker.Update(r.Networks, r.Time);
                await ScanAsync();
            }
        };
        _ownButton.Click += (_, _) => EditOwnNetworks();
        _exportButton.Click += (_, _) => ExportCsv();
        _aboutButton.Click += (_, _) =>
        {
            using var about = new AboutForm();
            about.ShowDialog(this);
        };
        _locationLink.LinkClicked += (_, _) =>
            Process.Start(new ProcessStartInfo("ms-settings:privacy-location") { UseShellExecute = true });
        _tabs.SelectedIndexChanged += (_, _) => RefreshHistory();
        _list.SelectedIndexChanged += (_, _) => OnListSelection();
        _list.ColumnClick += (_, e) =>
        {
            _sortDescending = e.Column == _sortColumn ? !_sortDescending : e.Column is 3 or 4 or 10 or 11;
            _sortColumn = e.Column;
            RefreshList();
        };
        FormClosing += (_, _) => _settings.Save();
        Shown += async (_, _) => await StartAsync();
    }

    private async Task StartAsync()
    {
        int interval = Array.IndexOf(Intervals, _settings.IntervalSeconds);
        _intervalBox.SelectedIndex = interval >= 0 ? interval : 1;

        IReadOnlyList<WlanInterfaceInfo> adapters;
        try
        {
            adapters = _source.GetInterfaces();
        }
        catch (Exception ex)
        {
            ShowInfo("WLAN-Adapter konnten nicht abgefragt werden: " + ex.Message, warn: true);
            return;
        }
        if (adapters.Count == 0)
        {
            ShowInfo("Kein WLAN-Adapter gefunden. Zum Ausprobieren: WlanAnalyzer.exe --demo", warn: true);
            return;
        }

        foreach (var a in adapters)
            _adapterBox.Items.Add(new AdapterItem(a));
        int selected = adapters.ToList().FindIndex(a => a.Id.ToString() == _settings.AdapterId);
        // setzt SelectedIndexChanged -> erster Scan
        _adapterBox.SelectedIndex = selected >= 0 ? selected : 0;
        _timer.Interval = _settings.IntervalSeconds * 1000;
        _timer.Start();
        await Task.CompletedTask;
    }

    // ---- Scannen ---------------------------------------------------------

    private async Task ScanAsync()
    {
        if (_busy || _adapterBox.SelectedItem is not AdapterItem adapter)
            return;
        _busy = true;
        _scanButton.Enabled = false;
        _statusScan.Text = "Scanne …";
        try
        {
            var result = await Task.Run(() => _source.Scan(adapter.Info.Id));
            _last = result;
            _tracker.Update(result.Networks, result.Time);
            _locationLink.Visible = false;
            RefreshViews();
            _statusScan.Text = $"Letzter Scan: {result.Time:HH:mm:ss}" +
                               (result.FreshScan ? "" : " (Adapter hat nicht neu gescannt – zwischengespeicherte Liste)");
            if (_screenshotPath is not null)
                SaveScreenshotAndClose(_screenshotPath);
        }
        catch (WlanAccessDeniedException)
        {
            ShowInfo("Windows gibt die WLAN-Scanergebnisse nicht frei. Seit Windows 11 24H2 muss dafür unter " +
                     "Einstellungen → Datenschutz und Sicherheit → Standort „Desktop-Apps Zugriff auf Ihren Standort " +
                     "erlauben“ eingeschaltet sein.", warn: true);
            _locationLink.Visible = true;
            _statusScan.Text = "Kein Zugriff auf Scanergebnisse";
        }
        catch (Exception ex)
        {
            _statusScan.Text = "Scan fehlgeschlagen: " + ex.Message;
        }
        finally
        {
            _busy = false;
            _scanButton.Enabled = true;
        }
    }

    // ---- Anzeige ---------------------------------------------------------

    private bool IsOwn(BssInfo bss)
    {
        if (bss.Ssid.Length == 0)
            return false;
        if (_settings.OwnSsids.Contains(bss.Ssid))
            return true;
        return _settings.ConnectedIsOwn && _last?.ConnectedSsid == bss.Ssid;
    }

    private void RefreshViews()
    {
        var present = _tracker.Present.ToList();
        foreach (var (band, view) in _bands)
        {
            var loads = ChannelAnalysis.Compute(band, present, IsOwn);
            var recommendation = ChannelAnalysis.Recommend(band, loads);
            _recommendations[band] = recommendation;
            int count = present.Count(n => n.Band == band);

            view.Page.Text = $"{WifiChannels.Name(band)} ({count})";
            view.Spectrum.Networks = present;
            view.Spectrum.SelectedBssid = _selectedBssid;
            view.Load.Loads = loads;
            view.Load.Recommendation = count > 0 ? recommendation : null;
            view.Spectrum.Invalidate();
            view.Load.Invalidate();
        }
        RefreshList();
        RefreshHistory();
        RefreshInfo(present);
    }

    private void RefreshInfo(List<BssInfo> present)
    {
        var parts = new List<string>();
        var connected = present.FirstOrDefault(n => n.IsConnected);
        if (connected is not null)
            parts.Add($"Verbunden: {connected.DisplaySsid} · {connected.Bssid} · Kanal {connected.Channel} " +
                      $"({WifiChannels.Name(connected.Band)}, {connected.Width} MHz) · {connected.Rssi} dBm");
        else
            parts.Add("Nicht verbunden");
        foreach (var band in WifiChannels.AllBands)
        {
            if (present.Any(n => n.Band == band) && _recommendations.TryGetValue(band, out var r))
                parts.Add($"Empfehlung {WifiChannels.Name(band)}: {r.Text}");
        }
        ShowInfo(string.Join("   ·   ", parts), warn: false);

        int own = present.Count(IsOwn);
        _statusCount.Text = $"{present.Count} APs sichtbar · {own} eigene · {present.Count - own} fremde";
    }

    private void ShowInfo(string text, bool warn)
    {
        _infoLabel.Text = text;
        _infoLabel.ForeColor = warn ? Theme.Warn : Theme.Text;
    }

    private void RefreshHistory()
    {
        var band = WifiChannels.AllBands[Math.Max(0, _tabs.SelectedIndex)];
        _history.Band = band;
        _history.Networks = _tracker.All;
        _history.SelectedBssid = _selectedBssid;
        _history.Invalidate();

        _loadHistory.Band = band;
        _loadHistory.Snapshots = _tracker.Snapshots;
        _loadHistory.SelectedChannel = _selectedChannel.GetValueOrDefault(band);
        _loadHistory.OwnKey = OwnKey();
        _loadHistory.Invalidate();
    }

    /// <summary>Alles, wovon die Zuordnung eigen/fremd abhaengt.</summary>
    private string OwnKey() =>
        string.Join("\n", _settings.OwnSsids.OrderBy(s => s, StringComparer.Ordinal)) +
        "|" + _settings.ConnectedIsOwn + "|" + (_settings.ConnectedIsOwn ? _last?.ConnectedSsid : null);

    private void ShowLoadHistory(WifiBand band, int channel)
    {
        _selectedChannel[band] = channel;
        _historyTabs.SelectedIndex = 1;
        RefreshHistory();
    }

    private void RefreshList()
    {
        var now = DateTime.Now;
        var rows = _tracker.All.OrderBy(n => n, Comparer<TrackedNetwork>.Create(CompareRows)).ToList();

        _list.BeginUpdate();
        _list.Items.Clear();
        foreach (var t in rows)
        {
            var n = t.Latest;
            bool own = IsOwn(n);
            var item = new ListViewItem(new[]
            {
                own ? "★" : "",
                n.DisplaySsid + (n.IsConnected ? "  (verbunden)" : ""),
                n.Bssid,
                $"{n.Rssi} dBm",
                $"{n.LinkQuality} %",
                WifiChannels.Name(n.Band),
                n.Channel.ToString(),
                $"{n.Width} MHz",
                n.Standard,
                n.Security,
                n.StationCount?.ToString() ?? "–",
                n.UtilizationPct is double u ? $"{u:0} %" : "–",
                t.Present ? "jetzt" : $"vor {(int)(now - t.LastSeen).TotalSeconds} s",
            })
            {
                Tag = t,
                UseItemStyleForSubItems = true,
            };
            if (!t.Present)
                item.ForeColor = SystemColors.GrayText;
            else if (own)
                item.BackColor = Color.FromArgb(225, 246, 243);
            if (n.IsConnected)
                item.Font = new Font(_list.Font, FontStyle.Bold);
            if (n.Bssid == _selectedBssid)
                item.Selected = true;
            _list.Items.Add(item);
        }
        _list.EndUpdate();
    }

    private int CompareRows(TrackedNetwork a, TrackedNetwork b)
    {
        var x = a.Latest;
        var y = b.Latest;
        int result = _sortColumn switch
        {
            0 => IsOwn(x).CompareTo(IsOwn(y)),
            1 => string.Compare(x.DisplaySsid, y.DisplaySsid, StringComparison.CurrentCultureIgnoreCase),
            2 => string.CompareOrdinal(x.Bssid, y.Bssid),
            3 => x.Rssi.CompareTo(y.Rssi),
            4 => x.LinkQuality.CompareTo(y.LinkQuality),
            5 => x.Band.CompareTo(y.Band),
            6 => (x.Band, x.Channel).CompareTo((y.Band, y.Channel)),
            7 => x.Width.CompareTo(y.Width),
            8 => string.CompareOrdinal(x.Standard, y.Standard),
            9 => string.CompareOrdinal(x.Security, y.Security),
            10 => (x.StationCount ?? -1).CompareTo(y.StationCount ?? -1),
            11 => (x.UtilizationPct ?? -1).CompareTo(y.UtilizationPct ?? -1),
            12 => a.LastSeen.CompareTo(b.LastSeen),
            _ => 0,
        };
        if (_sortDescending)
            result = -result;
        // nicht mehr sichtbare Netze immer ans Ende, sonst stabil nach BSSID
        if (result == 0)
            result = string.CompareOrdinal(x.Bssid, y.Bssid);
        return a.Present == b.Present ? result : a.Present ? -1 : 1;
    }

    private BssInfo? SelectedNetwork() =>
        _list.SelectedItems.Count == 1 && _list.SelectedItems[0].Tag is TrackedNetwork t ? t.Latest : null;

    private void OnListSelection()
    {
        var bss = SelectedNetwork();
        if (bss is null || bss.Bssid == _selectedBssid)
            return;
        _selectedBssid = bss.Bssid;
        // zum passenden Band wechseln, damit das Netz im Diagramm sichtbar ist
        _tabs.SelectedIndex = Array.IndexOf(WifiChannels.AllBands, bss.Band);
        foreach (var (_, view) in _bands)
        {
            view.Spectrum.SelectedBssid = _selectedBssid;
            view.Spectrum.Invalidate();
        }
        RefreshHistory();
    }

    // ---- Aktionen --------------------------------------------------------

    private void EditOwnNetworks()
    {
        var visible = _tracker.All.Select(t => t.Latest.Ssid);
        using var dialog = new OwnNetworksForm(visible, _settings.OwnSsids, _settings.ConnectedIsOwn);
        if (dialog.ShowDialog(this) != DialogResult.OK)
            return;
        _settings.OwnSsids = dialog.OwnSsids;
        _settings.ConnectedIsOwn = dialog.ConnectedIsOwn;
        _settings.Save();
        RefreshViews();
    }

    private void ExportCsv()
    {
        using var dialog = new SaveFileDialog
        {
            Filter = "CSV (Semikolon)|*.csv",
            FileName = $"wlan-scan-{DateTime.Now:yyyyMMdd-HHmmss}.csv",
        };
        if (dialog.ShowDialog(this) != DialogResult.OK)
            return;

        var de = CultureInfo.GetCultureInfo("de-DE");
        var sb = new StringBuilder();
        sb.AppendLine("Zeit;Eigen;SSID;BSSID;Signal_dBm;Qualitaet_Prozent;Band;Kanal;Mitte_MHz;Breite_MHz;Standard;Sicherheit;Geraete;Auslastung_Prozent;Verbunden");
        foreach (var t in _tracker.All.Where(t => t.Present))
        {
            var n = t.Latest;
            sb.AppendLine(string.Join(";",
                t.LastSeen.ToString("yyyy-MM-dd HH:mm:ss"),
                IsOwn(n) ? "ja" : "nein",
                Csv(n.Ssid), n.Bssid, n.Rssi, n.LinkQuality,
                WifiChannels.Name(n.Band), n.Channel, n.CenterFrequencyMhz, n.Width,
                Csv(n.Standard), Csv(n.Security),
                n.StationCount?.ToString() ?? "",
                n.UtilizationPct?.ToString("0.0", de) ?? "",
                n.IsConnected ? "ja" : "nein"));
        }
        File.WriteAllText(dialog.FileName, sb.ToString(), new UTF8Encoding(true));
        _statusScan.Text = "Exportiert: " + dialog.FileName;
    }

    private static string Csv(string s) => s.Contains(';') || s.Contains('"') ? "\"" + s.Replace("\"", "\"\"") + "\"" : s;

    private void SaveScreenshotAndClose(string path)
    {
        // Nur fuer Doku-Screenshots (--screenshot <datei.png>)
        BeginInvoke(() =>
        {
            using var bmp = new Bitmap(Width, Height);
            DrawToBitmap(bmp, new Rectangle(Point.Empty, Size));
            bmp.Save(path, System.Drawing.Imaging.ImageFormat.Png);
            Close();
        });
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
            _timer.Dispose();
        base.Dispose(disposing);
    }

    private sealed record AdapterItem(WlanInterfaceInfo Info)
    {
        public override string ToString() => Info.Description + (Info.Connected ? " (verbunden)" : "");
    }
}
