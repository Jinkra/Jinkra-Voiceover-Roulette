"""安装 Jinkra 虚拟麦克风，并跟踪 Windows 安装程序的结果。"""

import ctypes
import re
import subprocess
from ctypes import wintypes as win
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication, QFileDialog


def _helper(directory, resources):
    helper = resources / "jinkra-driver-helper.exe"
    if not helper.is_file() and resources == directory / "assets":
        helper = directory / "build" / "jinkra-driver-helper.exe"
    return helper if helper.is_file() else None


def _has_package(package):
    return all((package / f"JinkraVad.{extension}").is_file() for extension in ("inf", "cat", "sys"))


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
        raise OSError("请选择包含 JinkraVad.inf、JinkraVad.cat 和 JinkraVad.sys 的驱动目录。")
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

    def __init__(self, directory, resources, parent):
        super().__init__(parent)
        self.directory = directory
        self.resources = resources
        self.message = ""
        self.process = None
        self.timer = QTimer(self, interval=350)
        self.timer.timeout.connect(self._poll)

    def hint(self):
        if self.message:
            return self.message
        if _has_package(self.directory / "VirtualMic"):
            return "已找到随附驱动包。安装时 Windows 会验证签名。"
        return "此版本未随附驱动包。若已有 Jinkra 正式签名驱动，可点「安装虚拟麦克风」选择目录。"

    def install(self, parent):
        if self.process is not None:
            return
        try:
            helper = _helper(self.directory, self.resources)
            if helper is None:
                raise OSError("缺少 Jinkra 驱动安装工具，请重新下载完整的 Jinkra 安装包。")
            package = self.directory / "VirtualMic"
            if not _has_package(package):
                directory = QFileDialog.getExistingDirectory(
                    parent, "选择 Jinkra 正式签名驱动目录", str(self.directory))
                if not directory:
                    return
                package = Path(directory)
            self.process = _start_install(helper, package, int(parent.winId()))
        except OSError as error:
            self.message = str(error)
        else:
            self.message = "正在安装 Jinkra Virtual Mic。"
            self.timer.start()
        self.changed.emit()

    def _poll(self):
        try:
            result = self.process.result()
        except OSError as error:
            self.message = f"读取驱动安装结果失败。{error}"
        else:
            if result is None:
                return
            self.message = (
                "安装程序已完成。设备出现后可启用送声，必要时重启 Windows 后重新检测。"
                if result == 0 else "Windows 未完成安装。请确认驱动包来自 Jinkra 且带有效签名。"
            )
        self.close()
        self.changed.emit()

    def close(self):
        self.timer.stop()
        if self.process is not None:
            self.process.close()
            self.process = None


def for_application(directory, resources):
    app = QApplication.instance()
    if not hasattr(app, "jinkra_driver_installation"):
        installation = DriverInstallation(directory, resources, app)
        app.jinkra_driver_installation = installation
        app.aboutToQuit.connect(installation.close)
    return app.jinkra_driver_installation
