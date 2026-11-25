"""一键安装虚拟麦克风，并跟踪 Windows 安装程序的结果。

默认安装 VB-Audio 的 VB-CABLE：它带微软签名，开着 Secure Boot 的 Windows 也能直接加载。
EXE 内原样附带官方驱动包（不做任何修改），点击后在本地解压，并以管理员身份打开
VB-Audio 自己的安装窗口。若构建内附带了微软签回的 Jinkra 驱动，则优先安装 Jinkra 驱动。
"""

import ctypes
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes as win
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication


APP_NAME = "Jinkra Voiceover Roulette"
DRIVER_FILES = ("JinkraVad.inf", "JinkraVad.cat", "JinkraVad.sys")

# VB-CABLE 官方驱动包。文件名带版本号，内容固定，用 SHA-256 锁定。
VB_CABLE_PACK = "VBCABLE_Driver_Pack46.zip"
VB_CABLE_URL = "https://download.vb-audio.com/Download_CABLE/" + VB_CABLE_PACK
VB_CABLE_SHA256 = "bc44e8974191a5a2427d6c979e2dab08dbb09925f3f435dfa2f0ba3e45b6eb90"
VB_CABLE_SETUP = "VBCABLE_Setup_x64.exe"
VB_CABLE_MAX = 16 * 1024 * 1024
ENDPOINT_WAIT = 25.0  # 安装程序退出后，等 Windows 枚举出端点的最长秒数


def _helper(directory, resources):
    helper = resources / "jinkra-driver-helper.exe"
    if not helper.is_file() and resources == directory / "assets":
        helper = directory / "build" / "jinkra-driver-helper.exe"
    return helper if helper.is_file() else None


def _has_package(package):
    return all((package / name).is_file() for name in DRIVER_FILES)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def _valid_pack(path):
    return path.is_file() and _sha256(path) == VB_CABLE_SHA256


def _download_pack(destination):
    """从 VB-Audio 官网下载驱动包。只在构建未附带驱动包时使用。"""
    request = urllib.request.Request(VB_CABLE_URL, headers={"User-Agent": APP_NAME})
    partial = destination.with_suffix(".part")
    with urllib.request.urlopen(request, timeout=30) as response, open(partial, "wb") as target:
        if not response.geturl().startswith("https://download.vb-audio.com/"):
            raise OSError("VB-CABLE 下载地址被重定向到了非官方站点。")
        total = 0
        for block in iter(lambda: response.read(1 << 16), b""):
            total += len(block)
            if total > VB_CABLE_MAX:
                raise OSError("VB-CABLE 驱动包大小异常。")
            target.write(block)
    if _sha256(partial) != VB_CABLE_SHA256:
        partial.unlink(missing_ok=True)
        raise OSError("下载的 VB-CABLE 驱动包校验失败，请稍后重试。")
    partial.replace(destination)
    return destination


def _extract_pack(pack, stage):
    if not _valid_pack(pack):
        raise OSError("VB-CABLE 驱动包校验失败，请重新下载完整的 Jinkra Voiceover Roulette。")
    root = stage.resolve()
    with zipfile.ZipFile(pack) as archive:
        for member in archive.infolist():
            target = (root / member.filename).resolve()
            if root not in target.parents:
                raise OSError("VB-CABLE 驱动包内容异常。")
        archive.extractall(root)
    setup = root / VB_CABLE_SETUP
    if not setup.is_file():
        raise OSError("VB-CABLE 驱动包缺少安装程序。")
    return setup


class _ShellExecuteInfo(ctypes.Structure):
    _fields_ = [
        ("size", win.DWORD), ("mask", win.ULONG), ("owner", win.HWND),
        ("verb", win.LPCWSTR), ("file", win.LPCWSTR), ("parameters", win.LPCWSTR),
        ("directory", win.LPCWSTR), ("show", ctypes.c_int), ("result", win.HINSTANCE),
        ("id_list", ctypes.c_void_p), ("class_name", win.LPCWSTR), ("class_key", win.HKEY),
        ("hot_key", win.DWORD), ("icon_or_monitor", win.HANDLE), ("process", win.HANDLE),
    ]


