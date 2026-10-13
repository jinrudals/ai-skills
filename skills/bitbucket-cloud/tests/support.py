import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "bitbucket_cloud.py"

_spec = importlib.util.spec_from_file_location("bitbucket_cloud", SCRIPT)
bb = importlib.util.module_from_spec(_spec)
sys.modules["bitbucket_cloud"] = bb
_spec.loader.exec_module(bb)

BB_VARS = (
    "BITBUCKET_EMAIL",
    "BITBUCKET_API_TOKEN",
    "BITBUCKET_WORKSPACE",
    "BITBUCKET_CLOUD_CONFIG",
)


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body.encode("utf-8") if isinstance(body, str) else body
        self.headers = {}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_urlopen(responses):
    """Return a urlopen stand-in that serves `responses` in order.

    Each entry is (status, body). Calls are recorded in `.calls` as
    (method, url, headers, data); status >= 400 raises HTTPError.
    """
    queue = list(responses)

    def opener(req, *args, **kwargs):
        opener.calls.append(
            (req.get_method(), req.full_url, dict(req.header_items()), req.data)
        )
        status, body = queue.pop(0)
        resp = FakeResponse(status, body)
        if status >= 400:
            raise urllib.error.HTTPError(
                req.full_url, status, "error", {}, io.BytesIO(resp.body)
            )
        return resp

    opener.calls = []
    return opener


class CliCase(unittest.TestCase):
    """Base class: run_main(argv, responses) drives bb.main with a fake HTTP layer."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cfg = str(Path(self._tmp.name) / "credentials.json")

    def run_main(self, argv, responses=(), **envvars):
        opener = fake_urlopen(list(responses))
        out, err = io.StringIO(), io.StringIO()
        base = dict(
            BITBUCKET_EMAIL="a@b.c",
            BITBUCKET_API_TOKEN="SECRET123",
            BITBUCKET_WORKSPACE="ws",
            BITBUCKET_CLOUD_CONFIG=self.cfg,
        )
        base.update(envvars)
        code = None
        with env(**base), mock.patch.object(bb, "_open", opener), contextlib.redirect_stdout(
            out
        ), contextlib.redirect_stderr(err):
            try:
                code = bb.main(argv)
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue(), opener

    def sent_json(self, opener, index=0):
        return json.loads(opener.calls[index][3].decode("utf-8"))


@contextlib.contextmanager
def env(**kw):
    """Patch os.environ with the BITBUCKET_* vars cleared, then set kw."""
    clean = {k: v for k, v in os.environ.items() if k not in BB_VARS}
    clean.update(kw)
    with mock.patch.dict(os.environ, clean, clear=True):
        yield
