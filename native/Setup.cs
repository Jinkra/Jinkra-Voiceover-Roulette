// Jinkra Voiceover Roulette 安装与卸载向导。
// 同一份源码编译两次：带 payload.zip 资源的是安装包，不带的是放进安装目录的卸载程序。
// 只用 .NET Framework 4.x 自带的 csc（C# 5），不要使用字符串内插、?. 等新语法。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("Jinkra Voiceover Roulette 安装程序")]
[assembly: AssemblyProduct("Jinkra Voiceover Roulette")]
[assembly: AssemblyCompany("Jinkra")]

internal sealed class RouletteSetup : Form {
    internal const string Product = "Jinkra Voiceover Roulette";
    internal const string ProductExe = "Jinkra Voiceover Roulette.exe";
    internal const string Uninstaller = "Uninstall Jinkra Voiceover Roulette.exe";
    internal const string Manifest = "install-manifest.txt";
    private const string ShortcutName = "Jinkra Voiceover Roulette.lnk";
    private const string InstallKey = @"Software\Jinkra\VoiceoverRoulette";
    private const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\JinkraVoiceoverRoulette";
    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string Repository = "https://github.com/Jinkra/Jinkra-Voiceover-Roulette";
    // 用户数据与程序放在同一目录（便携布局），卸载时按「保留用户数据」决定是否删除。
    private static readonly string[] UserData = {
        "config.json", "sounds.json", "sounds.json.bak", "sounds.json.tmp", "sounds",
        ".jinkra-activation", "jinkra_roulette.log", "models",
    };

    private const int BrandWidth = 258;
    private static readonly Color Rail = Color.FromArgb(36, 42, 38);
    private static readonly Color Linen = Color.FromArgb(241, 242, 233);
    private static readonly Color RailMuted = Color.FromArgb(171, 201, 188);
    private static readonly Color Ink = Color.FromArgb(34, 44, 37);
    private static readonly Color Accent = Color.FromArgb(48, 114, 99);
    private static readonly Color AccentHover = Color.FromArgb(36, 92, 79);
    private static readonly Color Muted = Color.FromArgb(70, 96, 86);
    private static readonly Color Surface = Color.FromArgb(248, 250, 247);
    private static readonly Color Soft = Color.FromArgb(229, 236, 231);
    private static readonly Color SoftHover = Color.FromArgb(216, 227, 220);
    private static readonly Color Danger = Color.FromArgb(157, 45, 60);

