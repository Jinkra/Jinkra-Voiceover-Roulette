"""构建 Windows 安装包、卸载程序和在线更新用的 ZIP。

用法（在 Windows 上）：
    python build_installer.py            # 先用 PyInstaller 打包 EXE，再生成安装包
    python build_installer.py --skip-exe # 直接使用 dist/Jinkra 里已有的 EXE

输出在 release/：
    Jinkra-Voiceover-Roulette-Setup-vX.Y.Z-x64.exe     安装向导（内含卸载向导）
    Jinkra-Voiceover-Roulette-vX.Y.Z-Windows-x64.zip   应用内「检查更新」下载的包
    以及两者的 .sha256
"""

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRODUCT = "Jinkra Voiceover Roulette"
EXE_NAME = PRODUCT + ".exe"
UNINSTALLER = "Uninstall " + EXE_NAME
DIST = ROOT / "dist" / "Jinkra"
RELEASE = ROOT / "release"
CSC = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"


def app_version():
    text = (ROOT / "sr_roulette.py").read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION = "v(\d+\.\d+\.\d+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("sr_roulette.py 里找不到 APP_VERSION。")
    return match.group(1)


def compile_setup(output, version, staging, resources=()):
    metadata = staging / "SetupVersion.cs"
    metadata.write_text(
        "using System.Reflection;\n"
        f'[assembly: AssemblyVersion("{version}")]\n'
        f'[assembly: AssemblyFileVersion("{version}")]\n'
        f'[assembly: AssemblyInformationalVersion("{version}")]\n',
        encoding="utf-8",
    )
    command = [
        str(CSC), "/nologo", "/codepage:65001", "/target:winexe", "/optimize+", "/platform:x64",
        "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll",
        "/r:System.IO.Compression.dll", "/r:System.IO.Compression.FileSystem.dll",
        f"/win32icon:{ROOT / 'icon.ico'}", f"/out:{output}",
        f"/resource:{ROOT / 'assets' / 'jinkra.png'},logo.png",
        *(f"/resource:{path},{name}" for path, name in resources),
        str(ROOT / "native" / "Setup.cs"), str(metadata),
    ]
    subprocess.run(command, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    value = digest.hexdigest()
    Path(str(path) + ".sha256").write_text(f"{value}  {path.name}\n", encoding="ascii")
    return value


def app_files(exe):
    files = [(exe, EXE_NAME), (ROOT / "LICENSE", "LICENSE"), (ROOT / "使用说明.txt", "使用说明.txt")]
    files += [(path, f"sounds/{path.name}") for path in sorted((ROOT / "sounds").glob("Jinkra-*.wav"))]
    missing = [str(path) for path, _ in files if not path.is_file()]
    if missing:
        raise SystemExit("缺少打包文件：" + "、".join(missing))
    return files


def write_zip(target, files):
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in files:
            archive.write(path, name)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-exe", action="store_true", help="不重新运行 PyInstaller")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("安装包只能在 Windows 上构建。")
    version = app_version()
    if not args.skip_exe:
        subprocess.run([sys.executable, "-m", "PyInstaller", "JinkraRoulette.spec", "--noconfirm", "--clean",
                        "--distpath", str(DIST)], cwd=ROOT, check=True)
    exe = DIST / EXE_NAME
    if not exe.is_file():
        raise SystemExit(f"找不到 {exe}，请先打包 EXE。")

    RELEASE.mkdir(exist_ok=True)
    setup = RELEASE / f"Jinkra-Voiceover-Roulette-Setup-v{version}-x64.exe"
    update_zip = RELEASE / f"Jinkra-Voiceover-Roulette-v{version}-Windows-x64.zip"
    with tempfile.TemporaryDirectory(prefix="jinkra-setup-build-") as temporary:
        staging = Path(temporary)
        uninstaller = staging / UNINSTALLER
        # 卸载程序原样附带 VB-CABLE 驱动包，用于「同时卸载虚拟麦克风」
        sys.path.insert(0, str(ROOT))
        import driver_setup
        cable = ROOT / "build" / driver_setup.VB_CABLE_PACK
        if not driver_setup._valid_pack(cable):
            raise SystemExit(f"缺少或校验失败：{cable}，请先完整打包一次 EXE。")
        compile_setup(uninstaller, version, staging, [(cable, "vbcable.zip")])
        payload = staging / "payload.zip"
        write_zip(payload, app_files(exe) + [(uninstaller, UNINSTALLER)])
        compile_setup(setup, version, staging, [(payload, "payload.zip")])
    write_zip(update_zip, app_files(exe))
    for artifact in (setup, update_zip):
        print(f"{artifact.name}  {artifact.stat().st_size / 1048576:.1f} MB  sha256={sha256(artifact)}")


if __name__ == "__main__":
    main()
