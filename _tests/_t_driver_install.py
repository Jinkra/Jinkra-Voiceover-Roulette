"""随包驱动的点击安装、失败重试和安装后送声。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import driver_setup
import sr_roulette as sr
from settings_window import MicPage
from welcome import SetupGuide


class DriverInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        sandbox = self.enterContext(tempfile.TemporaryDirectory())
        self.base = Path(sandbox)
        self.resources = self.base / "resources"
        self.resources.mkdir()
        (self.resources / "jinkra-driver-helper.exe").touch()
        self.package = self.resources / "VirtualMic"
        self.installation = driver_setup.DriverInstallation(self.base, self.resources, self.app)
        self.addCleanup(self.installation.close)
        self.enterContext(patch.object(self.app, "jinkra_driver_installation", self.installation, create=True))
        self.enterContext(patch.object(sr, "real_inputs", return_value=[]))
        self.enterContext(patch.object(sr, "virtual_route_status", return_value=(None, "等待端点")))
        self.save_config = self.enterContext(patch.object(sr, "save_config"))
        self.cfg = dict(sr.DEFAULT_CONFIG, animations=False, mic_enabled=False)

    def stage_fixture(self):
        self.package.mkdir()
        for name in driver_setup.DRIVER_FILES:
            (self.package / name).write_bytes(name.encode())

    def show_guide(self):
        activation = Mock()
        activation.active.return_value = True
        guide = SetupGuide(sr, activation, self.cfg)
        self.addCleanup(guide.close)
        guide.show()
        guide._show(2)
        return guide

    def test_guide_enables_sending_and_saves_before_endpoints_arrive(self):
        self.stage_fixture()
        guide = self.show_guide()
        process = Mock()
        process.result.side_effect = [None, 0]
        with patch.object(driver_setup, "_start_install", return_value=process) as launch:
            self.assertTrue(guide.btn_install.isEnabled())
            guide.btn_install.click()
        staged = launch.call_args.args[1]
        self.assertNotEqual(staged, self.package)
        for name in driver_setup.DRIVER_FILES:
            self.assertEqual((staged / name).read_bytes(), (self.package / name).read_bytes())
        self.assertFalse(guide.next.isEnabled())
        self.installation._poll()
        self.assertFalse(guide.enable_mic.isChecked())
        self.installation._poll()
        self.assertTrue(guide.enable_mic.isChecked())
        self.assertTrue(guide.next.isEnabled())
        self.assertFalse(staged.exists())
        process.close.assert_called_once()
        guide._finish()
        self.assertTrue(self.cfg["mic_enabled"])
        self.save_config.assert_called_once_with(self.cfg)

    def test_guide_can_choose_local_playback(self):
        self.stage_fixture()
        guide = self.show_guide()
        process = Mock()
        process.result.return_value = 0
        with patch.object(driver_setup, "_start_install", return_value=process):
            guide.btn_install.click()
        guide._finish(local_only=True)
        self.installation._poll()
        self.assertFalse(self.cfg["mic_enabled"])
        self.assertFalse(guide.enable_mic.isChecked())

    def test_settings_keeps_retry_and_enables_only_after_success(self):
        page = MicPage(self.cfg, None)
        self.addCleanup(page.close)
        self.assertFalse(page.btn_install.isEnabled())
        self.stage_fixture()
        page.refresh_devices()
        self.assertTrue(page.btn_install.isEnabled())
        with patch.object(driver_setup, "_start_install", side_effect=OSError("已取消 Windows 管理员确认。")) as launch:
            page.btn_install.click()
        self.assertFalse(launch.call_args.args[1].exists())
        self.assertIn("已取消", page.lbl_status.text())
        self.assertFalse(self.cfg["mic_enabled"])
        self.assertTrue(page.btn_install.isEnabled())

        process = Mock()
        process.result.return_value = 0
        with patch.object(driver_setup, "_start_install", return_value=process):
            page.btn_install.click()
        self.installation._poll()
        self.assertTrue(self.cfg["mic_enabled"])
        self.assertTrue(page.chk_enable.isChecked())
        self.assertIn("自动送声", page.lbl_status.text())


if __name__ == "__main__":
    unittest.main()
