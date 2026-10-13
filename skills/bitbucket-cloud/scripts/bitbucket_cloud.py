#!/usr/bin/env python3
"""bitbucket-cloud: dependency-free CLI for the Bitbucket Cloud REST API 2.0.

Credentials come from env vars (BITBUCKET_EMAIL, BITBUCKET_API_TOKEN,
BITBUCKET_WORKSPACE) or the config file written by `configure`.
Runs on Python 3.8+ on Windows and POSIX using only the standard library.
"""

import base64
import json
import os
import sys
from pathlib import Path

ENV_NAMES = {
    "email": "BITBUCKET_EMAIL",
    "token": "BITBUCKET_API_TOKEN",
    "workspace": "BITBUCKET_WORKSPACE",
}


class ConfigError(Exception):
    pass


def config_path():
    override = os.environ.get("BITBUCKET_CLOUD_CONFIG", "").strip()
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "bitbucket-cloud" / "credentials.json"
    return Path.home() / ".config" / "bitbucket-cloud" / "credentials.json"


def load_config():
    path = config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise ConfigError(f"cannot read config file {path}: {e}")
    return data if isinstance(data, dict) else {}


def setting(key):
    val = os.environ.get(ENV_NAMES[key], "").strip()
    if val:
        return val
    return str(load_config().get(key, "") or "").strip()


def auth_header():
    token = setting("token")
    if not token:
        raise ConfigError(
            "no API token configured; run `configure --token ...` or set BITBUCKET_API_TOKEN"
        )
    email = setting("email")
    if email:
        raw = f"{email}:{token}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")
    return "Bearer " + token


def configure(args):
    path = config_path()
    data = load_config()
    for key in ("email", "token", "workspace"):
        val = getattr(args, key, None)
        if val:
            data[key] = val
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(path, 0o600)
    print(f"saved {', '.join(sorted(data))} to {path}")
    return 0
