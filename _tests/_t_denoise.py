"""AI 降噪：模型下载校验、RNNoise 真实降噪效果、采集链路接入与开关。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtWidgets import QApplication

import denoise
import sr_roulette as sr

MODEL_HOME = Path(__file__).resolve().parents[1]  # 下载一次，留给后续测试复用（models/ 已被忽略）


class FakeDenoiser:
    def __init__(self, base):
        self.calls = 0

    def process(self, arr):
        self.calls += 1
        return arr[: len(arr) // 480 * 480] * 0.5

    def reset(self):
        pass


class DenoiseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_capture_routes_audio_through_denoiser(self):
        cap = sr.MicCapture(sr._fmt(48000, 2, sr.QAudioFormat.Float))
        with patch.object(denoise, "Denoiser", FakeDenoiser):
            cap.set_denoise(True)
        self.assertIsInstance(cap.denoiser, FakeDenoiser)
        frames = np.full((1000, 2), 0.4, dtype=np.float32)
        self.assertEqual(cap.push(frames.tobytes()), 960)
        self.assertAlmostEqual(float(cap._buf[0, 0]), 0.2, places=5)
        cap.set_denoise(False)
        self.assertIsNone(cap.denoiser)

    def test_missing_model_keeps_raw_voice(self):
        cap = sr.MicCapture(sr._fmt(48000, 2, sr.QAudioFormat.Float))
        with patch.object(sr, "BASE_DIR", Path(tempfile.mkdtemp())), \
             patch.object(denoise, "_LIB", None):
            cap.set_denoise(True)
        self.assertIsNone(cap.denoiser)
        self.assertIn("未安装", cap.denoise_error)
        self.assertEqual(cap.push(np.full((100, 2), 0.4, np.float32).tobytes()), 100)

    def test_non_48k_output_is_reported(self):
        cap = sr.MicCapture(sr._fmt(44100, 2, sr.QAudioFormat.Float))
        cap.set_denoise(True)
        self.assertIsNone(cap.denoiser)
        self.assertIn("48kHz", cap.denoise_error)

    def test_corrupt_download_falls_through_every_mirror(self):
        with tempfile.TemporaryDirectory() as base, \
             patch.object(denoise, "_fetch", return_value=b"not a wheel"):
            with self.assertRaises(OSError) as raised:
                denoise.download(Path(base))
            self.assertFalse(denoise.installed(Path(base)))
        for name, _ in denoise.MIRRORS:
            self.assertIn(name, str(raised.exception))

    @unittest.skipUnless(sys.platform == "win32", "RNNoise DLL 只有 Windows 版")
    def test_real_model_suppresses_noise_and_keeps_voice(self):
        if not denoise.installed(MODEL_HOME):
            denoise.download(MODEL_HOME)
        rng = np.random.default_rng(1)
        seconds = 3
        t = np.arange(48000 * seconds) / 48000
        noise = (0.05 * rng.standard_normal(len(t))).astype(np.float32)
        d = denoise.Denoiser(MODEL_HOME)
        out = d.process(np.repeat(noise[:, None], 2, axis=1))
        tail = slice(48000, None)  # 前一秒是模型收敛
        reduction = np.sqrt(np.mean(out[tail, 0] ** 2)) / np.sqrt(np.mean(noise[tail] ** 2))
        print(f"纯噪声能量剩余 {reduction:.3f}")
        self.assertLess(reduction, 0.3)
        self.assertEqual(out.shape, (len(t), 2))
        np.testing.assert_array_equal(out[:, 0], out[:, 1])
        d.close()


if __name__ == "__main__":
    unittest.main()
