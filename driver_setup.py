"""启动本产品随附并由 Windows 验证的虚拟麦克风驱动。"""

import ctypes
import subprocess
from pathlib import Path


def installer(directory, resources):
    package = directory / "VirtualMic"
    helper = resources / "jinkra-driver-helper.exe"
    if not helper.is_file() and resources == directory / "assets":
        helper = directory / "build" / "jinkra-driver-helper.exe"
    files = [package / f"JinkraVad.{extension}" for extension in ("inf", "cat", "sys")]
    if not helper.is_file() or not all(path.is_file() for path in files):
        return None
    return helper, package


def start_install(directory, resources):
    available = installer(directory, resources)
    if available is None:
        raise OSError("未检测到可安装的 Jinkra 驱动包")
    helper, package = available
    shell = ctypes.windll.shell32.ShellExecuteW
    shell.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                      ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int)
    shell.restype = ctypes.c_void_p
    args = subprocess.list2cmdline(["install", str(package)])
    result = shell(None, "runas", str(helper), args, str(Path(package).resolve()), 1)
    if result is None or result <= 32:
        raise OSError("驱动安装未启动，可重新尝试")

