"""Jinkra Voiceover Roulette - 音频环境探针

用途：在动手写任何功能前，先确认本机音频设备现状。
只读，不装驱动、不改系统、不碰游戏。

运行：python probe_audio.py
"""

import sys
import platform

from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaDevices

from sr_roulette import APP_NAME, guess_virtual_output, is_virtual_name, voice_input_for


def main() -> int:
    app = QApplication(sys.argv)          # noqa: F841  QMediaDevices 需要 Qt 应用实例
    print("=" * 58)
    print(f"{APP_NAME} - 音频环境检查")
    print("=" * 58)
    print(f"系统      : {platform.system()} {platform.release()} ({platform.version()})")

    outs = QMediaDevices.audioOutputs()
    ins = QMediaDevices.audioInputs()

    print(f"\n[输出设备] 共 {len(outs)} 个")
    for d in outs:
        tag = "  <虚拟>" if is_virtual_name(d.description()) else ""
        default = " (系统默认)" if d == QMediaDevices.defaultAudioOutput() else ""
        print(f"  - {d.description()}{default}{tag}")

    print(f"\n[输入设备] 共 {len(ins)} 个")
    for d in ins:
        tag = "  <虚拟>" if is_virtual_name(d.description()) else ""
        default = " (系统默认)" if d == QMediaDevices.defaultAudioInput() else ""
        print(f"  - {d.description()}{default}{tag}")

    print("\n" + "-" * 58)
    output = guess_virtual_output()
    target = voice_input_for(output.description()) if output is not None else None
    if target is not None:
        print(f"[配对] Jinkra 播放端 {output.description()}")
        print(f"[配对] 游戏录音端 {target.description()}")
    else:
        print("[配对] 未检测到可自动配对的语音设备。")

    print("\n[提示] 本脚本只读取设备列表，未启动任何音频流。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
