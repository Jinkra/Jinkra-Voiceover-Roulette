"""AI 麦克风降噪：RNNoise（xiph.org 的循环神经网络降噪，BSD-3 许可）。

模型和推理库编译在同一个 rnnoise.dll 里，取自 PyPI 上 pyrnnoise 的 Windows 包
（Apache-2.0）。为了不让安装包多出 15 MB，模型在用户点「安装降噪模型」时才下载：
依次尝试清华、阿里云 PyPI 镜像和官方 PyPI，整包与 DLL 都用固定的 SHA-256 校验。
"""

import ctypes
import hashlib
import io
import os
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

WHEEL_PATH = ("packages/e3/a0/d15da42873e1a8474c9147de59845345ba91e495e6a2f505dfd30d39cfde/"
              "pyrnnoise-0.4.6-py3-none-win_amd64.whl")
WHEEL_SHA256 = "f34c07815581e110a84e820e7abf452578ad6d2d8af4b4178e2541d247e2d634"
WHEEL_SIZE = 13263771
DLL_MEMBER = "pyrnnoise-0.4.6.data/purelib/pyrnnoise/rnnoise.dll"
DLL_SHA256 = "2ed431c1e2924d7f8c0e2b785d8f3a55a84b9cdda649b0e7a82392636244ec1d"
MIRRORS = (
    ("清华镜像", "https://pypi.tuna.tsinghua.edu.cn/"),
    ("阿里云镜像", "https://mirrors.aliyun.com/pypi/"),
    ("PyPI 官方", "https://files.pythonhosted.org/"),
)
SAMPLE_RATE = 48000
FRAME = 480          # RNNoise 每次处理 10ms
NOTICE = """Jinkra Voiceover Roulette 的 AI 降噪模型

rnnoise.dll 来自 pyrnnoise 0.4.6（Apache License 2.0，https://github.com/pengzhendong/pyrnnoise），
其中的 RNNoise 推理代码和模型由 Xiph.Org 等发布（BSD 3-Clause，https://github.com/xiph/rnnoise）。
删除本文件夹即可移除降噪模型。
"""


def model_dir(base: Path) -> Path:
    return Path(base) / "models" / "rnnoise"


def model_path(base: Path) -> Path:
    return model_dir(base) / "rnnoise.dll"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def installed(base: Path) -> bool:
    path = model_path(base)
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _fetch(url: str, progress) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Jinkra-Voiceover-Roulette"})
    with urllib.request.urlopen(request, timeout=20) as response:
        if not response.geturl().startswith("https://"):
            raise OSError("下载地址被重定向到了非 HTTPS 站点。")
        chunks, total = [], 0
        while True:
            block = response.read(1 << 16)
            if not block:
                break
            total += len(block)
            if total > WHEEL_SIZE:
                raise OSError("降噪模型大小异常。")
            chunks.append(block)
            progress(total * 100 // WHEEL_SIZE)
    return b"".join(chunks)


def download(base: Path, progress=lambda percent, route: None) -> Path:
    """下载并安装降噪模型，返回 DLL 路径。在后台线程里调用。"""
    errors = []
    for name, prefix in MIRRORS:
        try:
            wheel = _fetch(prefix + WHEEL_PATH, lambda p, n=name: progress(p, n))
            if _sha256(wheel) != WHEEL_SHA256:
                raise OSError("校验失败")
            with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
                dll = archive.read(DLL_MEMBER)
            if _sha256(dll) != DLL_SHA256:
                raise OSError("模型文件校验失败")
            break
        except Exception as error:  # 换下一条线路
            errors.append(f"{name}：{error}")
    else:
        raise OSError("降噪模型下载失败。" + "；".join(errors))
    folder = model_dir(base)
    folder.mkdir(parents=True, exist_ok=True)
    target = model_path(base)
    partial = target.with_suffix(".part")
    partial.write_bytes(dll)
    partial.replace(target)
    (folder / "说明.txt").write_text(NOTICE, encoding="utf-8")
    return target


_LIB = None


def _load(base: Path):
    global _LIB
    if _LIB is None:
        path = model_path(base)
        if sys.platform != "win32" or not path.is_file():
            raise OSError("降噪模型未安装")
        if _sha256(path.read_bytes()) != DLL_SHA256:
            raise OSError("降噪模型文件已损坏，请重新安装")
        # rnnoise.dll 依赖 VCRUNTIME140.dll。打包版把它放在解包目录里，
        # 而 ctypes 默认不搜索那里；没装 VC++ 运行库的电脑会加载失败。
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(bundle)
        lib = ctypes.CDLL(str(path))
        lib.rnnoise_create.argtypes = [ctypes.c_void_p]
        lib.rnnoise_create.restype = ctypes.c_void_p
        lib.rnnoise_destroy.argtypes = [ctypes.c_void_p]
        lib.rnnoise_destroy.restype = None
        lib.rnnoise_process_frame.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float),
                                              ctypes.POINTER(ctypes.c_float)]
        lib.rnnoise_process_frame.restype = ctypes.c_float
        if lib.rnnoise_get_frame_size() != FRAME:
            raise OSError("降噪模型版本不匹配")
        _LIB = lib
    return _LIB


