"""虚拟麦克风一键安装：随包 VB-CABLE、官网兜底、签名 Jinkra 驱动、失败重试和安装后送声。"""

import os
import sys
import tempfile
import hashlib
import zipfile
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
        self.ready = False
        self.installation = driver_setup.DriverInstallation(self.base, self.resources, self.app,
                                                            lambda: self.ready)
        self.addCleanup(self.installation.close)
        self.enterContext(patch.object(self.app, "jinkra_driver_installation", self.installation, create=True))
        self.enterContext(patch.object(sr, "real_inputs", return_value=[]))
        self.enterContext(patch.object(sr, "virtual_route_status", return_value=(None, "等待端点")))
        self.save_config = self.enterContext(patch.object(sr, "save_config"))
        self.cable_status = set()
        self.enterContext(patch.object(driver_setup, "_cable_status", lambda: set(self.cable_status)))
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

    # ---- VB-CABLE ----
    def make_pack(self, where):
        where.mkdir(parents=True, exist_ok=True)
        pack = where / driver_setup.VB_CABLE_PACK
        with zipfile.ZipFile(pack, "w") as archive:
            archive.writestr(driver_setup.VB_CABLE_SETUP, b"setup")
            archive.writestr("vbMmeCable64_win10.inf", b"inf")
        self.enterContext(patch.object(driver_setup, "VB_CABLE_SHA256",
                                       hashlib.sha256(pack.read_bytes()).hexdigest()))
        return pack

    def test_bundled_vb_cable_installs_without_download(self):
        self.make_pack(self.resources)
        page = MicPage(self.cfg, None)
        self.addCleanup(page.close)
        self.assertTrue(page.btn_install.isEnabled())
        self.assertIn("全自动", page.lbl_status.text())
        process = Mock()
        process.result.side_effect = [None, 1]
        with patch.object(driver_setup, "_download_pack") as download, \
             patch.object(driver_setup, "_start_vb_cable", return_value=process) as launch:
            page.btn_install.click()
        download.assert_not_called()
        setup = launch.call_args.args[0]
        self.assertEqual(driver_setup.VB_CABLE_SILENT, "-i -h")
        self.assertEqual(setup.name, driver_setup.VB_CABLE_SETUP)
        self.assertEqual(setup.read_bytes(), b"setup")
        self.assertFalse(page.btn_install.isEnabled())
        self.installation._poll()           # 安装窗口还开着
        self.installation._poll()           # 窗口关闭（VB 安装程序退出码不可信，看端点）
        self.assertFalse(setup.exists())
        self.assertFalse(self.cfg["mic_enabled"])
        self.installation._poll()           # 端点还没出现
        self.assertFalse(self.cfg["mic_enabled"])
        self.ready = True
        self.installation._poll()
        self.assertTrue(self.cfg["mic_enabled"])
        self.assertTrue(page.chk_enable.isChecked())
        self.assertIsNone(self.installation._stage)

    def test_endpoints_never_appear_suggests_restart(self):
        self.make_pack(self.resources)
        process = Mock()
        process.result.return_value = 0
        with patch.object(driver_setup, "_start_vb_cable", return_value=process):
            self.installation.install(None)
        self.installation._poll()
        with patch.object(driver_setup.time, "monotonic", return_value=1e12):
            self.installation._poll()
        self.assertIn("没有装上", self.installation.hint())
        self.assertTrue(self.installation.can_install())

    def wait_for_status(self):
        future = self.installation._status
        if future is not None:
            future.result(timeout=5)
        self.installation._poll()

    def test_device_failed_to_start_asks_for_restart_without_waiting(self):
        self.make_pack(self.resources)
        self.cable_status = {"Error"}
        process = Mock()
        process.result.return_value = 0
        with patch.object(driver_setup, "_start_vb_cable", return_value=process):
            self.installation.install(None)
        self.installation._poll()          # 安装程序结束，开始查设备状态
        self.wait_for_status()
        self.assertIn("需要重启", self.installation.hint())
        self.assertIn("无需重新安装", self.installation.hint())
        self.assertTrue(self.installation.can_install())

    def test_no_device_after_timeout_asks_to_retry(self):
        self.make_pack(self.resources)
        process = Mock()
        process.result.return_value = 0
        with patch.object(driver_setup, "_start_vb_cable", return_value=process):
            self.installation.install(None)
        self.installation._poll()
        self.wait_for_status()
        with patch.object(driver_setup.time, "monotonic", return_value=1e12):
            self.installation._poll()
        self.assertIn("没有装上", self.installation.hint())

    def test_working_device_still_waits_for_endpoints(self):
        self.make_pack(self.resources)
        self.cable_status = {"OK"}
        process = Mock()
        process.result.return_value = 0
        with patch.object(driver_setup, "_start_vb_cable", return_value=process):
            self.installation.install(None)
        self.installation._poll()
        self.wait_for_status()
        self.assertTrue(self.installation.busy())
        self.ready = True
        self.installation._poll()
        self.assertIn("已自动启用送声", self.installation.hint())

    def test_tampered_bundle_falls_back_to_official_download(self):
        pack = self.make_pack(self.resources)
        good = pack.read_bytes()
        pack.write_bytes(b"tampered")
        def fetch(destination):
            destination.write_bytes(good)
            return destination
        process = Mock()
        process.result.return_value = None
        with patch.object(driver_setup, "_download_pack", side_effect=fetch) as download, \
             patch.object(driver_setup, "_start_vb_cable", return_value=process) as launch:
            self.installation.install(None)
            self.assertIn("官网", self.installation.hint())
            self.installation._download.result(timeout=5)
            self.installation._poll()
        download.assert_called_once()
        launch.assert_called_once()

    def test_download_failure_can_retry(self):
        with patch.object(driver_setup, "_download_pack", side_effect=OSError("校验失败")):
            self.installation.install(None)
            self.installation._download.exception(timeout=5)
            self.installation._poll()
        self.assertIn("校验失败", self.installation.hint())
        self.assertTrue(self.installation.can_install())

    def test_zip_with_escaping_path_is_rejected(self):
        where = self.base / "evil"
        where.mkdir()
        pack = where / driver_setup.VB_CABLE_PACK
        with zipfile.ZipFile(pack, "w") as archive:
            archive.writestr("../escape.exe", b"x")
        with patch.object(driver_setup, "VB_CABLE_SHA256", hashlib.sha256(pack.read_bytes()).hexdigest()):
            with self.assertRaises(OSError):
                driver_setup._extract_pack(pack, self.base / "stage")
        self.assertFalse((self.base / "escape.exe").exists())


if __name__ == "__main__":
    unittest.main()
