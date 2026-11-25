"""生成程序图标 icon.ico（多尺寸），供 exe 使用。

图形与托盘图标共用绘制代码。
ICO 直接内嵌 PNG 数据（Vista 以后都支持），避免依赖 BMP 转换。
"""

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

SIZES = [16, 24, 32, 48, 64, 128, 256]


def render(artwork: QPixmap, size: int) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    artwork.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(buf, "PNG")
    buf.close()
    return bytes(ba.data())


def build_ico(path: Path) -> None:
    artwork = QPixmap(str(ROOT / "assets" / "jinkra.png"))
    if artwork.isNull() or artwork.width() != artwork.height():
        raise ValueError("需要方形的 assets/jinkra.png")
    blobs = [(size, render(artwork, size)) for size in SIZES]
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries = b""
    for size, data in blobs:
        dim = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset
        )
        offset += len(data)
    path.write_bytes(header + entries + b"".join(d for _, d in blobs))


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841
    out = ROOT / "icon.ico"
    build_ico(out)
    print(f"已生成 {out}  ({out.stat().st_size} bytes, {len(SIZES)} 个尺寸)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
