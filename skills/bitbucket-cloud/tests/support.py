import contextlib
import importlib.util
import os
import sys
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


@contextlib.contextmanager
def env(**kw):
    """Patch os.environ with the BITBUCKET_* vars cleared, then set kw."""
    clean = {k: v for k, v in os.environ.items() if k not in BB_VARS}
    clean.update(kw)
    with mock.patch.dict(os.environ, clean, clear=True):
        yield