class Denoiser:
    """把 48kHz 的麦克风数据按 10ms 一帧送进 RNNoise。

    多声道先混成单声道降噪，再按原声道数铺回去（麦克风本来就是单声道信号）。
    不满一帧的尾巴留到下一次，因此最多多出 10ms 延迟。
    """

    def __init__(self, base: Path, lib=None) -> None:
        self.lib = lib or _load(base)
        self.state = self.lib.rnnoise_create(None)
        if not self.state:
            raise OSError("降噪模型初始化失败")
        self._pending = np.zeros(0, dtype=np.float32)
        self.voice = 0.0   # 最近一帧的说话概率

    def process(self, arr: np.ndarray) -> np.ndarray:
        """arr: (帧数, 声道) float32，-1~1。返回降噪后的整帧部分。"""
        channels = arr.shape[1]
        mono = arr.mean(axis=1) if channels > 1 else arr[:, 0]
        data = np.concatenate([self._pending, mono.astype(np.float32)])
        usable = len(data) // FRAME * FRAME
        self._pending = data[usable:].copy()
        if usable == 0:
            return np.zeros((0, channels), dtype=np.float32)
        frames = np.ascontiguousarray(data[:usable] * 32768.0, dtype=np.float32)
        for offset in range(0, usable, FRAME):
            frame = frames[offset:offset + FRAME].ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            self.voice = float(self.lib.rnnoise_process_frame(self.state, frame, frame))
        out = np.clip(frames / 32768.0, -1.0, 1.0).astype(np.float32)
        return np.repeat(out[:, None], channels, axis=1) if channels > 1 else out[:, None]

    def reset(self) -> None:
        self._pending = self._pending[:0]

    def close(self) -> None:
        if self.state:
            self.lib.rnnoise_destroy(self.state)
            self.state = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


class ModelInstaller:
    """「安装降噪模型」按钮背后的后台下载。用计时器轮询，避免跨线程碰 Qt 对象。"""

    def __init__(self, base: Path) -> None:
        self.base = Path(base)
        self._executor = None
        self._future = None
        self.percent = 0
        self.route = ""
        self.error = ""

    @property
    def busy(self) -> bool:
        return self._future is not None and not self._future.done()

    def start(self) -> None:
        if self.busy:
            return
        self.error = ""
        self.percent = 0
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1)
        self._future = self._executor.submit(download, self.base, self._report)

    def _report(self, percent, route) -> None:
        self.percent, self.route = int(percent), route

    def finished(self):
        """下载结束返回 True/False（成功/失败），还在下载返回 None。"""
        if self._future is None or not self._future.done():
            return None
        future, self._future = self._future, None
        try:
            future.result()
        except Exception as error:
            self.error = str(error)
            return False
        return True
