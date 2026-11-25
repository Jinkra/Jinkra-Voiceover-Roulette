"""在已安装正式驱动的 Windows 上验证 Jinkra 的录音端。"""

import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QIODevice
from PySide6.QtMultimedia import QAudioSink, QAudioSource
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sr_roulette as sr


def run() -> int:
    app = QApplication([])
    render = sr.guess_virtual_output()
    if render is None:
        print("未运行系统端到端验证。Windows 未识别 Jinkra 的两个端点。")
        return 2
    record = sr.voice_input_for(render.description())
    source_format = sr.capture_format(record)
    assert source_format is not None
    mix_format = sr._fmt(48000, 2, sr.QAudioFormat.Float)
    mixed = sr.Mixer(mix_format)
    mixed.mic = sr.MicCapture(mix_format)
    mixed.mic_target = 480
    mixed.volume = 1.0
    mixed.open(QIODevice.ReadOnly)
    adapter = sr.MicCapture(mix_format, src_fmt=source_format)
    source = QAudioSource(record, source_format)
    sink = QAudioSink(render, mix_format)
    io = source.start()
    try:
        assert io is not None and source.error().name == "NoError"
        sink.start(mixed)
        assert sink.state().name != "StoppedState"
        pcm_time = np.arange(48000, dtype=np.float32) / 48000
        for block in np.array_split(pcm_time, 10):
            voice = np.float32(0.12) * np.sin(2 * np.pi * 380 * block)
            effects = np.float32(0.12) * np.sin(2 * np.pi * 900 * block)
            voice = np.repeat(voice[:, None], 2, axis=1)
            effects = np.repeat(effects[:, None], 2, axis=1)
            mixed.mic.push(voice.tobytes() * 2)
            assert mixed.trigger(effects)
            deadline = time.monotonic() + 0.1
            while time.monotonic() < deadline:
                QTest.qWait(10)
                adapter.push(bytes(io.readAll()))
        frames = min(24000, adapter.pushed)
        assert frames >= 12000
        received = adapter.pull(frames, 0)[:, 0]
        emitted = []
        for hz in (380, 900):
            t = np.arange(len(received), dtype=np.float32) / 48000
            strength = abs(np.dot(received, np.exp(-2j * np.pi * hz * t))) / len(t)
            emitted.append(float(strength))
        assert min(emitted) > 0.003, emitted
        print("虚拟麦克风录到了两路合成信号", emitted)
        return 0
    finally:
        sink.stop()
        source.stop()
        mixed.close()
        app.quit()


if __name__ == "__main__":
    raise SystemExit(run())
