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


class RateLimitTests(unittest.TestCase):
    """GitHub 接口限流（HTTP 403）时改读发布清单 latest.json。"""

    def setUp(self):
        self.payload = b"PK-update"
        self.data = updates.manifest("v1.4.0", updates.filename("v1.4.0"), len(self.payload),
                                     hashlib.sha256(self.payload).hexdigest(), "说明")

    def limited(self, *args, **kwargs):
        raise updates.urllib.error.HTTPError(updates.LATEST, 403, "rate limit exceeded", {}, None)

    def test_rate_limited_api_falls_back_to_manifest(self):
        opened = []

        def fake_open(url, **kwargs):
            opened.append(url)
            if url == updates.LATEST:
                self.limited()
            return io.BytesIO(updates.json.dumps(self.data).encode())

        with patch.object(updates, "_open", side_effect=fake_open):
            release = updates.check("v1.3.0")
        self.assertEqual(release.version, "v1.4.0")
        self.assertEqual(release.sha256, self.data["sha256"])
        self.assertTrue(opened[1].endswith("/releases/latest/download/latest.json"))

    def test_manifest_tries_every_route(self):
        calls = []

        def fake_open(url, **kwargs):
            calls.append(url)
            if url == updates.LATEST:
                self.limited()
            if not url.startswith(updates.ROUTES[-1][1]):
                raise OSError("线路不通")
            return io.BytesIO(updates.json.dumps(self.data).encode())

        with patch.object(updates, "_open", side_effect=fake_open):
            self.assertEqual(updates.check("v1.3.0").version, "v1.4.0")
        self.assertEqual(len(calls), 1 + len(updates.ROUTES))

    def test_everything_down_gives_clear_message(self):
        def fake_open(url, **kwargs):
            if url == updates.LATEST:
                self.limited()
            raise OSError("线路不通")

        with patch.object(updates, "_open", side_effect=fake_open):
            with self.assertRaises(OSError) as raised:
                updates.check("v1.3.0")
        self.assertIn("限制了查询次数", str(raised.exception))
        self.assertIn("打开发布页", str(raised.exception))

    def test_tampered_manifest_is_rejected(self):
        bad = dict(self.data, sha256="not-a-digest")

        def fake_open(url, **kwargs):
            if url == updates.LATEST:
                self.limited()
            return io.BytesIO(updates.json.dumps(bad).encode())

        with patch.object(updates, "_open", side_effect=fake_open):
            with self.assertRaises(OSError):
                updates.check("v1.3.0")


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

