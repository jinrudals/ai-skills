import base64
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from support import bb, env


def b64(s):
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = Path(self.tmp.name) / "credentials.json"

    def write_cfg(self, **data):
        self.cfg.write_text(json.dumps(data), encoding="utf-8")

    def test_env_beats_file(self):
        self.write_cfg(token="A")
        with env(BITBUCKET_CLOUD_CONFIG=str(self.cfg), BITBUCKET_API_TOKEN="B"):
            self.assertEqual(bb.setting("token"), "B")

    def test_file_used_when_no_env(self):
        self.write_cfg(token="A", workspace="ws")
        with env(BITBUCKET_CLOUD_CONFIG=str(self.cfg)):
            self.assertEqual(bb.setting("token"), "A")
            self.assertEqual(bb.setting("workspace"), "ws")
            self.assertEqual(bb.setting("email"), "")

    def test_auth_basic_when_email(self):
        with env(BITBUCKET_EMAIL="a@b.c", BITBUCKET_API_TOKEN="t"):
            self.assertEqual(bb.auth_header(), "Basic " + b64("a@b.c:t"))

    def test_auth_bearer_when_no_email(self):
        with env(BITBUCKET_API_TOKEN="t"):
            self.assertEqual(bb.auth_header(), "Bearer t")
        with env(BITBUCKET_API_TOKEN="t", BITBUCKET_EMAIL=""):
            self.assertEqual(bb.auth_header(), "Bearer t")

    def test_missing_token_raises_configerror(self):
        with env(BITBUCKET_CLOUD_CONFIG=str(self.cfg)):
            with self.assertRaises(bb.ConfigError):
                bb.auth_header()

    def test_config_path_posix(self):
        with env(), mock.patch.object(bb.sys, "platform", "linux"):
            p = bb.config_path()
        self.assertEqual(p.parts[-3:], (".config", "bitbucket-cloud", "credentials.json"))

    def test_config_path_windows(self):
        appdata = r"C:\Users\x\AppData\Roaming"
        with env(APPDATA=appdata), mock.patch.object(bb.sys, "platform", "win32"):
            p = bb.config_path()
        self.assertEqual(p.name, "credentials.json")
        self.assertEqual(p.parent.name, "bitbucket-cloud")
        self.assertEqual(p.parent.parent, Path(appdata))

    def test_config_path_override(self):
        with env(BITBUCKET_CLOUD_CONFIG=str(self.cfg)):
            self.assertEqual(bb.config_path(), self.cfg)

    def run_configure(self, **kw):
        args = SimpleNamespace(email=None, token=None, workspace=None)
        for k, v in kw.items():
            setattr(args, k, v)
        out = io.StringIO()
        with env(BITBUCKET_CLOUD_CONFIG=str(self.cfg)), contextlib.redirect_stdout(out):
            rc = bb.configure(args)
        return rc, out.getvalue()

    def test_configure_merges(self):
        rc1, _ = self.run_configure(email="a@b.c")
        rc2, out = self.run_configure(token="SECRET123")
        self.assertEqual((rc1, rc2), (0, 0))
        data = json.loads(self.cfg.read_text(encoding="utf-8"))
        self.assertEqual(data, {"email": "a@b.c", "token": "SECRET123"})
        self.assertNotIn("SECRET123", out)

    def test_configure_skips_chmod_on_windows(self):
        with mock.patch.object(bb.sys, "platform", "win32"), mock.patch.object(
            bb.os, "chmod"
        ) as chmod:
            self.run_configure(token="t")
        chmod.assert_not_called()

    def test_configure_chmods_0600_on_posix(self):
        with mock.patch.object(bb.sys, "platform", "linux"), mock.patch.object(
            bb.os, "chmod"
        ) as chmod:
            self.run_configure(token="t")
        chmod.assert_called_once_with(self.cfg, 0o600)

    def test_auth_header_non_ascii_email(self):
        with env(BITBUCKET_EMAIL="한글@b.c", BITBUCKET_API_TOKEN="t+/="):
            self.assertEqual(bb.auth_header(), "Basic " + b64("한글@b.c:t+/="))


if __name__ == "__main__":
    unittest.main()
