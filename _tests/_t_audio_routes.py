"""Jinkra 端点筛选、混音与无驱动回退。"""

import sys
from pathlib import Path
import numpy as np
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sr_roulette as sr


def device(name: str):
    return SimpleNamespace(description=lambda: name)


def main() -> None:
    app = QApplication([])
    render = device("扬声器 (Jinkra Mix Input)")
    mic = device("麦克风 (2- Jinkra Virtual Mic)")
    external = device("Voicemeeter Input (VB-Audio Voicemeeter VAIO)")
    inputs = [device("CABLE Output (VB-Audio Virtual Cable)")]
    outputs = [render, external]
    with patch.object(sr, "virtual_outputs", return_value=outputs), \
         patch.object(sr, "all_inputs", return_value=inputs):
        assert sr.guess_virtual_output() is None
        assert "还缺少录音设备" in sr.virtual_route_status()[1]
        assert sr.voice_input_for(external.description()) is None
        inputs.append(mic)
        assert sr.guess_virtual_output() is render
        assert sr.voice_input_for(render.description()) is mic
        outputs.remove(render)
        assert "还缺少播放端" in sr.virtual_route_status()[1]
        outputs.append(render)
        inputs.append(device("Jinkra Virtual Mic"))
        assert sr.guess_virtual_output() is None
        assert "多个 Jinkra 端点" in sr.virtual_route_status()[1]
    assert sr.is_virtual_name(mic.description())
    cable_out = device("CABLE Input (VB-Audio Virtual Cable)")
    cable_in = device("CABLE Output (VB-Audio Virtual Cable)")
    with patch.object(sr.QMediaDevices, "audioOutputs",
                      return_value=[device("耳机 (USB)"), cable_out,
                                    device("CABLE In 16ch (VB-Audio Virtual Cable)")]), \
         patch.object(sr, "all_inputs", return_value=[cable_in, device("USB Mic")]):
        assert sr.virtual_outputs() == [cable_out]
        assert sr.guess_virtual_output() is cable_out
        assert sr.voice_input_for(cable_out.description()) is cable_in
        assert sr.voice_mic_name(cable_out) == "CABLE Output"
    with patch.object(sr, "virtual_outputs", return_value=[render, cable_out]), \
         patch.object(sr, "all_inputs", return_value=[mic, cable_in]):
        assert sr.guess_virtual_output() is render  # 自带驱动优先
        assert sr.voice_mic_name() == "Jinkra Virtual Mic"
    # 中文 Windows 静默安装后的真实端点名（播放端叫「扬声器」）
    zh_out = device("扬声器 (VB-Audio Virtual Cable)")
    with patch.object(sr.QMediaDevices, "audioOutputs",
                      return_value=[device("耳机 (ROG PELTA (2.4GHz))"), device("扬声器 (Realtek(R) Audio)"),
                                    zh_out, device("CABLE In 16 Ch (VB-Audio Virtual Cable)")]), \
         patch.object(sr, "all_inputs", return_value=[device("耳机式麦克风 (ROG PELTA (2.4GHz))"), cable_in,
                                                       device("麦克风阵列 (Realtek(R) Audio)")]):
        assert sr.virtual_outputs() == [zh_out], sr.virtual_outputs()
        assert sr.virtual_route_status() == (zh_out, "")
        assert sr.voice_input_for(zh_out.description()) is cable_in
        assert sr.voice_mic_name(zh_out) == "CABLE Output"
    assert not sr.VB_CABLE.render_matches("扬声器 (Realtek(R) Audio)")
    assert not sr.VB_CABLE.render_matches("Voicemeeter Input (VB-Audio Voicemeeter VAIO)")
    with patch.object(sr, "virtual_outputs", return_value=[cable_out]), \
         patch.object(sr, "all_inputs", return_value=[]):
        assert "VB-CABLE" in sr.virtual_route_status()[1]
    with patch.object(sr, "virtual_outputs", return_value=[]), \
         patch.object(sr, "all_inputs", return_value=[device("CABLE Output (Some Other Driver)")]):
        assert sr.virtual_route_status() == (None, "Windows 当前未检测到虚拟麦克风。")
    physical = device("USB Mic")
    with patch.object(sr, "find_input", return_value=physical):
        assert sr.capture_candidates("USB Mic") == [physical]
    with patch.object(sr, "find_input", return_value=None):
        assert sr.capture_candidates("Offline USB Mic") == []

    fmt = sr._fmt(48000, 2, sr.QAudioFormat.Float)
    mixed = sr.Mixer(fmt)
    mixed.volume = 1.0
    mixed.mic_gain = 1.0
    mixed.mic_target = 2400
    mixed.mic = sr.MicCapture(fmt)
    frames = 2400
    time = np.arange(frames, dtype=np.float32) / 48000
    mic_pcm = np.repeat((0.15 * np.sin(2 * np.pi * 380 * time))[:, None], 2, axis=1)
    effects = np.repeat((0.15 * np.sin(2 * np.pi * 900 * time))[:, None], 2, axis=1)
    mixed.mic.push(mic_pcm.astype(np.float32).tobytes() * 2)
    assert mixed.trigger(effects.astype(np.float32))
    received = np.frombuffer(mixed.readData(frames * 8), dtype=np.float32).reshape(-1, 2)
    spectrum = np.abs(np.fft.rfft(received[:, 0]))
    assert spectrum[19] > 100 and spectrum[45] > 100, spectrum[[19, 45]]
    cfg = dict(sr.DEFAULT_CONFIG, mic_enabled=True, monitor_enabled=False)
    engine = sr.AudioEngine(sr.SoundBank(20), cfg)
    with patch.object(sr, "guess_virtual_output", return_value=None), \
         patch.object(engine, "restart_capture") as capture, \
         patch.object(engine, "_start_monitor_sink") as monitor:
        engine.rebuild()
        capture.assert_not_called()
        monitor.assert_called_once()
        assert not engine.audio_status()["cable_active"]
    print("Jinkra 端点配对、实体麦克风固定、双源混音及本地播放回退通过")
    app.quit()


if __name__ == "__main__":
    main()