class _InstallProcess:
    def __init__(self, handle):
        self.handle = handle
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.exit_code = kernel.GetExitCodeProcess
        self.exit_code.argtypes = (win.HANDLE, ctypes.POINTER(win.DWORD))
        self.exit_code.restype = win.BOOL
        self.close_handle = kernel.CloseHandle
        self.close_handle.argtypes = (win.HANDLE,)
        self.close_handle.restype = win.BOOL

    def result(self):
        code = win.DWORD()
        if not self.exit_code(self.handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return None if code.value == 259 else code.value  # STILL_ACTIVE

    def close(self):
        self.close_handle(self.handle)


def _run_elevated(program, parameters, owner, show):
    shell = ctypes.WinDLL("shell32", use_last_error=True).ShellExecuteExW
    shell.argtypes = (ctypes.POINTER(_ShellExecuteInfo),)
    shell.restype = win.BOOL
    info = _ShellExecuteInfo(size=ctypes.sizeof(_ShellExecuteInfo), mask=0x440, owner=owner,
                             verb="runas", file=str(program), parameters=parameters,
                             directory=str(program.parent), show=show)
    if not shell(ctypes.byref(info)):
        error = ctypes.get_last_error()
        if error == 1223:
            raise OSError("已取消 Windows 管理员确认。")
        raise ctypes.WinError(error)
    if not info.process:
        raise OSError("Windows 没有返回安装程序的运行状态。请重新检测设备。")
    return _InstallProcess(info.process)


def _start_install(helper, package, owner):
    """安装微软签回的 Jinkra 驱动。"""
    package = package.resolve()
    if not _has_package(package):
        raise OSError("驱动包不完整，请重新获取 Jinkra Voiceover Roulette 正式安装包。")
    with (package / "JinkraVad.inf").open("rb") as source:
        raw = source.read(65536)
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    if not re.search(r"^\s*%[^%\r\n]+%\s*=[^,\r\n]+,\s*ROOT\\JINKRAVAD\s*$",
                     raw.decode(encoding, errors="replace"), re.IGNORECASE | re.MULTILINE):
        raise OSError("这个驱动包与 Jinkra Virtual Mic 不匹配。")
    return _run_elevated(helper.resolve(), subprocess.list2cmdline(["install", str(package)]), owner, 0)


def _start_vb_cable(setup, owner):
    """以管理员身份打开 VB-Audio 自己的安装窗口，由用户在其中确认安装。"""
    return _run_elevated(setup.resolve(), "", owner, 1)


class DriverInstallation(QObject):
    changed = Signal()
    installed = Signal(object)

    def __init__(self, directory, resources, parent, route_ready=None):
        super().__init__(parent)
        self.directory = directory
        self.resources = resources
        self.route_ready = route_ready or (lambda: False)
        self.message = ""
        self.process = None
        self._download = None
        self._executor = None
        self._waiting_since = None
        self._owner = None
        self._stage = None
        self.timer = QTimer(self, interval=350)
        self.timer.timeout.connect(self._poll)

    # ---- 驱动来源 ----
    def _package(self):
        return next((path for path in (self.resources / "VirtualMic", self.directory / "VirtualMic")
                     if _has_package(path)), None)

    def _uses_jinkra(self):
        return self._package() is not None and _helper(self.directory, self.resources) is not None

    def _bundled_pack(self):
        for path in (self.resources / VB_CABLE_PACK, self.directory / "build" / VB_CABLE_PACK):
            if path.is_file():
                return path
        return None

    # ---- 状态 ----
    def busy(self):
        return self.process is not None or self._download is not None or self._waiting_since is not None

    def can_install(self):
        return not self.busy() and (self._uses_jinkra() or sys.platform == "win32")

    def installing_from(self, parent):
        return self.busy() and self._owner is parent

    def hint(self):
        if self.message:
            return self.message
        if self._uses_jinkra():
            return "点击安装并确认 Windows 提示，完成后自动启用送声。"
        if sys.platform != "win32":
            return "虚拟麦克风仅支持 Windows。"
        return ("点击「安装虚拟麦克风」，确认 Windows 管理员提示，再在 VB-CABLE 窗口中点击"
                "「Install Driver」。VB-CABLE 由 VB-Audio 提供（捐赠软件，vb-cable.com）。")

    # ---- 安装 ----
    def install(self, parent):
        if self.busy():
            return
        self._owner = parent
        try:
            if self._uses_jinkra():
                self._install_jinkra(parent)
            else:
                pack = self._bundled_pack()
                if pack is not None and _valid_pack(pack):
                    self._launch_vb_cable(pack)
                else:
                    self._stage = Path(tempfile.mkdtemp(prefix="jinkra-vbcable-"))
                    self._executor = ThreadPoolExecutor(max_workers=1)
                    self._download = self._executor.submit(_download_pack, self._stage / VB_CABLE_PACK)
                    self.message = "正在从 VB-Audio 官网下载 VB-CABLE。"
        except OSError as error:
            self._fail(str(error))
            return
        self.timer.start()
        self.changed.emit()

    def _install_jinkra(self, parent):
        # 安装包由提升权限后的独立进程读取，须独立于便携 EXE 的解包生命周期。
        package = self._package()
        self._stage = Path(tempfile.mkdtemp(prefix="jinkra-driver-"))
        for name in DRIVER_FILES:
            shutil.copyfile(package / name, self._stage / name)
        self.process = _start_install(_helper(self.directory, self.resources), self._stage,
                                      int(parent.winId()))
        self.message = "正在安装 Jinkra Virtual Mic。"

    def _launch_vb_cable(self, pack):
        if self._stage is None:
            self._stage = Path(tempfile.mkdtemp(prefix="jinkra-vbcable-"))
        setup = _extract_pack(pack, self._stage / "VBCABLE")
        self.process = _start_vb_cable(setup, int(self._owner.winId()) if self._owner else 0)
        self.message = "请在 VB-CABLE 窗口中点击「Install Driver」，完成后关闭该窗口。"

    def _poll(self):
        try:
            if self._download is not None:
                if not self._download.done():
                    return
                future, self._download = self._download, None
                self._launch_vb_cable(future.result())
                self.changed.emit()
                return
            if self.process is not None:
                result = self.process.result()
                if result is None:
                    return
                jinkra = self._uses_jinkra()
                self.process.close()
                self.process = None
                self._clean_stage()
                if jinkra:
                    # 安装助手的退出码可信：成功即启用送声，端点稍后由 Windows 枚举。
                    if result == 0:
                        self._finish(True, "驱动安装已完成。Windows 识别音频端点后会自动送声，"
                                           "必要时请重启 Windows。")
                    else:
                        self._fail("Windows 未完成驱动安装，请重试并确认管理员提示。")
                    return
                self._waiting_since = time.monotonic()
                self.message = "安装程序已结束，正在等待 Windows 识别虚拟麦克风。"
                self.changed.emit()
            if self._waiting_since is not None:
                if self.route_ready():
                    self._finish(True, "虚拟麦克风已安装，已自动启用送声。")
                elif time.monotonic() - self._waiting_since > ENDPOINT_WAIT:
                    self._finish(False, "安装窗口已关闭，但 Windows 还没有出现虚拟麦克风。"
                                        "如果已点击「Install Driver」，请重启电脑后再打开"
                                        f" {APP_NAME}；否则请重新点击安装。")
        except Exception as error:  # 下载、解压或读取进程状态失败
            self._fail(str(error) or "虚拟麦克风安装失败，请重试。")

    def _finish(self, success, message):
        owner = self._owner
        self.close()
        self.message = message
        if success:
            self.installed.emit(owner)
        self.changed.emit()

    def _fail(self, message):
        self.close()
        self.message = message
        self.changed.emit()

    def _clean_stage(self):
        stage, self._stage = self._stage, None
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)

    def close(self):
        self.timer.stop()
        if self.process is not None:
            self.process.close()
            self.process = None
        if self._download is not None:
            self._download.cancel()
            self._download = None
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None
        self._waiting_since = None
        self._owner = None
        self._clean_stage()


def for_application(directory, resources, route_ready=None):
    app = QApplication.instance()
    if not hasattr(app, "jinkra_driver_installation"):
        installation = DriverInstallation(directory, resources, app, route_ready)
        app.jinkra_driver_installation = installation
        app.aboutToQuit.connect(installation.close)
    return app.jinkra_driver_installation
