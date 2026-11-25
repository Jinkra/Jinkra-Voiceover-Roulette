"""安装 Jinkra 虚拟麦克风，并跟踪 Windows 安装程序的结果。"""

import ctypes
import re
import shutil
import subprocess
import tempfile
from ctypes import wintypes as win
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication


DRIVER_FILES = ("JinkraVad.inf", "JinkraVad.cat", "JinkraVad.sys")


def _helper(directory, resources):
    helper = resources / "jinkra-driver-helper.exe"
    if not helper.is_file() and resources == directory / "assets":
        helper = directory / "build" / "jinkra-driver-helper.exe"
    return helper if helper.is_file() else None


def _has_package(package):
    return all((package / name).is_file() for name in DRIVER_FILES)


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


def _start_install(helper, package, owner):
    package = package.resolve()
    if not _has_package(package):
        raise OSError("驱动包不完整，请重新获取 Jinkra 正式安装包。")
    with (package / "JinkraVad.inf").open("rb") as source:
        raw = source.read(65536)
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    if not re.search(r"^\s*%[^%\r\n]+%\s*=[^,\r\n]+,\s*ROOT\\JINKRAVAD\s*$",
                     raw.decode(encoding, errors="replace"), re.IGNORECASE | re.MULTILINE):
        raise OSError("这个驱动包与 Jinkra Virtual Mic 不匹配。")

    shell = ctypes.WinDLL("shell32", use_last_error=True).ShellExecuteExW
    shell.argtypes = (ctypes.POINTER(_ShellExecuteInfo),)
    shell.restype = win.BOOL
    info = _ShellExecuteInfo(size=ctypes.sizeof(_ShellExecuteInfo), mask=0x440, owner=owner,
                             verb="runas", file=str(helper.resolve()),
                             parameters=subprocess.list2cmdline(["install", str(package)]),
                             directory=str(helper.resolve().parent), show=0)
    if not shell(ctypes.byref(info)):
        error = ctypes.get_last_error()
        if error == 1223:
            raise OSError("已取消 Windows 管理员确认。")
        raise ctypes.WinError(error)
    if not info.process:
        raise OSError("Windows 没有返回安装程序的运行状态。请重新检测设备。")
    return _InstallProcess(info.process)


class DriverInstallation(QObject):
    changed = Signal()
    installed = Signal(object)

    def __init__(self, directory, resources, parent):
        super().__init__(parent)
        self.directory = directory
        self.resources = resources
        self.message = ""
        self.process = None
        self._owner = None
        self._stage = None
        self.timer = QTimer(self, interval=350)
        self.timer.timeout.connect(self._poll)

    def _package(self):
        return next((path for path in (self.resources / "VirtualMic", self.directory / "VirtualMic")
                     if _has_package(path)), None)

    def can_install(self):
        return (self.process is None and self._package() is not None
                and _helper(self.directory, self.resources) is not None)

    def installing_from(self, parent):
        return self.process is not None and self._owner is parent

    def hint(self):
        if self.message:
            return self.message
        if self.can_install():
            return "点击安装并确认 Windows 提示，完成后自动启用送声。"
        return "当前构建未随附可安装的正式驱动，可先使用本地播放。"

    def install(self, parent):
        if self.process is not None:
            return
        try:
            helper = _helper(self.directory, self.resources)
            if helper is None:
                raise OSError("缺少 Jinkra 驱动安装工具，请重新下载完整的 Jinkra 安装包。")
            package = self._package()
            if package is None:
                raise OSError("当前构建未随附正式驱动。")
            # 安装包由提升权限后的独立进程读取，须独立于便携 EXE 的解包生命周期。
            self._stage = Path(tempfile.mkdtemp(prefix="jinkra-driver-"))
            for name in DRIVER_FILES:
                shutil.copyfile(package / name, self._stage / name)
            self.process = _start_install(helper, self._stage, int(parent.winId()))
        except OSError as error:
            self._clean_stage()
            self.message = str(error)
        else:
            self._owner = parent
            self.message = "正在安装 Jinkra Virtual Mic。"
            self.timer.start()
        self.changed.emit()

    def _poll(self):
        success = False
        try:
            result = self.process.result()
        except OSError as error:
            self.message = f"读取驱动安装结果失败。{error}"
        else:
            if result is None:
                return
            success = result == 0
            self.message = (
                "驱动安装已完成。Windows 识别音频端点后会自动送声，必要时请重启 Windows。"
                if success else "Windows 未完成驱动安装，请重试并确认管理员提示。"
            )
            self._clean_stage()
        owner = self._owner
        self.close()
        if success:
            self.installed.emit(owner)
        self.changed.emit()

    def _clean_stage(self):
        stage, self._stage = self._stage, None
        if stage is not None:
            try:
                for name in DRIVER_FILES:
                    (stage / name).unlink(missing_ok=True)
                stage.rmdir()
            except OSError:
                pass

    def close(self):
        self.timer.stop()
        if self.process is not None:
            self.process.close()
            self.process = None
        self._owner = None


def for_application(directory, resources):
    app = QApplication.instance()
    if not hasattr(app, "jinkra_driver_installation"):
        installation = DriverInstallation(directory, resources, app)
        app.jinkra_driver_installation = installation
        app.aboutToQuit.connect(installation.close)
    return app.jinkra_driver_installation
