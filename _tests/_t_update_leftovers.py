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

    def test_clean_environment_drops_pyinstaller_state(self):
        import updates
        env = updates.clean_environment({"PATH": "x", "_PYI_APPLICATION_HOME_DIR": "C:/old", "_PYI_ARCHIVE_FILE": "a",
                                         "_PYI_PARENT_PROCESS_LEVEL": "1", "_MEIPASS2": "C:/old", "JINKRA_RELAUNCHED": "1"})
        self.assertEqual(env, {"PATH": "x", "PYINSTALLER_RESET_ENVIRONMENT": "1"})

    def test_apply_update_launches_updater_with_clean_environment(self):
        import updates
        base = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (base / "jinkra-updater.exe").write_bytes(b"MZ")
        stage = base / ".jinkra-update-x"
        stage.mkdir()
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", str(base), create=True), \
             patch.dict(os.environ, {"_PYI_APPLICATION_HOME_DIR": str(base)}), \
             patch.object(updates.subprocess, "Popen") as popen:
            updates.apply_update(stage / updates.NAME)
        env = popen.call_args.kwargs["env"]
        self.assertNotIn("_PYI_APPLICATION_HOME_DIR", env)
        self.assertEqual(env["PYINSTALLER_RESET_ENVIRONMENT"], "1")

    def test_stale_bundle_relaunches_once(self):
        bundle = Path(self.enterContext(tempfile.TemporaryDirectory()))
        common = (patch.object(sys, "frozen", True, create=True),
                  patch.object(sys, "_MEIPASS", str(bundle), create=True))
        with common[0], common[1], patch("subprocess.Popen") as popen, \
             patch.dict(os.environ, {"_PYI_APPLICATION_HOME_DIR": "C:/old"}, clear=False):
            os.environ.pop("JINKRA_RELAUNCHED", None)
            self.assertTrue(sr.ensure_fresh_bundle())          # 没有版本标记：旧版的解压目录
            env = popen.call_args.kwargs["env"]
            self.assertNotIn("_PYI_APPLICATION_HOME_DIR", env)
            self.assertEqual(env["JINKRA_RELAUNCHED"], "1")
            popen.reset_mock()
            (bundle / sr.BUNDLE_MARKER).write_text(sr.APP_VERSION, encoding="utf-8")
            self.assertFalse(sr.ensure_fresh_bundle())         # 版本对得上：正常启动
            (bundle / sr.BUNDLE_MARKER).write_text("v0.0.1", encoding="utf-8")
            os.environ["JINKRA_RELAUNCHED"] = "1"
            self.assertFalse(sr.ensure_fresh_bundle())         # 已经重启过：不再循环
            self.assertNotIn("JINKRA_RELAUNCHED", os.environ)
            popen.assert_not_called()

    def test_progress_text_is_dark(self):
        from update_dialog import UpdateDialog
        with patch.object(UpdateDialog, "_check", lambda self: None):
            dialog = UpdateDialog(sr)
        self.addCleanup(dialog.close)
        self.assertIn("color: #1f2b25", dialog.bar.styleSheet())


if __name__ == "__main__":
    unittest.main()
