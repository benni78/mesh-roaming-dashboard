namespace WlanAnalyzer.UI;

/// <summary>Auswahl, welche SSIDs als eigene Netze gelten.</summary>
internal sealed class OwnNetworksForm : Form
{
    private readonly CheckedListBox _list = new() { Dock = DockStyle.Fill, CheckOnClick = true, IntegralHeight = false };
    private readonly TextBox _newSsid = new() { Dock = DockStyle.Fill, PlaceholderText = "SSID, die gerade nicht sichtbar ist" };
    private readonly CheckBox _connectedIsOwn = new()
    {
        Text = "Netz, mit dem dieser PC verbunden ist, automatisch als eigenes werten",
        AutoSize = true,
        Dock = DockStyle.Fill,
    };

    public OwnNetworksForm(IEnumerable<string> visibleSsids, IEnumerable<string> ownSsids, bool connectedIsOwn)
    {
        Text = "Eigene Netze";
        StartPosition = FormStartPosition.CenterParent;
        FormBorderStyle = FormBorderStyle.SizableToolWindow;
        MinimizeBox = MaximizeBox = false;
        ClientSize = new Size(440, 420);
        AutoScaleMode = AutoScaleMode.Dpi;
        Padding = new Padding(10);

        var own = new HashSet<string>(ownSsids, StringComparer.Ordinal);
        foreach (var ssid in visibleSsids.Concat(own).Where(s => s.Length > 0).Distinct(StringComparer.Ordinal)
                     .OrderBy(s => s, StringComparer.CurrentCultureIgnoreCase))
            _list.Items.Add(ssid, own.Contains(ssid));
        _connectedIsOwn.Checked = connectedIsOwn;

        var add = new Button { Text = "Hinzufügen", AutoSize = true };
        add.Click += (_, _) => AddSsid();
        _newSsid.KeyDown += (_, e) =>
        {
            if (e.KeyCode != Keys.Enter)
                return;
            AddSsid();
            e.SuppressKeyPress = true;
        };

        var ok = new Button { Text = "OK", DialogResult = DialogResult.OK, AutoSize = true };
        var cancel = new Button { Text = "Abbrechen", DialogResult = DialogResult.Cancel, AutoSize = true };
        AcceptButton = ok;
        CancelButton = cancel;

        var hint = new Label
        {
            Text = "Angehakte SSIDs gelten als eigene Netze (z. B. alle SSIDs des eigenen Mesh). " +
                   "Sie werden in den Diagrammen kräftig und in kühlen Farben dargestellt.",
            AutoSize = true,
            MaximumSize = new Size(410, 0),
            Dock = DockStyle.Fill,
        };

        var addRow = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, AutoSize = true };
        addRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        addRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        addRow.Controls.Add(_newSsid, 0, 0);
        addRow.Controls.Add(add, 1, 0);

        var buttons = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.RightToLeft, AutoSize = true };
        buttons.Controls.Add(cancel);
        buttons.Controls.Add(ok);

        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1 };
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.Controls.Add(hint, 0, 0);
        layout.Controls.Add(_list, 0, 1);
        layout.Controls.Add(addRow, 0, 2);
        layout.Controls.Add(_connectedIsOwn, 0, 3);
        layout.Controls.Add(buttons, 0, 4);
        Controls.Add(layout);
    }

    public List<string> OwnSsids => _list.CheckedItems.Cast<string>().ToList();

    public bool ConnectedIsOwn => _connectedIsOwn.Checked;

    private void AddSsid()
    {
        string ssid = _newSsid.Text.Trim();
        if (ssid.Length == 0)
            return;
        int idx = _list.Items.IndexOf(ssid);
        if (idx < 0)
            idx = _list.Items.Add(ssid);
        _list.SetItemChecked(idx, true);
        _newSsid.Clear();
    }
}
