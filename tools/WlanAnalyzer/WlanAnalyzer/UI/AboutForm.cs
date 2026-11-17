using System.Diagnostics;
using System.Reflection;

namespace WlanAnalyzer.UI;

/// <summary>Info-Dialog: Version, Lizenz und Hinweise zu Software Dritter.</summary>
internal sealed class AboutForm : Form
{
    public const string ProjectUrl = "https://github.com/benni78/mesh-roaming-dashboard";

    /// <summary>Version aus der Projektdatei (&lt;Version&gt;), z. B. "1.1.1".</summary>
    public static string AppVersion
    {
        get
        {
            var v = Assembly.GetExecutingAssembly().GetName().Version ?? new Version(0, 0, 0);
            return $"{v.Major}.{v.Minor}.{v.Build}";
        }
    }

    public AboutForm()
    {
        Text = "Info – WLAN-Analyzer";
        AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = new Size(720, 560);
        MinimumSize = new Size(480, 360);
        StartPosition = FormStartPosition.CenterParent;
        Font = new Font("Segoe UI", 9f);
        ShowInTaskbar = false;
        MinimizeBox = false;

        var header = new Label
        {
            Dock = DockStyle.Top,
            Height = 64,
            Padding = new Padding(12, 10, 12, 0),
            Text = $"WLAN-Analyzer {AppVersion}\n" +
                   "Copyright Benjamin Johann (WLAN-Analyzer) · Lizenz: PolyForm Noncommercial 1.0.0 " +
                   "(nicht-kommerzielle Nutzung frei, kommerzielle Lizenzen auf Anfrage)",
        };
        var link = new LinkLabel { Dock = DockStyle.Top, Height = 24, Padding = new Padding(12, 0, 12, 0), Text = ProjectUrl };
        link.LinkClicked += (_, _) => Process.Start(new ProcessStartInfo(ProjectUrl) { UseShellExecute = true });

        var tabs = new TabControl { Dock = DockStyle.Fill };
        tabs.TabPages.Add(TextPage("Software Dritter", ReadResource("THIRD-PARTY-NOTICES.md")));
        tabs.TabPages.Add(TextPage("Lizenz", ReadResource("LICENSE")));

        var close = new Button { Text = "Schließen", DialogResult = DialogResult.OK, Anchor = AnchorStyles.Right | AnchorStyles.Bottom, AutoSize = true };
        var buttons = new FlowLayoutPanel { Dock = DockStyle.Bottom, Height = 42, FlowDirection = FlowDirection.RightToLeft, Padding = new Padding(8) };
        buttons.Controls.Add(close);
        AcceptButton = close;
        CancelButton = close;

        Controls.Add(tabs);
        Controls.Add(buttons);
        Controls.Add(link);
        Controls.Add(header);
    }

    private static TabPage TextPage(string title, string text)
    {
        var box = new TextBox
        {
            Dock = DockStyle.Fill,
            Multiline = true,
            ReadOnly = true,
            ScrollBars = ScrollBars.Both,
            WordWrap = false,
            Font = new Font("Consolas", 9f),
            Text = text.Replace("\r\n", "\n").Replace("\n", "\r\n"),
        };
        var page = new TabPage(title);
        page.Controls.Add(box);
        return page;
    }

    private static string ReadResource(string name)
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(name);
        if (stream is null)
            return $"({name} nicht eingebettet – siehe {ProjectUrl})";
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    }
}
