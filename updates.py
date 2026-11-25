"""GitHub 官方发布与经过校验的多线路更新。"""

import hashlib
import http.client
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

REPOSITORY = "Jinkra/Jinkra-Voiceover-Roulette"
RELEASES = f"https://github.com/{REPOSITORY}/releases"
LATEST = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
NAME = "Jinkra Voiceover Roulette.exe"
ROUTES = (
    ("GitHub 直连", ""),
    ("GHFast", "https://ghfast.top/"),
    ("GH-Proxy", "https://gh-proxy.org/"),
    ("GH-Proxy CDN", "https://cdn.gh-proxy.org/"),
)
_OFFICIAL = {"github.com", "api.github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
_DOWNLOADS = _OFFICIAL | {urllib.parse.urlsplit(prefix).hostname for _, prefix in ROUTES if prefix}
_BLOCK = 128 * 1024
_MAX = 300 * 1024 * 1024


def version_tuple(version):
    if not isinstance(version, str) or not re.fullmatch(r"v?[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}", version):
        raise ValueError("发布版本格式不正确")
    return tuple(int(part) for part in version.lstrip("v").split("."))


def filename(version):
    return f"Jinkra-Voiceover-Roulette-v{version.lstrip('v')}-Windows-x64.zip"


def _validate_url(url, hosts):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in hosts or parsed.port
            or parsed.username is not None or parsed.password is not None):
        raise ValueError("更新地址不受支持")


class _Redirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 4

    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl, self.hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url, *, hosts, timeout, headers=None):
    _validate_url(url, hosts)
    request = urllib.request.Request(url, headers={
        "User-Agent": "Jinkra-Voiceover-Roulette", **(headers or {})
    })
    return urllib.request.build_opener(_Redirect(hosts)).open(request, timeout=timeout)


@dataclass(frozen=True)
class Release:
    version: str
    asset: str
    size: int
    sha256: str
    notes: str

    @property
    def url(self):
        return f"{RELEASES}/download/{self.version}/{self.asset}"


def parse_release(document, current):
    tag = document.get("tag_name")
    if document.get("prerelease") or document.get("draft") or version_tuple(tag) <= version_tuple(current):
        return None
    if not tag.startswith("v"):
        raise ValueError("发布标签须以 v 开头")
    name = filename(tag)
    asset = next((a for a in document.get("assets", []) if a.get("name") == name), None)
    digest = asset.get("digest", "") if asset else ""
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise ValueError("官方发布缺少 Windows 更新包或 SHA-256 校验值")
    size = asset.get("size")
    if type(size) is not int or not 0 < size <= _MAX:
        raise ValueError("官方发布中的安装包大小无效")
    return Release(tag, name, size, digest[7:].lower(), str(document.get("body") or "")[:4000])


def check(current):
    try:
        with _open(LATEST, hosts=_OFFICIAL, timeout=8, headers={"Accept": "application/vnd.github+json"}) as response:
            raw = response.read(262145)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    if len(raw) > 262144:
        raise ValueError("官方发布信息过大")
    return parse_release(json.loads(raw), current)


def probe_routes(release, report=lambda *_: None):
    """测量真实发布包首段读取时间。"""
    def probe(line):
        name, prefix = line
        started = time.monotonic()
        try:
            with _open(prefix + release.url, hosts=_DOWNLOADS, timeout=4,
                       headers={"Range": f"bytes=0-{_BLOCK - 1}"}) as response:
                if response.status == 206:
                    total = response.headers.get("Content-Range", "")
                    if not total.startswith("bytes 0-") or not total.endswith(f"/{release.size}"):
                        return name, prefix, None
                elif response.status != 200:
                    return name, prefix, None
                first = response.read(min(_BLOCK, release.size))
                if not first.startswith(b"PK\x03\x04"):
                    return name, prefix, None
            return name, prefix, time.monotonic() - started
        except (OSError, ValueError, http.client.HTTPException):
            return name, prefix, None

    with ThreadPoolExecutor(max_workers=len(ROUTES)) as executor:
        results = list(executor.map(probe, ROUTES))
    for name, _, elapsed in results:
        report(name, elapsed)
    return sorted((r for r in results if r[2] is not None), key=lambda r: r[2])


def _extract_exe(package, destination):
    with zipfile.ZipFile(package) as archive:
        matches = [member for member in archive.infolist() if member.filename == NAME]
        if len(matches) != 1 or not 0 < matches[0].file_size <= _MAX:
            raise ValueError("更新包缺少正确的程序文件")
        with archive.open(matches[0]) as source, destination.open("xb") as output:
            if source.read(2) != b"MZ":
                raise ValueError("更新包中的程序格式无效")
            output.write(b"MZ")
            shutil.copyfileobj(source, output, _BLOCK)


def download(release, directory, notify):
    routes = probe_routes(release, lambda name, elapsed: notify(
        f"{name}：{int(elapsed * 1000)} ms" if elapsed is not None else f"{name}：不可用", None))
    if not routes:
        raise OSError("所有下载线路均无法读取发布资源")
    with tempfile.TemporaryDirectory(prefix="jinkra-download-") as temp:
        package = Path(temp) / "release.zip"
        for name, prefix, _ in routes:
            notify(f"通过 {name} 下载", 0)
            try:
                received = 0
                digest = hashlib.sha256()
                last_percent = -1
                with _open(prefix + release.url, hosts=_DOWNLOADS, timeout=12) as source, package.open("wb") as output:
                    while block := source.read(_BLOCK):
                        received += len(block)
                        if received > release.size:
                            raise ValueError("文件长度与官方发布不一致")
                        digest.update(block)
                        output.write(block)
                        percent = int(received * 100 / release.size)
                        if percent != last_percent:
                            notify(None, percent)
                            last_percent = percent
                if received != release.size or digest.hexdigest() != release.sha256:
                    raise ValueError("文件的 SHA-256 与官方发布不一致")
                stage = Path(tempfile.mkdtemp(prefix=".jinkra-update-", dir=directory))
                try:
                    next_exe = stage / NAME
                    _extract_exe(package, next_exe)
                    return next_exe
                except Exception:
                    shutil.rmtree(stage)
                    raise
            except (OSError, ValueError, http.client.HTTPException, zipfile.BadZipFile):
                notify(f"{name} 下载或校验失败，尝试下一条线路", None)
    raise OSError("可用线路均未能下载并校验更新包")


def apply_update(staged):
    if not getattr(sys, "frozen", False):
        raise OSError("源码模式请从发布页下载安装包")
    exe = Path(sys.executable).resolve()
    helper = staged.parent / "apply-update.exe"
    shutil.copy2(Path(sys._MEIPASS) / "jinkra-updater.exe", helper)
    subprocess.Popen([str(helper), str(staged), str(exe)])

