"""首启激活、官方更新信息和镜像完整性回归。"""

import hashlib
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import activation
import updates


class UpdateTests(unittest.TestCase):
    def setUp(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(updates.NAME, b"MZ-test-executable")
            archive.writestr("../untouched.config", b"excluded")
        self.payload = buffer.getvalue()
        self.asset = updates.filename("v1.4.0")
        self.document = {"tag_name": "v1.4.0", "assets": [{
            "name": self.asset,
            "size": len(self.payload),
            "digest": "sha256:" + hashlib.sha256(self.payload).hexdigest(),
        }]}

    def test_release_version_and_digest(self):
        self.assertIsNone(updates.parse_release(self.document, "v1.4.0"))
        self.assertIsNone(updates.parse_release(self.document, "v2.0.0"))
        self.assertEqual(updates.parse_release(self.document, "v1.3.0").asset, self.asset)
        with self.assertRaises(ValueError):
            updates.parse_release({"tag_name": "v1.4.1", "assets": []}, "v1.3.0")
        with self.assertRaises(ValueError):
            updates._validate_url("https://evil.example/package.zip", updates._DOWNLOADS)

    def test_failed_digest_falls_back_and_extracts_one_file(self):
        release = updates.parse_release(self.document, "v1.3.0")
        bad = self.payload[:-1] + bytes([self.payload[-1] ^ 1])
        routes = [("fast", "https://ghfast.top/", 0.1), ("GitHub", "", 0.2)]
        seen = []
        with tempfile.TemporaryDirectory() as data, \
             patch.object(updates, "probe_routes", return_value=routes), \
             patch.object(updates, "_open", side_effect=(io.BytesIO(bad), io.BytesIO(self.payload))):
            staged = updates.download(release, Path(data), lambda text, _: seen.append(text))
            self.assertEqual(staged.read_bytes(), b"MZ-test-executable")
            self.assertEqual(list(staged.parent.iterdir()), [staged])
            self.assertTrue(any(text and "校验失败" in text for text in seen))


class ActivationTests(unittest.TestCase):
    def test_receipt_belongs_to_version(self):
        code = "test-only-code"
        digest = hashlib.scrypt(code.encode(), salt=activation._SALT, n=16384, r=8, p=1)
        with tempfile.TemporaryDirectory() as data, patch.object(activation, "_EXPECTED", digest):
            folder = Path(data)
            current = activation.Activation(folder, "v1.3.0")
            self.assertFalse(current.active())
            self.assertFalse(current.activate("wrong"))
            self.assertTrue(current.activate(code))
            self.assertTrue(current.active())
            self.assertFalse(activation.Activation(folder, "v1.4.0").active())
            self.assertNotIn(code.encode(), current.path.read_bytes())


if __name__ == "__main__":
    unittest.main()