    private readonly Image logo;
    private readonly TextBox directory = new TextBox();
    private readonly Label headline;
    private readonly Label detail;
    private readonly Label status;
    private readonly Button browse;
    private readonly Button next;
    private readonly Button back;
    private readonly Button close;
    private readonly CheckBox desktopShortcut;
    private readonly CheckBox launchAfter;
    private readonly CheckBox keepData;
    private readonly CheckBox removeCable;
    private readonly bool removing;
    private readonly ProgressBar progress = new ProgressBar();
    private bool running;
    private bool complete;

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern int SetCurrentProcessExplicitAppUserModelID(string id);
    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);
    [DllImport("user32.dll")]
    private static extern bool ReleaseCapture();
    [DllImport("user32.dll")]
    private static extern IntPtr SendMessage(IntPtr handle, int message, IntPtr wParam, IntPtr lParam);

    private RouletteSetup(Image logo, string uninstallDirectory) {
        this.logo = logo;
        removing = uninstallDirectory != null;
        Text = removing ? Product + " 卸载向导" : Product + " 安装向导";
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(758, 518);
        BackColor = Surface;
        DoubleBuffered = true;
        Font = new Font("Microsoft YaHei UI", 10);
        using (GraphicsPath outline = Rounded(new RectangleF(0, 0, Width, Height), 24)) Region = new Region(outline);
        MouseDown += delegate(object sender, MouseEventArgs args) {
            if (args.Button == MouseButtons.Left && args.Y < 53) {
                ReleaseCapture();
                SendMessage(Handle, 0xa1, new IntPtr(2), IntPtr.Zero);
            }
        };
        FormClosing += delegate(object sender, FormClosingEventArgs args) { if (running) args.Cancel = true; };

        headline = PlaceLabel(removing ? "卸载 Jinkra Voiceover Roulette" : "安装 Jinkra Voiceover Roulette",
            300, 77, 430, 44, 19, Ink, FontStyle.Bold);
        detail = PlaceLabel(removing ? "将从这台电脑移除程序及其快捷方式。" : "选择安装位置。安装后可从开始菜单打开。",
            301, 127, 402, 28, 10, Muted, FontStyle.Regular);
        PlaceLabel("安装目录", 301, 177, 380, 23, 10, Ink, FontStyle.Bold);

        directory.SetBounds(316, 216, 291, 24);
        directory.BorderStyle = BorderStyle.None;
        directory.BackColor = Color.White;
        directory.ForeColor = Ink;
        directory.Text = uninstallDirectory ?? DefaultDirectory();
        directory.ReadOnly = removing;
        directory.AccessibleName = "安装目录";
        Controls.Add(directory);
        browse = PlaceButton("浏览…", 617, 204, 89, 42, false);
        browse.Click += ChooseFolder;

        desktopShortcut = PlaceChoice("创建桌面快捷方式", 262, true);
        launchAfter = PlaceChoice("安装完成后打开 Jinkra Voiceover Roulette", 291, true);
        browse.Visible = desktopShortcut.Visible = launchAfter.Visible = !removing;
        keepData = PlaceChoice("保留用户数据（设置、音效、降噪模型和激活记录）", 262, true);
        keepData.Visible = removing;
        removeCable = PlaceChoice("同时卸载虚拟麦克风（VB-CABLE）", 291, false);
        removeCable.Visible = removing && CableInstalled();
        status = PlaceLabel(removing ? "保留设置、音效和激活记录，重新安装到同一目录即可继续使用。"
                                     : "仅为当前 Windows 用户安装，不需要管理员权限。",
            301, 332, 409, 60, 9, Muted, FontStyle.Regular);
        removeCable.CheckedChanged += delegate {
            if (removeCable.Checked) SetStatus("卸载虚拟麦克风需要确认 Windows 管理员提示。其他软件若也在用 VB-CABLE，会一起失去这个设备。", false);
            else SetStatus(keepData.Checked ? "保留设置、音效和激活记录，重新安装到同一目录即可继续使用。"
                                            : "设置、音效和激活记录将被一并删除。", !keepData.Checked);
        };
        keepData.CheckedChanged += delegate {
            SetStatus(keepData.Checked ? "保留设置、音效和激活记录，重新安装到同一目录即可继续使用。"
                                       : "设置、音效和激活记录将被一并删除。", !keepData.Checked);
        };
        progress.SetBounds(302, 412, 404, 10);
        progress.Visible = false;
        progress.AccessibleName = removing ? "卸载进度" : "安装进度";
        Controls.Add(progress);

        back = PlaceButton("取消", 466, 448, 98, 43, false);
        back.Click += delegate { Close(); };
        next = PlaceButton(removing ? "卸载" : "立即安装", 577, 448, 129, 43, true);
        if (removing) {
            next.BackColor = Danger;
            next.FlatAppearance.MouseOverBackColor = Color.FromArgb(135, 34, 48);
        }
        next.Click += delegate {
            if (removing) { if (complete) Close(); else BeginUninstall(); }
            else if (complete) OpenProduct();
            else BeginInstall();
        };
        close = PlaceButton("×", 699, 17, 40, 34, false);
        close.AccessibleName = removing ? "关闭卸载向导" : "关闭安装向导";
        close.Click += delegate { Close(); };
        AcceptButton = removing ? back : next;
        CancelButton = back;
        Shown += delegate { ActiveControl = removing ? back : next; directory.Select(directory.Text.Length, 0); };
        if (SystemInformation.IsMenuAnimationEnabled) {
            Opacity = 0;
            var fade = new Timer { Interval = 16 };
            fade.Tick += delegate {
                Opacity = Math.Min(1, Opacity + 0.09);
                if (Opacity >= 1) fade.Dispose();
            };
            Shown += delegate { fade.Start(); };
        }
    }

    // ---------------------------------------------------------------- 界面

    // Windows 11 会给无边框窗口再画一圈 1 像素的系统边框，与自绘圆角叠在一起会在四边露出浅色线。
    protected override void OnHandleCreated(EventArgs e) {
        base.OnHandleCreated(e);
        int none = unchecked((int)0xFFFFFFFE);  // DWMWA_COLOR_NONE
        int square = 1;                          // DWMWCP_DONOTROUND：圆角由窗口区域负责
        try {
            DwmSetWindowAttribute(Handle, 34, ref none, sizeof(int));   // DWMWA_BORDER_COLOR
            DwmSetWindowAttribute(Handle, 33, ref square, sizeof(int)); // DWMWA_WINDOW_CORNER_PREFERENCE
        } catch (DllNotFoundException) {} catch (EntryPointNotFoundException) {}
    }

    private Label PlaceLabel(string text, int x, int y, int width, int height, int size, Color color, FontStyle style) {
        var label = new Label { Text = text, ForeColor = color, Font = new Font("Microsoft YaHei UI", size, style) };
        label.SetBounds(x, y, width, height);
        Controls.Add(label);
        return label;
    }

    private Button PlaceButton(string text, int x, int y, int width, int height, bool primary) {
        var button = new Button {
            Text = text, FlatStyle = FlatStyle.Flat, BackColor = primary ? Accent : Soft,
            ForeColor = primary ? Color.White : Ink, UseVisualStyleBackColor = false, Cursor = Cursors.Hand
        };
        button.FlatAppearance.BorderSize = 0;
        button.FlatAppearance.MouseOverBackColor = primary ? AccentHover : SoftHover;
        button.SetBounds(x, y, width, height);
        using (GraphicsPath shape = Rounded(new RectangleF(0, 0, width, height), 10)) button.Region = new Region(shape);
        Controls.Add(button);
        return button;
    }

    private CheckBox PlaceChoice(string text, int y, bool selected) {
        var choice = new CheckBox { Text = text, Checked = selected, ForeColor = Ink, Cursor = Cursors.Hand };
        choice.SetBounds(301, y, 405, 26);
        Controls.Add(choice);
        return choice;
    }

    protected override void OnPaint(PaintEventArgs e) {
        base.OnPaint(e);
        Graphics g = e.Graphics;
        // 先关着抗锯齿铺满左栏：开着时整数坐标的矩形边缘只覆盖半个像素，
        // 窗口最左一列和最上一行会和浅色底混成一条灰白线。
        g.SmoothingMode = SmoothingMode.None;
        using (var rail = new SolidBrush(Rail)) g.FillRectangle(rail, 0, 0, BrandWidth, Height);
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
        // 轮盘刻度：与应用里带刻度的轮盘呼应
        using (var ring = new Pen(Color.FromArgb(70, 171, 201, 188), 1))
        using (var tick = new Pen(Color.FromArgb(110, 171, 201, 188), 2)) {
            var center = new PointF(BrandWidth / 2f, 207);
            for (int offset = 0; offset < 3; offset++) {
                float r = 150 - offset * 14;
                g.DrawEllipse(ring, center.X - r, center.Y - r, r * 2, r * 2);
            }
            for (int i = 0; i < 24; i++) {
                double a = i * Math.PI / 12;
                float r1 = i % 3 == 0 ? 112 : 117, r2 = 122;
                g.DrawLine(tick, center.X + (float)Math.Cos(a) * r1, center.Y + (float)Math.Sin(a) * r1,
                                 center.X + (float)Math.Cos(a) * r2, center.Y + (float)Math.Sin(a) * r2);
            }
        }
        DrawRoundLogo(g, new RectangleF((BrandWidth - 150) / 2f, 132, 150, 150));
        using (var light = new SolidBrush(Linen))
        using (var subtle = new SolidBrush(RailMuted))
        using (var display = new Font("Segoe UI", 21, FontStyle.Bold))
        using (var sub = new Font("Segoe UI", 12, FontStyle.Bold))
        using (var small = new Font("Consolas", 11))
        using (var centered = new StringFormat { Alignment = StringAlignment.Center }) {
            g.DrawString("Jinkra", display, light, new RectangleF(0, 322, BrandWidth, 40), centered);
            g.DrawString("Voiceover Roulette", sub, light, new RectangleF(0, 362, BrandWidth, 26), centered);
            g.DrawString("Windows x64", small, subtle, new RectangleF(0, 404, BrandWidth, 22), centered);
            string version = Assembly.GetExecutingAssembly().GetName().Version.ToString(3);
            g.DrawString("版本 " + version, small, subtle, new RectangleF(0, 430, BrandWidth, 22), centered);
        }
        using (GraphicsPath input = Rounded(new RectangleF(301, 204, 307, 42), 10))
        using (var border = new Pen(Color.FromArgb(189, 205, 196)))
        using (var white = new SolidBrush(Color.White)) {
            g.FillPath(white, input);
            g.DrawPath(border, input);
        }
    }

    private Bitmap roundLogo;

    // LOGO 原图是方形深蓝底上的圆形徽章，只取圆形部分（向内收一点，去掉外圈底色），边缘抗锯齿。
    private void DrawRoundLogo(Graphics g, RectangleF bounds) {
        if (roundLogo == null) {
            roundLogo = new Bitmap((int)bounds.Width, (int)bounds.Height);
            using (Graphics scaled = Graphics.FromImage(roundLogo)) {
                scaled.InterpolationMode = InterpolationMode.HighQualityBicubic;
                scaled.PixelOffsetMode = PixelOffsetMode.HighQuality;
                scaled.DrawImage(logo, new Rectangle(0, 0, roundLogo.Width, roundLogo.Height));
            }
        }
        float inset = bounds.Width * 0.03f;
        using (var brush = new TextureBrush(roundLogo, WrapMode.Clamp)) {
            brush.TranslateTransform(bounds.X, bounds.Y);
            g.FillEllipse(brush, bounds.X + inset, bounds.Y + inset, bounds.Width - inset * 2, bounds.Height - inset * 2);
        }
    }

    protected override void Dispose(bool disposing) {
        if (disposing && roundLogo != null) { roundLogo.Dispose(); roundLogo = null; }
        base.Dispose(disposing);
    }

    private void SetStatus(string message, bool error) {
        status.Text = message;
        status.ForeColor = error ? Danger : Muted;
    }

    private void ChooseFolder(object sender, EventArgs e) {
        using (var picker = new FolderBrowserDialog { Description = "选择 Jinkra Voiceover Roulette 的安装位置", ShowNewFolderButton = true }) {
            if (Directory.Exists(directory.Text)) picker.SelectedPath = directory.Text;
            if (picker.ShowDialog(this) == DialogResult.OK) {
                directory.Text = IsInstalled(picker.SelectedPath) ? picker.SelectedPath : Path.Combine(picker.SelectedPath, Product);
            }
        }
    }

    // ---------------------------------------------------------------- 安装

    private async void BeginInstall() {
        string target;
        try { target = ValidateDirectory(directory.Text, false); }
        catch (Exception error) { SetStatus(error.Message, true); return; }
        directory.Text = target;
        running = true;
        directory.Enabled = browse.Enabled = next.Enabled = back.Enabled = close.Enabled = false;
        desktopShortcut.Enabled = launchAfter.Enabled = false;
        bool desktop = desktopShortcut.Checked;
        headline.Text = "正在安装";
        detail.Text = "正在写入程序文件和开始菜单快捷方式。";
        SetStatus("正在准备安装文件…", false);
        progress.Style = ProgressBarStyle.Continuous;
        progress.Value = 0;
        progress.Visible = true;
        var updates = new Progress<int>(percent => { progress.Value = Math.Max(0, Math.Min(100, percent)); });
        try {
            await Task.Run(() => Install(target, updates, desktop));
            complete = true;
            headline.Text = "安装完成";
            detail.Text = "可以从开始菜单或桌面打开 Jinkra Voiceover Roulette。";
            SetStatus("首次启动后，在「语音输出」里点「安装虚拟麦克风」即可一键装好虚拟麦克风。", false);
            progress.Value = 100;
            next.Text = launchAfter.Checked ? "完成并打开" : "完成";
            back.Visible = false;
        } catch (Exception error) {
            headline.Text = "安装未完成";
            detail.Text = "可以检查安装目录后重试。";
            SetStatus(error.Message, true);
            progress.Visible = false;
            directory.Enabled = browse.Enabled = true;
            desktopShortcut.Enabled = launchAfter.Enabled = true;
        } finally {
            running = false;
            next.Enabled = back.Enabled = close.Enabled = true;
        }
    }

    private void OpenProduct() {
        if (!launchAfter.Checked) { Close(); return; }
        try {
            string exe = Path.Combine(directory.Text, ProductExe);
            Process.Start(new ProcessStartInfo(exe) { WorkingDirectory = directory.Text, UseShellExecute = true }).Dispose();
            Close();
        } catch (Exception error) { SetStatus("无法打开 Jinkra Voiceover Roulette。" + error.Message, true); }
    }

    internal static void Install(string directory, IProgress<int> progress, bool desktop) {
        EnsureClosed(directory);
        Directory.CreateDirectory(directory);
        var installed = new List<string>();
        string root = Path.GetFullPath(directory).TrimEnd('\\') + "\\";
        using (Stream source = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip")) {
            if (source == null) throw new IOException("安装包不完整，请重新下载。");
            using (var archive = new ZipArchive(source, ZipArchiveMode.Read)) {
                int done = 0;
                foreach (ZipArchiveEntry entry in archive.Entries) {
                    done++;
                    if (entry.FullName.EndsWith("/")) continue;
                    string relative = entry.FullName.Replace('/', '\\');
                    string target = Path.GetFullPath(Path.Combine(root, relative));
                    if (!target.StartsWith(root, StringComparison.OrdinalIgnoreCase)) throw new IOException("安装包内容异常。");
                    // 示例音效只在第一次安装时放入；用户删改过的不再覆盖。
                    bool sample = relative.StartsWith("sounds\\", StringComparison.OrdinalIgnoreCase);
                    if (!(sample && File.Exists(target))) {
                        Directory.CreateDirectory(Path.GetDirectoryName(target));
                        string temporary = target + ".jinkra-setup";
                        entry.ExtractToFile(temporary, true);
                        ReplaceFile(temporary, target);
                    }
                    if (!sample) installed.Add(relative);
                    if (progress != null) progress.Report(done * 95 / archive.Entries.Count);
                }
            }
        }
        string exe = Path.Combine(directory, ProductExe);
        if (!File.Exists(exe) || !File.Exists(Path.Combine(directory, Uninstaller))) {
            throw new IOException("安装未完成，请检查目录权限后重试。");
        }
        installed.Add(Manifest);
        File.WriteAllLines(Path.Combine(directory, Manifest), installed.ToArray());

        string programs = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
        CreateShortcut(Path.Combine(programs, ShortcutName), exe, directory);
        string desktopLink = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), ShortcutName);
        if (desktop) CreateShortcut(desktopLink, exe, directory);

        string version = Assembly.GetExecutingAssembly().GetName().Version.ToString(3);
        string uninstaller = Path.Combine(directory, Uninstaller);
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(InstallKey)) {
            key.SetValue("InstallLocation", directory);
        }
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(UninstallKey)) {
            key.SetValue("DisplayName", Product);
            key.SetValue("DisplayVersion", version);
            key.SetValue("Publisher", "Jinkra");
            key.SetValue("DisplayIcon", exe);
            key.SetValue("InstallLocation", directory);
            key.SetValue("URLInfoAbout", Repository);
            key.SetValue("UninstallString", "\"" + uninstaller + "\" --uninstall \"" + directory + "\"");
            key.SetValue("QuietUninstallString", "\"" + uninstaller + "\" --uninstall-silent \"" + directory + "\"");
            key.SetValue("NoModify", 1, RegistryValueKind.DWord);
            key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            key.SetValue("EstimatedSize", (int)(DirectorySize(directory) / 1024), RegistryValueKind.DWord);
        }
        if (progress != null) progress.Report(100);
    }

    // ---------------------------------------------------------------- 卸载

    private async void BeginUninstall() {
        string target = directory.Text;
        bool keep = keepData.Checked;
        bool cable = removeCable.Visible && removeCable.Checked;
        running = true;
        removeCable.Enabled = false;
        keepData.Enabled = back.Enabled = next.Enabled = close.Enabled = false;
        headline.Text = "正在卸载";
        detail.Text = "正在移除程序文件和快捷方式。";
        SetStatus(keep ? "将保留用户数据。" : "将删除用户数据。", false);
        progress.Style = ProgressBarStyle.Marquee;
        progress.Visible = true;
        try {
            string cableResult = null;
            if (cable) {
                SetStatus("正在卸载虚拟麦克风…", false);
                cableResult = await Task.Run(() => RemoveCable(Handle));
            }
            bool remaining = await Task.Run(() => Uninstall(target, keep));
            complete = true;
            headline.Text = "卸载完成";
            detail.Text = "已移除 Jinkra Voiceover Roulette。";
            SetStatus((keep ? "用户数据保留在 " + target + "。" :
                       remaining ? "部分文件仍被占用，可稍后手动删除 " + target + "。" : "已删除用户数据。") +
                      "\n" + (cableResult ?? "虚拟麦克风 VB-CABLE 已保留。"), remaining || (cable && !CableRemovedMessage(cableResult)));
            progress.Style = ProgressBarStyle.Continuous;
            progress.Value = 100;
            next.Text = "完成";
            next.BackColor = Accent;
            next.FlatAppearance.MouseOverBackColor = AccentHover;
            back.Visible = false;
            AcceptButton = next;
        } catch (Exception error) {
            headline.Text = "卸载未完成";
            detail.Text = "可以退出 Jinkra Voiceover Roulette 后重试。";
            SetStatus(error.Message, true);
            progress.Visible = false;
            keepData.Enabled = true;
            removeCable.Enabled = true;
        } finally {
            running = false;
            back.Enabled = next.Enabled = close.Enabled = true;
        }
    }

    // 返回 true 表示还有文件没删掉。
    internal static bool Uninstall(string directory, bool keepData) {
        EnsureClosed(directory);
        string exe = Path.Combine(directory, ProductExe);
        foreach (string link in new[] {
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), ShortcutName),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), ShortcutName) }) {
            // 只删指向本目录的快捷方式：另一个目录里的安装（或便携版）不受影响。
            if (SamePath(ShortcutTarget(link), exe)) TryDelete(link);
        }
        using (RegistryKey run = Registry.CurrentUser.OpenSubKey(RunKey, true)) {
            string value = run == null ? null : run.GetValue(Product) as string;
            if (value != null && value.Trim('"').Equals(exe, StringComparison.OrdinalIgnoreCase)) run.DeleteValue(Product, false);
        }
        foreach (string key in new[] { UninstallKey, InstallKey }) {
            string location;
            using (RegistryKey record = Registry.CurrentUser.OpenSubKey(key)) {
                location = record == null ? null : record.GetValue("InstallLocation") as string;
            }
            if (location != null && SamePath(location, directory)) Registry.CurrentUser.DeleteSubKeyTree(key, false);
        }

        if (!keepData) {
            for (int attempt = 0; attempt < 20 && Directory.Exists(directory); attempt++) {
                try { Directory.Delete(directory, true); }
                catch (IOException) { System.Threading.Thread.Sleep(250); }
                catch (UnauthorizedAccessException) { System.Threading.Thread.Sleep(250); }
            }
            return Directory.Exists(directory);
        }
        string manifest = Path.Combine(directory, Manifest);
        var files = new List<string>(File.Exists(manifest) ? File.ReadAllLines(manifest) : new string[0]);
        files.AddRange(new[] { ProductExe, Uninstaller, Manifest });
        string root = Path.GetFullPath(directory).TrimEnd('\\') + "\\";
        bool remaining = false;
        foreach (string relative in files) {
            if (relative.Length == 0) continue;
            string target = Path.GetFullPath(Path.Combine(root, relative));
            if (!target.StartsWith(root, StringComparison.OrdinalIgnoreCase)) continue;
            if (File.Exists(target) && !TryDelete(target)) remaining = true;
        }
        foreach (string stale in Directory.GetDirectories(directory, ".jinkra-update-*")) {
            try { Directory.Delete(stale, true); } catch (IOException) {} catch (UnauthorizedAccessException) {}
        }
        return remaining;
    }

    // ---------------------------------------------------------------- 虚拟麦克风

    private const string CableRemoved = "虚拟麦克风 VB-CABLE 已卸载，重启电脑后彻底移除。";

    private static bool CableRemovedMessage(string message) { return message == CableRemoved; }

    internal static bool CableInstalled() {
        using (RegistryKey key = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\VBAudioVACMME")) {
            return key != null;
        }
    }

    // 用 VB-CABLE 官方安装程序自带的静默卸载参数（-u -h）。驱动包原样嵌在卸载程序里。
    internal static string RemoveCable(IntPtr owner) {
        Stream pack = Assembly.GetExecutingAssembly().GetManifestResourceStream("vbcable.zip");
        if (pack == null) return "卸载程序缺少 VB-CABLE 驱动包，请在「设备管理器」里手动卸载。";
        string work = Path.Combine(Path.GetTempPath(), "jinkra-vbcable-" + Guid.NewGuid().ToString("N"));
        try {
            using (pack)
            using (var archive = new ZipArchive(pack, ZipArchiveMode.Read)) {
                archive.ExtractToDirectory(work);
            }
            string setup = Path.Combine(work, "VBCABLE_Setup_x64.exe");
            if (!File.Exists(setup)) return "VB-CABLE 驱动包不完整，请在「设备管理器」里手动卸载。";
            var start = new ProcessStartInfo(setup, "-u -h") {
                Verb = "runas", UseShellExecute = true, WorkingDirectory = work,
                WindowStyle = ProcessWindowStyle.Hidden, ErrorDialog = false
            };
            if (owner != IntPtr.Zero) start.ErrorDialogParentHandle = owner;
            using (Process process = Process.Start(start)) {
                if (!process.WaitForExit(120000)) return "VB-CABLE 卸载超时，请稍后在「设备管理器」里检查。";
            }
            for (int attempt = 0; attempt < 20 && CableInstalled(); attempt++) System.Threading.Thread.Sleep(500);
            return CableInstalled() ? "VB-CABLE 卸载程序已结束，重启电脑后虚拟麦克风会被移除。" : CableRemoved;
        } catch (System.ComponentModel.Win32Exception error) {
            return error.NativeErrorCode == 1223 ? "已取消管理员确认，虚拟麦克风 VB-CABLE 已保留。"
                                                 : "虚拟麦克风卸载失败：" + error.Message;
        } catch (Exception error) {
            return "虚拟麦克风卸载失败：" + error.Message;
        } finally {
            try { Directory.Delete(work, true); } catch (IOException) {} catch (UnauthorizedAccessException) {}
        }
    }

    // ---------------------------------------------------------------- 工具

    private static void EnsureClosed(string directory) {
        string exe = Path.GetFullPath(Path.Combine(directory, ProductExe));
        foreach (Process process in Process.GetProcessesByName(Path.GetFileNameWithoutExtension(ProductExe))) {
            using (process) {
                string path;
                try { path = process.MainModule.FileName; }
                catch (Exception) { continue; }
                if (String.Equals(Path.GetFullPath(path), exe, StringComparison.OrdinalIgnoreCase)) {
                    throw new IOException("Jinkra Voiceover Roulette 正在运行。请在托盘图标右键选择「退出」后重试。");
                }
            }
        }
    }

    // 刚写入的大文件常被杀毒软件短暂占用，替换时稍等重试。
    private static void ReplaceFile(string temporary, string target) {
        for (int attempt = 0; ; attempt++) {
            try {
                if (File.Exists(target)) File.Delete(target);
                File.Move(temporary, target);
                return;
            } catch (IOException) {
                if (attempt >= 40) throw;
            } catch (UnauthorizedAccessException) {
                if (attempt >= 40) throw;
            }
            System.Threading.Thread.Sleep(250);
        }
    }

    internal static bool IsInstalled(string folder) {
        return File.Exists(Path.Combine(folder, ProductExe)) && File.Exists(Path.Combine(folder, Uninstaller));
    }

    internal static string DefaultDirectory() {
        using (RegistryKey key = Registry.CurrentUser.OpenSubKey(InstallKey)) {
            string installed = key == null ? null : key.GetValue("InstallLocation") as string;
            if (!String.IsNullOrEmpty(installed) && IsInstalled(installed)) return installed;
        }
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", Product);
    }

    internal static string ValidateDirectory(string input, bool existing) {
        string value = (input ?? "").Trim();
        if (value.Length < 4 || value[1] != ':' || (value[2] != '\\' && value[2] != '/')) {
            throw new IOException("请选择本机磁盘上的完整安装目录。");
        }
        string fullPath = Path.GetFullPath(value);
        string folder = fullPath.TrimEnd('\\');
        if (folder.Equals(Path.GetPathRoot(fullPath).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase)) {
            throw new IOException("请选择磁盘中的子目录。");
        }
        if (Directory.Exists(folder) && (File.GetAttributes(folder) & FileAttributes.ReparsePoint) != 0) {
            throw new IOException("请选择实际安装目录。");
        }
        bool installed = IsInstalled(folder);
        if (existing && !installed) throw new IOException("无法定位已安装的 Jinkra Voiceover Roulette。");
        // 便携版目录（已有程序但没有卸载程序）也可以直接升级为安装版，设置和音效原样保留。
        // 卸载时保留下来的用户数据目录也可以直接装回去。
        bool portable = File.Exists(Path.Combine(folder, ProductExe)) || OnlyUserData(folder);
        if (!installed && !portable && Directory.Exists(folder) && Directory.GetFileSystemEntries(folder).Length != 0) {
            throw new IOException("请选择空目录，或 Jinkra Voiceover Roulette 现有的目录。");
        }
        return folder;
    }

    private static bool OnlyUserData(string folder) {
        if (!Directory.Exists(folder)) return false;
        string[] entries = Directory.GetFileSystemEntries(folder);
        if (entries.Length == 0) return false;
        foreach (string entry in entries) {
            string name = Path.GetFileName(entry);
            if (Array.IndexOf(UserData, name) < 0 && !name.StartsWith(".jinkra-update-", StringComparison.Ordinal)) return false;
        }
        return true;
    }

    private static bool SamePath(string a, string b) {
        if (String.IsNullOrEmpty(a) || String.IsNullOrEmpty(b)) return false;
        try {
            return String.Equals(Path.GetFullPath(a).TrimEnd('\\'), Path.GetFullPath(b).TrimEnd('\\'),
                                 StringComparison.OrdinalIgnoreCase);
        } catch (Exception) { return false; }
    }

    private static string ShortcutTarget(string link) {
        if (!File.Exists(link)) return null;
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        object shell = Activator.CreateInstance(shellType);
        try {
            object shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { link });
            try {
                return shortcut.GetType().InvokeMember("TargetPath", BindingFlags.GetProperty, null, shortcut, null) as string;
            } finally { Marshal.FinalReleaseComObject(shortcut); }
        } catch (Exception) {
            return null;
        } finally { Marshal.FinalReleaseComObject(shell); }
    }

    private static void CreateShortcut(string link, string target, string workingDirectory) {
        Directory.CreateDirectory(Path.GetDirectoryName(link));
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        object shell = Activator.CreateInstance(shellType);
        try {
            object shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { link });
            try {
                Type t = shortcut.GetType();
                t.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut, new object[] { target });
                t.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut, new object[] { workingDirectory });
                t.InvokeMember("IconLocation", BindingFlags.SetProperty, null, shortcut, new object[] { target + ",0" });
                t.InvokeMember("Description", BindingFlags.SetProperty, null, shortcut, new object[] { "游戏内音效轮盘" });
                t.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
            } finally { Marshal.FinalReleaseComObject(shortcut); }
        } finally { Marshal.FinalReleaseComObject(shell); }
    }

    private static long DirectorySize(string folder) {
        long total = 0;
        foreach (string file in Directory.GetFiles(folder, "*", SearchOption.AllDirectories)) {
            try { total += new FileInfo(file).Length; } catch (IOException) {}
        }
        return total;
    }

    private static bool TryDelete(string file) {
        for (int attempt = 0; attempt < 12; attempt++) {
            try { if (File.Exists(file)) File.Delete(file); return true; }
            catch (IOException) {}
            catch (UnauthorizedAccessException) {}
            System.Threading.Thread.Sleep(250);
        }
        return false;
    }

    private static GraphicsPath Rounded(RectangleF bounds, float radius) {
        float diameter = radius * 2;
        var path = new GraphicsPath();
        path.AddArc(bounds.Left, bounds.Top, diameter, diameter, 180, 90);
        path.AddArc(bounds.Right - diameter, bounds.Top, diameter, diameter, 270, 90);
        path.AddArc(bounds.Right - diameter, bounds.Bottom - diameter, diameter, diameter, 0, 90);
        path.AddArc(bounds.Left, bounds.Bottom - diameter, diameter, diameter, 90, 90);
        path.CloseFigure();
        return path;
    }

    // 卸载程序就在要删除的目录里，先把自己复制到临时目录再运行，结束后由 cmd 清理这份副本。
    private static bool RelaunchFromTemp(string[] args, string directory) {
        string self = Path.GetFullPath(Application.ExecutablePath);
        string root = Path.GetFullPath(directory).TrimEnd('\\') + "\\";
        if (!self.StartsWith(root, StringComparison.OrdinalIgnoreCase)) return false;
        string work = Path.Combine(Path.GetTempPath(), "jinkra-uninstall-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(work);
        string copy = Path.Combine(work, Uninstaller);
        File.Copy(self, copy);
        var quoted = new List<string>();
        foreach (string arg in args) quoted.Add("\"" + arg + "\"");
        quoted.Add("--cleanup");
        Process.Start(new ProcessStartInfo(copy, String.Join(" ", quoted.ToArray())) { WorkingDirectory = work, UseShellExecute = false }).Dispose();
        return true;
    }

    private static void ScheduleSelfCleanup() {
        string self = Path.GetFullPath(Application.ExecutablePath);
        string folder = Path.GetDirectoryName(self);
        if (!Path.GetFileName(folder).StartsWith("jinkra-uninstall-", StringComparison.Ordinal)) return;
        Process.Start(new ProcessStartInfo("cmd.exe",
            "/c ping 127.0.0.1 -n 3 > nul & del /f /q \"" + self + "\" & rmdir \"" + folder + "\"") {
            CreateNoWindow = true, UseShellExecute = false, WindowStyle = ProcessWindowStyle.Hidden,
            WorkingDirectory = Path.GetTempPath()  // cmd 的当前目录不能在要删除的目录里
        }).Dispose();
    }

    // 静默模式没有界面，失败原因写到临时目录，方便排查。
    private static void ReportSilentError(Exception error) {
        try { File.WriteAllText(Path.Combine(Path.GetTempPath(), "jinkra-voiceover-roulette-setup.log"), error.ToString()); }
        catch (IOException) {}
    }

    [STAThread]
    private static int Main(string[] args) {
        var list = new List<string>(args);
        bool cleanup = list.Remove("--cleanup");
        args = list.ToArray();
        try {
            if (args.Length >= 2 && (args[0] == "--uninstall" || args[0] == "--uninstall-silent")) {
                string target;
                try { target = ValidateDirectory(args[1], true); }
                catch (Exception error) {
                    if (args[0] == "--uninstall") MessageBox.Show(error.Message, Product + " 卸载向导", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return 1;
                }
                args[1] = target;  // 去掉末尾的反斜杠，避免重新拼命令行时把引号转义掉
                if (!cleanup && RelaunchFromTemp(args, target)) return 0;
                if (args[0] == "--uninstall-silent") {
                    bool removeData = Array.IndexOf(args, "--remove-data") >= 0;
                    if (Array.IndexOf(args, "--remove-vbcable") >= 0 && CableInstalled()) RemoveCable(IntPtr.Zero);
                    try { return Uninstall(target, !removeData) ? 3 : 0; }
                    catch (Exception error) { ReportSilentError(error); return 1; }
                }
                return RunWizard(target);
            }
            if (Assembly.GetExecutingAssembly().GetManifestResourceInfo("payload.zip") == null) {
                // 卸载程序被直接双击：按注册表找到安装目录。
                string installed = DefaultDirectory();
                if (!IsInstalled(installed)) {
                    MessageBox.Show("没有找到已安装的 Jinkra Voiceover Roulette。", Product, MessageBoxButtons.OK, MessageBoxIcon.Information);
                    return 1;
                }
                if (RelaunchFromTemp(new[] { "--uninstall", installed }, installed)) return 0;
                return RunWizard(installed);
            }
            if (args.Length >= 1 && args[0] == "--silent") {
                try {
                    string location = args.Length >= 2 ? args[1] : DefaultDirectory();
                    Install(ValidateDirectory(location, false), null, Array.IndexOf(args, "--no-desktop-shortcut") < 0);
                    return 0;
                } catch (Exception error) { ReportSilentError(error); return 1; }
            }
            return RunWizard(null);
        } finally {
            if (cleanup) ScheduleSelfCleanup();
        }
    }

    private static int RunWizard(string uninstallDirectory) {
        SetCurrentProcessExplicitAppUserModelID(uninstallDirectory == null ? "Jinkra.VoiceoverRoulette.Setup" : "Jinkra.VoiceoverRoulette.Uninstall");
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("logo.png"))
        using (Image image = Image.FromStream(stream))
        using (var setup = new RouletteSetup(image, uninstallDirectory)) {
            Application.Run(setup);
            return setup.complete ? 0 : 2;
        }
    }
}
