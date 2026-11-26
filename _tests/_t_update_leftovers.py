"""应用内更新：启动时清理旧暂存目录，但不碰更新程序还在用的那个；进度条文字可读。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import sr_roulette as sr


class LeftoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_removes_finished_update_stage_and_keeps_user_files(self):
        base = Path(self.enterContext(tempfile.TemporaryDirectory()))
        done = base / ".jinkra-update-old"
        done.mkdir()
        (done / "previous.exe").write_bytes(b"MZ" * 100)
        (done / "apply-update.exe").write_bytes(b"MZ")
        (base / "sounds").mkdir()
        (base / "sounds" / "我的音效.wav").write_bytes(b"RIFF")
        (base / "sounds.json").write_text("{}", encoding="utf-8")
        busy = base / ".jinkra-update-busy"
        busy.mkdir()
        (busy / "previous.exe").write_bytes(b"MZ")
        (busy / "apply-update.exe").write_bytes(b"MZ")
        real_unlink = Path.unlink

        def unlink(path, missing_ok=False):
            if path.parent == busy and path.name == "apply-update.exe":
                raise PermissionError("更新程序仍在运行")
            return real_unlink(path, missing_ok=missing_ok)

        with patch.object(sr, "BASE_DIR", base), patch.object(sys, "frozen", True, create=True), \
             patch.object(Path, "unlink", unlink):
            sr.clean_update_leftovers()
        self.assertFalse(done.exists())
        self.assertTrue((busy / "previous.exe").exists(), "回滚用的备份必须保留")
        self.assertTrue((base / "sounds" / "我的音效.wav").exists())
        self.assertTrue((base / "sounds.json").exists())

    def test_update_and_restart_really_exits_with_settings_window_open(self):
        """设置窗口开着（它会先拒绝关闭做淡出动画）时点「更新并重启」，程序必须真正退出。"""
        import subprocess
        import textwrap
        script = textwrap.dedent(r"""
            import os, sys, time
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
            sys.path.insert(0, sys.argv[1])
            from pathlib import Path
            from unittest.mock import patch
            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QApplication, QWidget
            app = QApplication([])
            app.setQuitOnLastWindowClosed(False)
            import sr_roulette as sr
            import updates
            from update_dialog import UpdateDialog

            class Settings(QWidget):
                def closeEvent(self, e):
                    e.ignore()

            win = Settings(); win.show()
            with patch.object(UpdateDialog, "_check", lambda self: None):
                dialog = UpdateDialog(sr, win)
            dialog.staged = Path("staged.exe")

            def press():
                with patch.object(updates, "apply_update"):
                    dialog._download_or_apply()

            QTimer.singleShot(200, lambda: dialog.exec())
            QTimer.singleShot(500, press)
            QTimer.singleShot(5000, lambda: os._exit(3))
            app.exec()
            print("exited", flush=True)
        """)
        result = subprocess.run([sys.executable, "-c", script, str(Path(__file__).resolve().parents[1])],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("exited", result.stdout)

    def test_progress_text_is_dark(self):
        from update_dialog import UpdateDialog
        with patch.object(UpdateDialog, "_check", lambda self: None):
            dialog = UpdateDialog(sr)
        self.addCleanup(dialog.close)
        self.assertIn("color: #1f2b25", dialog.bar.styleSheet())


if __name__ == "__main__":
    unittest.main()
