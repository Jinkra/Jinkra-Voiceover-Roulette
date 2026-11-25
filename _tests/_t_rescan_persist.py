"""程序开着时往 sounds 放音效：重新扫描后的轮盘布局必须立刻存盘，重启（更新）后保持一致。"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import sr_roulette as sr
from sounds_config import SoundsConfig

SAMPLES = sorted((Path(sr.__file__).parent / "sounds").glob("Jinkra-*.wav"))


class RescanPersistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.base = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.sounds = self.base / "sounds"
        self.sounds.mkdir()
        for sample in SAMPLES:
            shutil.copy(sample, self.sounds / sample.name)
        self.json = self.base / "sounds.json"
        self.enterContext(patch.object(sr, "SOUNDS_DIR", self.sounds))

    def start(self):
        """模拟一次程序启动：读盘、扫描、需要时落盘。"""
        scfg = SoundsConfig(self.json)
        scfg.load()
        bank = sr.SoundBank(sr.MAX_SLOTS, scfg)
        if scfg.dirty:
            scfg.save()
        return scfg, bank

    def layout(self, scfg):
        return list(scfg.order), list(scfg.outer_slots)

    def test_files_added_while_running_survive_restart(self):
        scfg, bank = self.start()
        # 程序开着：用户删掉示例、拷进自己的音效，然后打开设置窗口（触发重新扫描）
        for sample in self.sounds.glob("Jinkra-*.wav"):
            sample.unlink()
        for i in range(17):
            shutil.copy(SAMPLES[i % len(SAMPLES)], self.sounds / f"我的音效{i:02d}.wav")
        bank.reload()
        seen = self.layout(scfg)
        self.assertTrue(any(name.startswith("我的音效") for name in seen[0]))
        on_disk = json.loads(self.json.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["order"], seen[0], "重新扫描后的布局没有存盘")
        # 更新重启
        restarted, _bank = self.start()
        self.assertEqual(self.layout(restarted), seen)

    def test_unchanged_rescan_does_not_rewrite(self):
        scfg, bank = self.start()
        stamp = self.json.stat().st_mtime_ns
        bank.reload()
        self.assertEqual(self.json.stat().st_mtime_ns, stamp)


if __name__ == "__main__":
    unittest.main()
