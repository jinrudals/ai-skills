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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.bitbucket.org/2.0"
API_HOST = "api.bitbucket.org"

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


# ------------------------------------------------------------------ http ----


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects but never forward credentials to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).hostname != API_HOST:
            for name in list(new.headers):
                if name.lower() == "authorization":
                    del new.headers[name]
            for name in list(new.unredirected_hdrs):
                if name.lower() == "authorization":
                    del new.unredirected_hdrs[name]
        return new


def _default_open(req):
    return urllib.request.build_opener(SafeRedirectHandler).open(req)


_open = _default_open


def redact(text):
    token = setting("token")
    return text.replace(token, "***") if token else text


def quote(segment):
    return urllib.parse.quote(str(segment), safe="")


def quote_path(path):
    return urllib.parse.quote(str(path), safe="/")


def _check_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname != API_HOST:
        raise ApiError(0, f"refusing to send credentials to {parts.scheme}://{parts.hostname}")


def _error_message(raw):
    text = raw.decode("utf-8", errors="replace") if raw else ""
    try:
        data = json.loads(text)
    except ValueError:
        return text.strip()[:200]
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if data.get("message"):
            return str(data["message"])
    return text.strip()[:200]


def request(method, path_or_url, *, params=None, body=None, raw=False):
    url = path_or_url if path_or_url.startswith("http") else BASE + path_or_url
    _check_url(url)
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    headers = {"Authorization": auth_header(), "Accept": "application/json"}
    data = None
    if isinstance(body, dict):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif isinstance(body, str):
        data = body.encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with _open(req) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, redact(_error_message(e.read())))
    except urllib.error.URLError as e:
        raise ApiError(0, redact(str(e.reason)))
    if not payload:
        return None
    text = payload.decode("utf-8", errors="replace")
    if raw:
        return text
    try:
        return json.loads(text)
    except ValueError:
        return text


def paginate(path, params=None, limit=100):
    params = dict(params or {})
    params.setdefault("pagelen", max(1, min(limit, 100)))
    items = []
    page = request("GET", path, params=params)
    while True:
        values = page.get("values", []) if isinstance(page, dict) else []
        items.extend(values)
        nxt = page.get("next") if isinstance(page, dict) else None
        if len(items) >= limit or not nxt:
            return items[:limit]
        page = request("GET", nxt)


def read_body(args):
    if getattr(args, "body", None) is not None:
        return args.body
    path = getattr(args, "body_file", None)
    if not path:
        return None
    if path == "-":
        buf = getattr(sys.stdin, "buffer", None)
        text = buf.read().decode("utf-8-sig") if buf else sys.stdin.read()
        return text.lstrip("\ufeff")
    return Path(path).read_bytes().decode("utf-8-sig")


def setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def emit_text(text):
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
