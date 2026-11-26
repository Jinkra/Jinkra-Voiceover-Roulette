"""验证打包后的 Qt 界面、音频解码和手柄绑定配置。"""

import json
import wave
from pathlib import Path

from PySide6.QtWidgets import QApplication

import sr_roulette as sr
from settings_window import SettingsWindow


def run(report: Path) -> int:
    report = report.resolve()
    data = report.parent / (report.stem + '-data')
    data.mkdir(parents=True, exist_ok=True)
    sr.CONFIG_PATH = data / 'config.json'
    sr.SOUNDS_CONFIG_PATH = data / 'sounds.json'
    sr.SOUNDS_DIR = data / 'sounds'
    sr.LOG_PATH = data / 'startup.log'
    sr.SOUNDS_DIR.mkdir(exist_ok=True)
    with wave.open(str(sr.SOUNDS_DIR / 'startup.wav'), 'wb') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(b'\x00' * 19200)

    app = QApplication([])
    cfg = dict(sr.DEFAULT_CONFIG, help_tip_shown=True, autostart=False,
               mic_enabled=False)
    scfg = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
    scfg.load()
    bank = sr.SoundBank(20, scfg)
    audio = sr.AudioEngine(bank, cfg)
    window = SettingsWindow(cfg, scfg, bank, audio)
    window.show()
    app.processEvents()
    window.detail.hotkey.edit._apply('pad_a')
    saved = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
    saved.load()
    bound = saved.setting('startup.wav').hotkey
    image = report.with_suffix('.png')
    rendered = window.grab().save(str(image))
    clip = audio.clips[0] if audio.clips else None
    decoded_frames = len(clip) if clip is not None else 0
    icon_loaded = not window.windowIcon().pixmap(48, 48).isNull()
    # AI 朗读：页面在导航第二位、离线引擎能加载、系统语音能合成（只合成不播放）
    import tts
    nav = [button.text() for button in window.findChildren(type(window.navigation.button(0)))
           if button.objectName() == "NavItem"]
    nav.sort(key=lambda text: next(b for b in window.navigation.buttons() if b.text() == text).x())
    try:
        import sherpa_onnx
        sherpa_ok = hasattr(sherpa_onnx, "OfflineTts")
    except Exception as error:
        sherpa_ok = f"{type(error).__name__}: {error}"
    pack_frames = None
    for pack in tts.PACKS:
        if tts.installed(sr.BASE_DIR, pack):
            try:
                pack_frames = len(tts.synth_pack(sr.BASE_DIR, pack.groups[0].key, 0, "你好", 1.0)[0])
            except Exception as error:
                pack_frames = f"{type(error).__name__}: {error}"
            break
    voices = tts.system_voices(window.page_speech.helper)
    speech_frames = 0
    if voices:
        try:
            speech_frames = len(tts.synth_system(window.page_speech.helper, voices[0].key, "你好", 1.0)[0])
        except Exception as error:
            speech_frames = f"{error}"
    result = {'icon_loaded': icon_loaded, 'version': sr.APP_VERSION, 'settings_visible': window.isVisible(),
              'decoded_frames': decoded_frames, 'saved_binding': bound,
              'screenshot': str(image), 'rendered': rendered,
              'nav': nav, 'sherpa': sherpa_ok, 'system_voices': len(voices), 'speech_frames': speech_frames, 'pack_frames': pack_frames}
    result['ok'] = bool(result['settings_visible'] and decoded_frames > 0
                        and bound == 'pad_a' and rendered and icon_loaded
                        and nav[1:2] == ['AI 朗读'] and sherpa_ok is True
                        and (not voices or (isinstance(speech_frames, int) and speech_frames > 0))
                        and (pack_frames is None or (isinstance(pack_frames, int) and pack_frames > 0)))
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    window.close()
    audio.stop_outputs()
    return 0 if result['ok'] else 1
