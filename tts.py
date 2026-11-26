"""AI 朗读：把文字合成为语音，送进 Jinkra Voiceover Roulette 的混音（自己的耳机 + 虚拟麦克风）。

两类音色：
- 系统语音：Windows 自带的语音（慧慧、康康、瑶瑶……），由 native/Tts.cs 编译出的
  jinkra-tts.exe 调用，不需要下载。
- 朗读包：sherpa-onnx（Apache-2.0）离线神经网络语音。模型做成可选下载的朗读包，
  从 k2-fsa/sherpa-onnx 的官方发布下载，经 GitHub 直连或国内加速线路，按 SHA-256 校验。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

import updates

MODEL_BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_CHARS = 2000


# ---------------------------------------------------------------- 朗读包

@dataclass(frozen=True)
class VoiceGroup:
    key: str          # 写进配置的音色键：pack:<包>:<组>
    label: str        # 下拉框里的名字
    first: int        # 这一组在模型里的第一个 speaker id
    count: int        # 这一组有几个音色


@dataclass(frozen=True)
class Pack:
    id: str
    name: str
    summary: str
    license: str
    archive: str      # 官方发布里的文件名（不含 .tar.bz2）
    size: int
    sha256: str
    kind: str         # vits | kokoro
    groups: tuple = field(default_factory=tuple)

    @property
    def url(self) -> str:
        return f"{MODEL_BASE}{self.archive}.tar.bz2"


PACKS = (
    Pack("xiaoya", "小雅", "中文女声，清晰自然，14 MB", "模型 MIT；训练数据（标贝）仅限非商业用途",
         "vits-piper-zh_CN-xiao_ya-medium-int8", 14016124,
         "eab027e194e70289233cf12308373611fa4e2e96ef2d97354ef433ab663d831f", "vits",
         (VoiceGroup("pack:xiaoya", "小雅（女声）", 0, 1),)),
    Pack("chaowen", "超文", "中文男声，14 MB", "模型 MIT；训练数据 CC0，可自由使用",
         "vits-piper-zh_CN-chaowen-medium-int8", 14011298,
         "f5f7c8628427fbb259ea4b7ec1a9a822a0c04e3f267071f0abfa0610371d9e0c", "vits",
         (VoiceGroup("pack:chaowen", "超文（男声）", 0, 1),)),
    Pack("kokoro", "Kokoro 多音色", "103 种音色：中文女声 55、男声 45、英文 3，中英混读，147 MB",
         "Apache-2.0", "kokoro-int8-multi-lang-v1_1", 147052523,
         "259c9c8bc906d6078e4e0570421885dabb68b539c2f970fcbb890a58eeaf3e9c", "kokoro",
         (VoiceGroup("pack:kokoro:zf", "Kokoro 中文女声", 3, 55),
          VoiceGroup("pack:kokoro:zm", "Kokoro 中文男声", 58, 45),
          VoiceGroup("pack:kokoro:en", "Kokoro 英文女声", 0, 3))),
)
_SKIP = ("rule.far",)  # 体积大（180 MB）的文本规整文件，朗读用不上


def pack_by_id(pack_id: str) -> Pack | None:
    return next((p for p in PACKS if p.id == pack_id), None)


def pack_dir(base: Path, pack: Pack) -> Path:
    return Path(base) / "models" / "tts" / pack.id


def installed(base: Path, pack: Pack) -> bool:
    return (pack_dir(base, pack) / ".installed").is_file()


def remove(base: Path, pack: Pack) -> None:
    with _ENGINE_LOCK:
        _ENGINES.pop(pack.id, None)
    shutil.rmtree(pack_dir(base, pack), ignore_errors=True)


def _routes():
    """国内加速线路优先，GitHub 直连兜底。"""
    return sorted(updates.ROUTES, key=lambda route: route[1] == "")


def download(base: Path, pack: Pack, progress=lambda percent, route: None, cancelled=lambda: False) -> Path:
    """下载、校验并解压一个朗读包。在后台线程调用。"""
    target = pack_dir(base, pack)
    target.parent.mkdir(parents=True, exist_ok=True)
    errors = []
    with tempfile.TemporaryDirectory(prefix="jinkra-tts-", dir=target.parent) as temp:
        archive = Path(temp) / "pack.tar.bz2"
        for name, prefix in _routes():
            try:
                digest = hashlib.sha256()
                received = 0
                progress(0, name)
                with updates._open(prefix + pack.url, hosts=updates._DOWNLOADS, timeout=15) as source, \
                        archive.open("wb") as output:
                    while block := source.read(1 << 17):
                        if cancelled():
                            raise InterruptedError("已取消")
                        received += len(block)
                        if received > pack.size:
                            raise ValueError("文件大小与官方发布不一致")
                        digest.update(block)
                        output.write(block)
                        progress(received * 100 // pack.size, name)
                if received != pack.size or digest.hexdigest() != pack.sha256:
                    raise ValueError("校验失败")
                break
            except InterruptedError:
                raise
            except Exception as error:  # 换下一条线路
                errors.append(f"{name}：{error}")
        else:
            raise OSError("朗读包下载失败。" + "；".join(errors))
        progress(100, "正在解压")
        staging = Path(temp) / "unpacked"
        root = staging.resolve()
        with tarfile.open(archive, "r:bz2") as bundle:
            for member in bundle.getmembers():
                parts = Path(member.name).parts
                if len(parts) < 2 or parts[-1] in _SKIP:
                    continue
                if not (member.isfile() or member.isdir()):
                    continue
                destination = (root / Path(*parts[1:])).resolve()
                if root != destination and root not in destination.parents:
                    raise OSError("朗读包内容异常")
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output, 1 << 20)
        (staging / ".installed").write_text(pack.sha256, encoding="ascii")
        remove(base, pack)
        shutil.move(str(staging), str(target))
    return target


# ---------------------------------------------------------------- 音色列表

@dataclass(frozen=True)
class Voice:
    key: str          # sys:<系统语音ID> 或 pack:<包>[:<组>]
    label: str
    count: int = 1    # >1 时界面显示「音色编号」
    pack: str = ""


def helper_path(base: Path, resources: Path) -> Path | None:
    for candidate in (Path(resources) / "jinkra-tts.exe", Path(base) / "build" / "jinkra-tts.exe"):
        if candidate.is_file():
            return candidate
    return None


_SYSTEM_CACHE: list[Voice] | None = None
_NAMES = {"Huihui": "慧慧", "Yaoyao": "瑶瑶", "Kangkang": "康康", "Xiaoxiao": "晓晓", "Yunyang": "云扬",
          "Hanhan": "涵涵", "Zhiwei": "志玮", "Tracy": "Tracy", "Danny": "Danny"}


def system_voices(helper: Path | None, refresh: bool = False) -> list[Voice]:
    global _SYSTEM_CACHE
    if _SYSTEM_CACHE is not None and not refresh:
        return list(_SYSTEM_CACHE)
    voices: list[Voice] = []
    if helper is not None and sys.platform == "win32":
        try:
            result = subprocess.run([str(helper), "list"], capture_output=True, timeout=20,
                                    creationflags=NO_WINDOW)
            for line in result.stdout.decode("utf-8", "replace").splitlines():
                parts = line.split("\t")
                if len(parts) < 4 or not parts[0]:
                    continue
                name = parts[1].replace("Microsoft ", "").replace(" Desktop", "")
                name = _NAMES.get(name.split(" ")[0], name)
                gender = "男声" if parts[3].lower().startswith("m") else "女声"
                lang = {"zh-CN": "中文", "en-US": "英文", "zh-TW": "台湾中文", "zh-HK": "粤语",
                        "ja-JP": "日语"}.get(parts[2], parts[2])
                voices.append(Voice("sys:" + parts[0], f"系统 · {name}（{lang}{gender}）"))
        except (OSError, subprocess.SubprocessError):
            pass
    _SYSTEM_CACHE = voices
    return list(voices)


def pack_voices(base: Path) -> list[Voice]:
    return [Voice(group.key, group.label, group.count, pack.id)
            for pack in PACKS if installed(base, pack) for group in pack.groups]


def group_of(key: str) -> tuple[Pack, VoiceGroup] | None:
    for pack in PACKS:
        for group in pack.groups:
            if group.key == key:
                return pack, group
    return None


# ---------------------------------------------------------------- 合成

def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as source:
        rate, channels, width = source.getframerate(), source.getnchannels(), source.getsampwidth()
        raw = source.readframes(source.getnframes())
    if width != 2:
        raise OSError("系统语音返回了不支持的音频格式")
    data = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, rate


def synth_system(helper: Path, voice_key: str, text: str, speed: float) -> tuple[np.ndarray, int]:
    with tempfile.TemporaryDirectory(prefix="jinkra-say-") as temp:
        out = Path(temp) / "say.wav"
        result = subprocess.run([str(helper), "speak", voice_key[4:], f"{speed:.2f}", str(out)],
                                input=text.encode("utf-8"), capture_output=True, timeout=120,
                                creationflags=NO_WINDOW)
        if result.returncode != 0 or not out.is_file():
            message = result.stderr.decode("utf-8", "replace").strip()
            raise OSError(message or "系统语音合成失败")
        return _read_wav(out)


_ENGINES: dict = {}
_ENGINE_LOCK = threading.Lock()


def _engine(base: Path, pack: Pack):
    """加载朗读包模型（约 1~2 秒）。只常驻一个，换包时释放上一个。"""
    with _ENGINE_LOCK:
        engine = _ENGINES.get(pack.id)
        if engine is not None:
            return engine
        import sherpa_onnx as so

        folder = pack_dir(base, pack)
        threads = max(1, min(4, (os.cpu_count() or 2)))
        if pack.kind == "kokoro":
            model = so.OfflineTtsModelConfig(
                kokoro=so.OfflineTtsKokoroModelConfig(
                    model=str(folder / "model.int8.onnx"), voices=str(folder / "voices.bin"),
                    tokens=str(folder / "tokens.txt"), data_dir=str(folder / "espeak-ng-data"),
                    dict_dir=str(folder / "dict"),
                    lexicon=f"{folder / 'lexicon-us-en.txt'},{folder / 'lexicon-zh.txt'}"),
                num_threads=threads, provider="cpu")
            fsts = ("date-zh.fst", "phone-zh.fst", "number-zh.fst")
        else:
            onnx = next(folder.glob("*.onnx"))
            model = so.OfflineTtsModelConfig(
                vits=so.OfflineTtsVitsModelConfig(model=str(onnx), lexicon=str(folder / "lexicon.txt"),
                                                  tokens=str(folder / "tokens.txt")),
                num_threads=threads, provider="cpu")
            fsts = ("phone.fst", "date.fst", "number.fst")
        config = so.OfflineTtsConfig(
            model=model, max_num_sentences=1,
            rule_fsts=",".join(str(folder / name) for name in fsts if (folder / name).is_file()))
        engine = so.OfflineTts(config)
        _ENGINES.clear()
        _ENGINES[pack.id] = engine
        return engine


def synth_pack(base: Path, voice_key: str, index: int, text: str, speed: float,
               on_chunk=None, cancelled=lambda: False) -> tuple[np.ndarray, int]:
    """用朗读包合成。on_chunk(samples, rate) 每合成完一句就回调一次，用来边合成边播放。"""
    found = group_of(voice_key)
    if found is None:
        raise OSError("这个朗读包音色不存在")
    pack, group = found
    if not installed(base, pack):
        raise OSError(f"请先安装朗读包「{pack.name}」")
    engine = _engine(base, pack)
    sid = group.first + max(0, min(group.count - 1, int(index)))
    rate = engine.sample_rate

    def callback(samples, _progress):
        if on_chunk is not None and len(samples):
            on_chunk(np.array(samples, dtype=np.float32), rate)
        return 0 if cancelled() else 1

    audio = engine.generate(text, sid=sid, speed=float(speed), callback=callback)
    return np.array(audio.samples, dtype=np.float32), audio.sample_rate


def save_wav(path: Path, samples: np.ndarray, rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(int(rate))
        target.writeframes(pcm.tobytes())
