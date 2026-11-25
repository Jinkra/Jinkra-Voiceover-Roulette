"""按 Windows 用户和软件版本保存的离线激活。"""

import ctypes
import hashlib
import hmac
from ctypes import wintypes

_SALT = b"jinkra-roulette-activation-v1"
_EXPECTED = bytes.fromhex(
    "ff48fec480b42a07b7d32da18d6317daefd96d21e581134a8b084993576b98dbc"
    "078b1d10c136ed3ccaa9c1dceb61d2dc9a80745c9d40b2e59addaef21565284"
)


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("pointer", ctypes.c_void_p)]


def _protect(raw: bytes, *, decrypt: bool = False) -> bytes:
    data = ctypes.create_string_buffer(raw)
    source = _Blob(len(raw), ctypes.addressof(data))
    result = _Blob()
    crypto = ctypes.windll.crypt32
    function = crypto.CryptUnprotectData if decrypt else crypto.CryptProtectData
    function.argtypes = (
        ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob),
    )
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise OSError("Windows 无法读写激活凭据")
    free = ctypes.windll.kernel32.LocalFree
    free.argtypes = (ctypes.c_void_p,)
    free.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(result.pointer, result.size)
    finally:
        free(result.pointer)


class Activation:
    def __init__(self, directory, version):
        self.path = directory / ".jinkra-activation"
        self.receipt = f"Jinkra/Voiceover-Roulette/{version}".encode()

    def active(self):
        try:
            if self.path.stat().st_size > 8192:
                return False
            return hmac.compare_digest(_protect(self.path.read_bytes(), decrypt=True), self.receipt)
        except OSError:
            return False

    def activate(self, code):
        secret = code.strip().encode("utf-8")
        if len(secret) > 128:
            return False
        derived = hashlib.scrypt(secret, salt=_SALT, n=16384, r=8, p=1)
        if not hmac.compare_digest(derived, _EXPECTED):
            return False
        temporary = self.path.with_suffix(".activation-tmp")
        try:
            temporary.write_bytes(_protect(self.receipt))
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
        return True

