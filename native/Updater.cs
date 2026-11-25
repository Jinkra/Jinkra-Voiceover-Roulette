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
            // Windows 允许替换正在运行的 EXE，所以不能靠「替换成功」判断旧版已退出：
            // 先等旧版（单文件 EXE 的启动器和主程序两个进程）全部退出，再替换并启动新版，
            // 否则新版会撞上旧版还没释放的单实例锁，弹出「已经在运行」后退出。
            WaitForOldCopies(current);
            ReplaceWhenClosed(staged, current, backup);
            try
            {
                using (var process = Process.Start(new ProcessStartInfo(current, "--after-update") {
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

    private static void WaitForOldCopies(string exe)
    {
        var deadline = DateTime.UtcNow.AddSeconds(20);
        while (true)
        {
            var running = RunningCopies(exe);
            if (running.Length == 0)
                return;
            if (DateTime.UtcNow > deadline)
            {
                // 旧版迟迟不退：结束它。设置和音效都是随改随存的。
                foreach (var process in running)
                {
                    try { process.Kill(); process.WaitForExit(5000); }
                    catch (Exception) { }
                }
                Thread.Sleep(500);
                if (RunningCopies(exe).Length != 0)
                    throw new IOException("旧版程序没有退出，请在托盘图标右键选择「退出」后重新更新。");
                return;
            }
            foreach (var process in running)
                process.Dispose();
            Thread.Sleep(200);
        }
    }

    private static Process[] RunningCopies(string exe)
    {
        var self = Process.GetCurrentProcess().Id;
        var found = new System.Collections.Generic.List<Process>();
        foreach (var process in Process.GetProcessesByName(Path.GetFileNameWithoutExtension(exe)))
        {
            string path = null;
            try { if (process.Id != self) path = process.MainModule.FileName; }
            catch (Exception) { }
            if (path != null && String.Equals(Path.GetFullPath(path), exe, StringComparison.OrdinalIgnoreCase))
                found.Add(process);
            else
                process.Dispose();
        }
        return found.ToArray();
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
