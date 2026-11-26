"""AI 朗读：朗读包下载校验与解压、音色列表、边合成边播放的排程、停止与保存为音效。"""

import hashlib
import io
import os
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtWidgets import QApplication

import sr_roulette as sr
import tts
import updates


def fake_pack_archive(top="vits-fake", extra=()):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as bundle:
        for name, data in (("model.onnx", b"onnx"), ("tokens.txt", b"t"), ("lexicon.txt", b"l"),
                           ("rule.far", b"x" * 1000), *extra):
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class PackTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.data = fake_pack_archive()
        self.pack = tts.Pack("fake", "测试包", "", "MIT", "vits-fake", len(self.data),
                             hashlib.sha256(self.data).hexdigest(), "vits",
                             (tts.VoiceGroup("pack:fake", "测试（女声）", 0, 1),))

    def test_install_falls_back_across_routes_and_skips_rule_far(self):
        tried = []

        def fake_open(url, **kwargs):
            tried.append(url)
            if len(tried) == 1:
                raise OSError("线路不通")
            if len(tried) == 2:
                return io.BytesIO(self.data[:-1] + b"\0")   # 内容被改过
            return io.BytesIO(self.data)

        with patch.object(updates, "_open", side_effect=fake_open):
            folder = tts.download(self.base, self.pack)
        self.assertEqual(len(tried), 3)
        self.assertTrue(tts.installed(self.base, self.pack))
        self.assertEqual(sorted(p.name for p in folder.iterdir()),
                         [".installed", "lexicon.txt", "model.onnx", "tokens.txt"])
        tts.remove(self.base, self.pack)
        self.assertFalse(tts.installed(self.base, self.pack))

    def test_all_routes_bad_raises_and_leaves_nothing(self):
        with patch.object(updates, "_open", side_effect=lambda url, **k: io.BytesIO(b"bad")):
            with self.assertRaises(OSError):
                tts.download(self.base, self.pack)
        self.assertFalse(tts.pack_dir(self.base, self.pack).exists())

    def test_escaping_paths_rejected(self):
        data = fake_pack_archive(extra=(("../../escape.txt", b"x"),))
        pack = tts.Pack("fake", "x", "", "", "vits-fake", len(data), hashlib.sha256(data).hexdigest(), "vits")
        with patch.object(updates, "_open", side_effect=lambda url, **k: io.BytesIO(data)):
            with self.assertRaises(OSError):
                tts.download(self.base, pack)
        self.assertFalse((self.base / "escape.txt").exists())

    def test_cancel_stops_download(self):
        with patch.object(updates, "_open", side_effect=lambda url, **k: io.BytesIO(self.data)):
            with self.assertRaises(InterruptedError):
                tts.download(self.base, self.pack, cancelled=lambda: True)

    def test_builtin_pack_table(self):
        ids = [pack.id for pack in tts.PACKS]
        self.assertEqual(len(ids), len(set(ids)))
        kokoro = tts.pack_by_id("kokoro")
        self.assertEqual(sum(group.count for group in kokoro.groups), 103)
        for pack in tts.PACKS:
            self.assertRegex(pack.sha256, r"^[0-9a-f]{64}$")
            self.assertTrue(pack.url.startswith("https://github.com/k2-fsa/sherpa-onnx/releases/download/"))


class SpeechPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.base = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(sr, "BASE_DIR", self.base))
        self.enterContext(patch.object(sr, "SOUNDS_DIR", self.base / "sounds"))
        self.enterContext(patch.object(sr, "save_config"))
        self.enterContext(patch.object(tts, "system_voices", return_value=[
            tts.Voice("sys:winrt:A", "系统 · 慧慧（中文女声）"), tts.Voice("sys:winrt:B", "系统 · 康康（中文男声）")]))
        self.engine = Mock()
        self.engine.fmt.sampleRate.return_value = 48000
        self.engine.new_token.side_effect = [101, 102, 103]
        self.engine.play_speech.side_effect = lambda samples, rate, token, delay, gain: len(samples) * 48000 // rate
        from settings_window import SpeechPage
        self.cfg = dict(sr.DEFAULT_CONFIG, tts_voice="sys:winrt:B", tts_text="你好")
        self.page = SpeechPage(self.cfg, self.engine)
        self.page.helper = Path("helper.exe")
        self.addCleanup(self.page.close)

    def wait(self, condition, timeout=5):
        end = time.monotonic() + timeout
        while not condition() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(condition())

    def test_saved_voice_restored_and_multi_voice_index(self):
        self.assertEqual(self.page.voice.currentData().key, "sys:winrt:B")
        self.assertFalse(self.page.index_row.isVisibleTo(self.page))
        with patch.object(tts, "pack_voices", return_value=[tts.Voice("pack:kokoro:zm", "Kokoro 中文男声", 45, "kokoro")]):
            self.cfg["tts_voice"] = "pack:kokoro:zm"
            self.cfg["tts_index"] = 7
            self.page.reload_voices()
        self.assertTrue(self.page.index_row.isVisibleTo(self.page))
        self.assertEqual(self.page.index.maximum(), 45)
        self.assertEqual(self.page.index.value(), 7)

    def test_system_voice_reads_through_mixer_and_saves(self):
        samples = np.full(16000, 0.1, dtype=np.float32)
        with patch.object(tts, "synth_system", return_value=(samples, 16000)) as synth:
            self.page.speak()
            self.wait(lambda: self.page._last is not None)
        synth.assert_called_once()
        args = self.engine.play_speech.call_args.args
        self.assertEqual(args[2], 101)            # 用这次朗读的触发编号
        self.assertEqual(args[3], 0)              # 第一段不延迟
        self.page.btn_stop.click()
        self.engine.stop_token.assert_called_with(101)
        saved = []
        self.page.saved.connect(saved.append)
        self.page.btn_save.click()
        path = self.base / "sounds" / "朗读" / "你好.wav"
        self.assertTrue(path.is_file())
        self.assertEqual(saved, [str(path)])
        self.page.btn_save.click()
        self.assertTrue((self.base / "sounds" / "朗读" / "你好（2）.wav").is_file())

    def test_streamed_chunks_are_queued_back_to_back(self):
        self.page._job = 1
        self.page._token = 101
        self.page._cancel = threading.Event()
        chunk = np.zeros(22050, dtype=np.float32)               # 1 秒
        self.page._on_chunk(1, chunk, 22050)
        self.page._on_chunk(1, chunk, 22050)
        delays = [call.args[3] for call in self.engine.play_speech.call_args_list]
        self.assertEqual(delays[0], 0)
        self.assertGreater(delays[1], 47000)                     # 第二句排在第一句之后
        self.page._on_chunk(0, chunk, 22050)                     # 过期任务的回调作废
        self.assertEqual(self.engine.play_speech.call_count, 2)

    def test_failure_is_reported(self):
        with patch.object(tts, "synth_system", side_effect=OSError("找不到这个系统语音")):
            self.page.speak()
            self.wait(lambda: "朗读失败" in self.page.status.text())
        self.assertTrue(self.page.btn_speak.isEnabled())


class EnginePlaybackTests(unittest.TestCase):
    def test_play_speech_resamples_to_stereo_and_feeds_every_output(self):
        fmt = sr._fmt(48000, 2, sr.QAudioFormat.Float)
        mixers = [Mock(), Mock()]
        engine = Mock(fmt=fmt, _active_mixers=Mock(return_value=mixers))
        frames = sr.AudioEngine.play_speech(engine, np.ones(16000, dtype=np.float32) * 0.5, 16000,
                                            token=7, delay_frames=480, gain=0.8)
        self.assertEqual(frames, 48000)
        for mixer in mixers:
            clip = mixer.trigger.call_args.args[0]
            self.assertEqual(clip.shape, (48000, 2))
            self.assertAlmostEqual(float(clip[1000, 1]), 0.5, places=4)
            self.assertEqual(mixer.trigger.call_args.kwargs, {"delay": 480, "token": 7})
            self.assertEqual(mixer.trigger.call_args.args[1], 0.8)


@unittest.skipUnless(sys.platform == "win32", "系统语音只在 Windows 上有")
class RealSystemVoiceTests(unittest.TestCase):
    def test_lists_and_synthesizes_distinct_voices(self):
        helper = tts.helper_path(Path(__file__).resolve().parents[1], Path("nowhere"))
        if helper is None:
            self.skipTest("还没编译 jinkra-tts.exe")
        voices = tts.system_voices(helper, refresh=True)
        self.assertTrue(voices)
        outputs = {}
        for voice in voices[:3]:
            samples, rate = tts.synth_system(helper, voice.key, "你好，测试。", 1.0)
            self.assertGreater(len(samples), rate // 4)
            outputs[voice.key] = hashlib.md5(samples.tobytes()).hexdigest()
        self.assertEqual(len(set(outputs.values())), len(outputs), "不同音色应合成出不同的声音")


if __name__ == "__main__":
    unittest.main()
