using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Windows.Forms;

internal static class JinkraUpdater
{
    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length != 2)
            return 2;

        var staged = Path.GetFullPath(args[0]);
        var current = Path.GetFullPath(args[1]);
        var folder = Path.GetDirectoryName(staged);
        var backup = Path.Combine(folder, "previous.exe");

        if (Path.GetFileName(staged) != "Jinkra Voiceover Roulette.exe" ||
            !Path.GetFileName(folder).StartsWith(".jinkra-update-", StringComparison.Ordinal) ||
            !String.Equals(Path.GetDirectoryName(folder), Path.GetDirectoryName(current),
                           StringComparison.OrdinalIgnoreCase))
            return 2;

        try
        {
            ReplaceWhenClosed(staged, current, backup);
            try
            {
                using (var process = Process.Start(new ProcessStartInfo(current) {
                    WorkingDirectory = Path.GetDirectoryName(current),
                    UseShellExecute = true
                }))
                {
                    if (process == null || (process.WaitForExit(6500) && process.ExitCode != 0))
                        throw new IOException("更新后的程序未持续运行。");
                }
            }
            catch
            {
                ReplaceWhenClosed(backup, current, null);
                Process.Start(current);
                throw;
            }
            try { File.Delete(backup); }
            catch (IOException) { }
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show("更新未能完成。现有设置及音效仍在原目录。\r\n" + error.Message,
                            "Jinkra 更新", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return 1;
        }
    }

    private static void ReplaceWhenClosed(string source, string target, string backup)
    {
        for (var attempt = 0; ; attempt++)
        {
            try
            {
                File.Replace(source, target, backup, true);
                return;
            }
            catch (IOException)
            {
                if (attempt == 119)
                    throw;
                Thread.Sleep(250);
            }
        }
    }
}
