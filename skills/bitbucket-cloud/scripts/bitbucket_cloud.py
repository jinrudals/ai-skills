#!/usr/bin/env python3
"""bitbucket-cloud: dependency-free CLI for the Bitbucket Cloud REST API 2.0.

Credentials come from env vars (BITBUCKET_EMAIL, BITBUCKET_API_TOKEN,
BITBUCKET_WORKSPACE) or the config file written by `configure`.
Runs on Python 3.8+ on Windows and POSIX using only the standard library.
"""

import argparse
import base64
import json
import os
import string
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

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
    payload = json.dumps(data, indent=2).encode("utf-8")
    if sys.platform == "win32":
        path.write_bytes(payload)
    else:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
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
        target = urllib.parse.urlsplit(newurl)
        if new is not None and (target.scheme != "https" or target.hostname != API_HOST):
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
    if str(segment) in (".", ".."):
        raise ConfigError(f"invalid path segment: {segment!r}")
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


# ------------------------------------------------------------- framework ----

_SCOPE_NAMES = {
    "repository": "rwad", "pullrequest": "rw", "project": "ra", "workspace": "ra",
    "user": "rw", "pipeline": "rwa", "runner": "rw", "issue": "rwd",
    "webhook": "rwd", "snippet": "rwd", "ssh-key": "rwd", "gpg-key": "rwd",
    "permission": "rwd",
}
_PREFIX = {"r": "read", "w": "write", "a": "admin", "d": "delete"}
KNOWN_SCOPES = frozenset(
    f"{_PREFIX[k]}:{name}:bitbucket" for name, kinds in _SCOPE_NAMES.items() for k in kinds
)


def _scopes(*names):
    return tuple(f"{n}:bitbucket" for n in names)


_READ_ONLY = _scopes(
    "read:repository", "read:pullrequest", "read:pipeline", "read:issue",
    "read:webhook", "read:user", "read:workspace",
)
_DEV = _READ_ONLY + _scopes(
    "write:repository", "write:pullrequest", "write:pipeline", "write:issue"
)
PRESETS = {
    "read-only": _READ_ONLY,
    "dev": _DEV,
    "admin": _DEV + _scopes(
        "write:webhook", "admin:repository", "write:permission",
        "delete:permission", "delete:webhook", "delete:issue",
    ),
}


@dataclass
class ArgSpec:
    names: tuple
    opts: dict = field(default_factory=dict)


def arg(*names, **opts):
    return ArgSpec(names, opts)


@dataclass
class Cmd:
    area: str
    action: str
    method: str
    path: str
    scopes: tuple = ()
    destructive: bool = False
    list_result: bool = False
    text: bool = False
    handler: Optional[Callable] = None
    args: tuple = ()
    help: str = ""

    @property
    def key(self):
        return f"{self.area} {self.action}".strip()


COMMANDS = []


def register(cmd):
    COMMANDS.append(cmd)


def _placeholders(path):
    return [n for _, n, _, _ in string.Formatter().parse(path) if n and n != "ws"]


def workspace(args):
    ws = (getattr(args, "workspace", None) or setting("workspace")).strip()
    if not ws:
        raise ConfigError("no workspace; pass --workspace or run `configure --workspace NAME`")
    return ws


def resolve_path(cmd, args):
    values = {n: quote(getattr(args, n)) for n in _placeholders(cmd.path)}
    if "{ws}" in cmd.path:
        values["ws"] = quote(workspace(args))
    return cmd.path.format(**values)


def require_yes(args, method, url, body):
    if getattr(args, "yes", False):
        return
    emit({"dry_run": True, "method": method, "url": url, "body": body})
    print("not executed: re-run with --yes to send this request", file=sys.stderr)
    raise SystemExit(5)


def run(cmd, args, *, body=None, params=None, path=None, method=None, destructive=None):
    method = method or cmd.method
    path = path if path is not None else resolve_path(cmd, args)
    gated = cmd.destructive if destructive is None else destructive
    if gated:
        url = path if path.startswith("http") else BASE + path
        require_yes(args, method, url, body)
    if cmd.list_result and method == "GET":
        emit(paginate(path, params, args.limit))
        return 0
    res = request(method, path, params=params, body=body, raw=cmd.text)
    if cmd.text:
        emit_text(res or "")
    else:
        emit(res if res is not None else {"ok": True})
    return 0


def scope_hint(command_key):
    for cmd in COMMANDS:
        if cmd.key == command_key and cmd.scopes:
            return f"{command_key} needs scopes: {', '.join(cmd.scopes)}"
    return f"{command_key}: check the token's scopes (run `scopes`)"


def _add_common(parser):
    parser.add_argument("--workspace", help="Bitbucket workspace slug (default: configured)")
    parser.add_argument("--limit", type=int, default=100, help="max items for list commands")
    parser.add_argument("--yes", action="store_true", help="confirm destructive requests")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="bitbucket_cloud.py", description="Bitbucket Cloud REST CLI"
    )
    sub = parser.add_subparsers(dest="area", metavar="AREA")
    sub.required = True
    groups = {}
    for cmd in COMMANDS:
        if cmd.action:
            if cmd.area not in groups:
                area_parser = sub.add_parser(cmd.area, help=f"{cmd.area} commands")
                groups[cmd.area] = area_parser.add_subparsers(dest="action", metavar="ACTION")
                groups[cmd.area].required = True
            leaf = groups[cmd.area].add_parser(cmd.action, help=cmd.help)
        else:
            leaf = sub.add_parser(cmd.area, help=cmd.help)
        _add_common(leaf)
        for name in _placeholders(cmd.path):
            leaf.add_argument(name)
        for spec in cmd.args:
            leaf.add_argument(*spec.names, **spec.opts)
        leaf.set_defaults(_cmd=cmd)
    return parser


def main(argv=None):
    setup_stdio()
    args = build_parser().parse_args(argv)
    cmd = args._cmd
    try:
        rc = cmd.handler(args, cmd) if cmd.handler else run(cmd, args)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except ApiError as e:
        print(f"error: {e}", file=sys.stderr)
        if e.status in (401, 403):
            if e.status == 401:
                print("hint: check the email/token (run `check`)", file=sys.stderr)
            else:
                print(f"hint: {scope_hint(cmd.key)}", file=sys.stderr)
            return 3
        return 4
    return rc or 0


# ------------------------------------------------------------- meta cmds ----


def _check(args, cmd):
    calls = [("GET /user", "/user", "read:user:bitbucket")]
    ws = (getattr(args, "workspace", None) or setting("workspace")).strip()
    if ws:
        calls.append((f"GET /workspaces/{ws}", f"/workspaces/{quote(ws)}", "read:workspace:bitbucket"))
    rows, code = [], 0
    for label, path, scope in calls:
        try:
            request("GET", path)
            rows.append({"call": label, "ok": True})
        except ApiError as e:
            code = code or (3 if e.status in (401, 403) else 4)
            rows.append({"call": label, "ok": False, "status": e.status,
                         "message": e.message, "hint": f"needs scope: {scope}"})
    emit(rows)
    return code


def _scopes_cmd(args, cmd):
    if args.preset:
        emit({"preset": args.preset, "scopes": list(PRESETS[args.preset])})
    else:
        emit([{"command": c.key, "scopes": list(c.scopes)} for c in COMMANDS])
    return 0


def _api_cmd(args, cmd):
    method = args.method.upper()
    body = read_body(args)
    path = args.path if args.path.startswith("http") else "/" + args.path.lstrip("/")
    return run(cmd, args, body=body, path=path, method=method, destructive=method != "GET")


register(Cmd("configure", "", "", "", help="save credentials to the config file",
             handler=lambda a, c: configure(a),
             args=(arg("--email"), arg("--token"))))
register(Cmd("check", "", "GET", "/user", scopes=_scopes("read:user", "read:workspace"),
             help="verify credentials and workspace access", handler=_check))
register(Cmd("scopes", "", "", "", help="show required scopes per command or a preset",
             handler=_scopes_cmd, args=(arg("--preset", choices=sorted(PRESETS)),)))
register(Cmd("api", "", "", "", help="raw METHOD PATH request (non-GET needs --yes)",
             handler=_api_cmd,
             args=(arg("method"), arg("path"), arg("--body"), arg("--body-file"))))


REPO = "/repositories/{ws}/{repo}"
R_READ = _scopes("read:repository")


def _branches(args, cmd):
    params = None
    if args.query:
        params = {"q": 'name~"{}"'.format(args.query.replace('"', '\\"'))}
    return run(cmd, args, params=params)


def _branch_create(args, cmd):
    body = {"name": args.name, "target": {"hash": args.from_commit}}
    return run(cmd, args, body=body)


def _commit_list(args, cmd):
    path = resolve_path(cmd, args)
    if args.revision:
        path += "/" + quote(args.revision)
    return run(cmd, args, path=path)


def _commit_file(args, cmd):
    path = f"{resolve_path(cmd, args)}/{quote(args.ref)}/{quote_path(args.path)}"
    return run(cmd, args, path=path)


register(Cmd("repo", "list", "GET", "/repositories/{ws}", R_READ, list_result=True,
             help="list repositories in the workspace"))
register(Cmd("repo", "get", "GET", REPO, R_READ, help="show one repository"))
register(Cmd("repo", "branches", "GET", REPO + "/refs/branches", R_READ, list_result=True,
             handler=_branches, args=(arg("--query", help="filter by branch name"),),
             help="list branches"))
register(Cmd("repo", "branch-create", "POST", REPO + "/refs/branches",
             _scopes("write:repository", "read:repository"), handler=_branch_create,
             args=(arg("name"), arg("--from", dest="from_commit", required=True,
                                    help="commit hash to branch from")),
             help="create a branch"))
register(Cmd("repo", "tags", "GET", REPO + "/refs/tags", R_READ, list_result=True,
             help="list tags"))
register(Cmd("commit", "list", "GET", REPO + "/commits", R_READ, list_result=True,
             handler=_commit_list, args=(arg("--revision", help="branch, tag or hash"),),
             help="list commits"))
register(Cmd("commit", "get", "GET", REPO + "/commit/{sha}", R_READ, help="show one commit"))
register(Cmd("commit", "diff", "GET", REPO + "/diff/{spec}", R_READ, text=True,
             help="diff of a commit or a..b spec"))
register(Cmd("commit", "file", "GET", REPO + "/src", R_READ, text=True,
             handler=_commit_file, args=(arg("path"), arg("--ref", required=True)),
             help="file content at a ref"))


PRS = REPO + "/pullrequests"
PR_READ = _scopes("read:pullrequest")
PR_WRITE = _scopes("read:pullrequest", "write:pullrequest")
MERGE_STRATEGIES = ("merge_commit", "squash", "fast_forward", "squash_fast_forward",
                    "rebase_fast_forward", "rebase_merge")
_TEXT_ARGS = (arg("--body"), arg("--body-file"))


def _text(args, required=False):
    text = read_body(args)
    if required and not text:
        raise ConfigError("provide text with --body, --body-file or --body-file -")
    return text


def _pr_list(args, cmd):
    return run(cmd, args, params={"state": args.state})


def _pr_create(args, cmd):
    body = {
        "title": args.title,
        "source": {"branch": {"name": args.source}},
        "reviewers": [{"uuid": u} for u in args.reviewer],
        "close_source_branch": args.close_source_branch,
    }
    if args.dest:
        body["destination"] = {"branch": {"name": args.dest}}
    text = _text(args)
    if text:
        body["description"] = text
    return run(cmd, args, body=body)


def _pr_update(args, cmd):
    body = {}
    if args.title:
        body["title"] = args.title
    text = _text(args)
    if text:
        body["description"] = text
    if args.dest:
        body["destination"] = {"branch": {"name": args.dest}}
    if not body:
        raise ConfigError("nothing to update: pass --title, --description or --dest")
    return run(cmd, args, body=body)


def _pr_comment_add(args, cmd):
    body = {"content": {"raw": _text(args, required=True)}}
    if args.parent:
        body["parent"] = {"id": args.parent}
    return run(cmd, args, body=body)


def _pr_merge(args, cmd):
    body = {"type": "pullrequest_merge_parameters"}
    if args.strategy:
        body["merge_strategy"] = args.strategy
    if args.message:
        body["message"] = args.message
    if args.close_source_branch:
        body["close_source_branch"] = True
    return run(cmd, args, body=body)


def _pr_decline(args, cmd):
    return run(cmd, args, body={"reason": args.reason} if args.reason else None)


def _task_add(args, cmd):
    body = {"content": {"raw": _text(args, required=True)}}
    if args.comment:
        body["comment"] = {"id": args.comment}
    return run(cmd, args, body=body)


def _task_update(args, cmd):
    body = {}
    text = _text(args)
    if text:
        body["content"] = {"raw": text}
    if args.state:
        body["state"] = args.state
    if not body:
        raise ConfigError("nothing to update: pass --body or --state")
    return run(cmd, args, body=body)


_DESC = arg("--body", "--description", dest="body", help="description text")
register(Cmd("pr", "list", "GET", PRS, PR_READ, list_result=True, handler=_pr_list,
             args=(arg("--state", default="OPEN",
                       choices=("OPEN", "MERGED", "DECLINED", "SUPERSEDED")),),
             help="list pull requests"))
register(Cmd("pr", "get", "GET", PRS + "/{id}", PR_READ, help="show a pull request"))
register(Cmd("pr", "create", "POST", PRS, PR_WRITE, handler=_pr_create,
             args=(arg("--title", required=True), arg("--source", required=True),
                   arg("--dest"), _DESC, arg("--body-file"),
                   arg("--reviewer", action="append", default=[], metavar="UUID"),
                   arg("--close-source-branch", action="store_true")),
             help="create a pull request"))
register(Cmd("pr", "update", "PUT", PRS + "/{id}", PR_WRITE, handler=_pr_update,
             args=(arg("--title"), arg("--dest"), _DESC, arg("--body-file")),
             help="update title, description or destination"))
register(Cmd("pr", "diff", "GET", PRS + "/{id}/diff", PR_READ, text=True,
             help="unified diff of a pull request"))
register(Cmd("pr", "comments", "GET", PRS + "/{id}/comments", PR_READ, list_result=True,
             help="list comments"))
register(Cmd("pr", "comment-add", "POST", PRS + "/{id}/comments", PR_READ,
             handler=_pr_comment_add,
             args=_TEXT_ARGS + (arg("--parent", type=int, help="parent comment id"),),
             help="add a comment"))
register(Cmd("pr", "approve", "POST", PRS + "/{id}/approve", PR_WRITE, help="approve"))
register(Cmd("pr", "unapprove", "DELETE", PRS + "/{id}/approve", _scopes("write:pullrequest"),
             help="remove your approval"))
register(Cmd("pr", "request-changes", "POST", PRS + "/{id}/request-changes", PR_WRITE,
             help="request changes"))
register(Cmd("pr", "merge", "POST", PRS + "/{id}/merge", PR_WRITE, destructive=True,
             handler=_pr_merge,
             args=(arg("--strategy", choices=MERGE_STRATEGIES), arg("--message"),
                   arg("--close-source-branch", action="store_true")),
             help="merge a pull request (needs --yes)"))
register(Cmd("pr", "decline", "POST", PRS + "/{id}/decline", PR_WRITE, destructive=True,
             handler=_pr_decline, args=(arg("--reason"),),
             help="decline a pull request (needs --yes)"))
register(Cmd("task", "list", "GET", PRS + "/{pr_id}/tasks", PR_READ, list_result=True,
             help="list tasks of a pull request"))
register(Cmd("task", "add", "POST", PRS + "/{pr_id}/tasks", PR_READ, handler=_task_add,
             args=_TEXT_ARGS + (arg("--comment", type=int, help="attach to comment id"),),
             help="add a task"))
register(Cmd("task", "update", "PUT", PRS + "/{pr_id}/tasks/{task_id}", PR_READ,
             handler=_task_update,
             args=_TEXT_ARGS + (arg("--state", choices=("RESOLVED", "UNRESOLVED")),),
             help="change task text or state"))
register(Cmd("task", "delete", "DELETE", PRS + "/{pr_id}/tasks/{task_id}", PR_READ,
             destructive=True, help="delete a task (needs --yes)"))

PIPES = REPO + "/pipelines/"
PIPE_READ = _scopes("read:pipeline")
PIPE_RW = _scopes("read:pipeline", "write:pipeline")
HOOKS = REPO + "/hooks"
PERMS = REPO + "/permissions-config"
ISSUES = REPO + "/issues"
ISSUE_READ = _scopes("read:issue")
ISSUE_RW = _scopes("read:issue", "write:issue")


def _pipeline_trigger(args, cmd):
    target = {"type": "pipeline_ref_target", "ref_type": "branch", "ref_name": args.branch}
    if args.pattern:
        target["selector"] = {"type": "custom", "pattern": args.pattern}
    body = {"target": target}
    variables = []
    for item in args.var:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise ConfigError(f"--var expects KEY=VALUE, got {item!r}")
        variables.append({"key": key, "value": value})
    if variables:
        body["variables"] = variables
    return run(cmd, args, body=body)


def _pipeline_log(args, cmd):
    base = resolve_path(cmd, args)
    if not args.step:
        emit(paginate(base + "/steps/", None, args.limit))
        return 0
    emit_text(request("GET", f"{base}/steps/{quote(args.step)}/log", raw=True) or "")
    return 0


def _webhook_create(args, cmd):
    body = {"description": args.description or "", "url": args.url, "active": True,
            "events": args.event}
    return run(cmd, args, body=body)


def _perm_target(args):
    if bool(args.user) == bool(args.group):
        raise ConfigError("pass exactly one of --user or --group")
    kind, ident = ("users", args.user) if args.user else ("groups", args.group)
    return f"/{kind}/{quote(ident)}"


def _perm_list(args, cmd):
    base = resolve_path(cmd, args)
    emit({
        "users": paginate(base + "/users", None, args.limit),
        "groups": paginate(base + "/groups", None, args.limit),
    })
    return 0


def _perm_set(args, cmd):
    return run(cmd, args, path=resolve_path(cmd, args) + _perm_target(args),
               body={"permission": args.permission})


def _perm_remove(args, cmd):
    return run(cmd, args, path=resolve_path(cmd, args) + _perm_target(args))


def _issue_create(args, cmd):
    body = {"title": args.title}
    text = _text(args)
    if text:
        body["content"] = {"raw": text}
    for name in ("kind", "priority"):
        if getattr(args, name):
            body[name] = getattr(args, name)
    return run(cmd, args, body=body)


def _issue_update(args, cmd):
    body = {}
    if args.title:
        body["title"] = args.title
    text = _text(args)
    if text:
        body["content"] = {"raw": text}
    if args.state:
        body["state"] = args.state
    if not body:
        raise ConfigError("nothing to update: pass --title, --body or --state")
    return run(cmd, args, body=body)


def _issue_comment(args, cmd):
    return run(cmd, args, body={"content": {"raw": _text(args, required=True)}})


_PERM_WHO = (arg("--user", help="Atlassian account id"), arg("--group", help="group slug"))
register(Cmd("pipeline", "list", "GET", PIPES, PIPE_READ, list_result=True,
             handler=lambda a, c: run(c, a, params={"sort": "-created_on"}),
             help="list pipelines, newest first"))
register(Cmd("pipeline", "get", "GET", PIPES + "{uuid}", PIPE_READ, help="show a pipeline"))
register(Cmd("pipeline", "trigger", "POST", PIPES, PIPE_RW, destructive=True,
             handler=_pipeline_trigger,
             args=(arg("--branch", required=True), arg("--pattern"),
                   arg("--var", action="append", default=[], metavar="KEY=VALUE")),
             help="run a pipeline (needs --yes)"))
register(Cmd("pipeline", "stop", "POST", PIPES + "{uuid}/stopPipeline",
             _scopes("write:pipeline"), destructive=True, help="stop a pipeline (needs --yes)"))
register(Cmd("pipeline", "log", "GET", REPO + "/pipelines/{uuid}", PIPE_READ,
             handler=_pipeline_log, args=(arg("--step", help="step uuid; omit to list steps"),),
             help="list steps, or print one step's log"))
register(Cmd("webhook", "list", "GET", HOOKS, _scopes("read:webhook"), list_result=True,
             help="list webhooks"))
register(Cmd("webhook", "create", "POST", HOOKS, _scopes("read:webhook", "write:webhook"),
             handler=_webhook_create,
             args=(arg("--url", required=True),
                   arg("--event", action="append", required=True, metavar="EVENT"),
                   arg("--description")),
             help="create a webhook"))
register(Cmd("webhook", "delete", "DELETE", HOOKS + "/{uid}", _scopes("delete:webhook"),
             destructive=True, help="delete a webhook (needs --yes)"))
register(Cmd("perm", "list", "GET", PERMS, _scopes("read:repository"), handler=_perm_list,
             help="list explicit user and group permissions"))
register(Cmd("perm", "set", "PUT", PERMS, _scopes("admin:repository", "write:permission"),
             destructive=True, handler=_perm_set,
             args=_PERM_WHO + (arg("--permission", required=True,
                                   choices=("read", "write", "admin")),),
             help="grant a permission (needs --yes)"))
register(Cmd("perm", "remove", "DELETE", PERMS,
             _scopes("admin:repository", "delete:permission"),
             destructive=True, handler=_perm_remove, args=_PERM_WHO,
             help="revoke a permission (needs --yes)"))
register(Cmd("issue", "list", "GET", ISSUES, ISSUE_READ, list_result=True, help="list issues"))
register(Cmd("issue", "get", "GET", ISSUES + "/{id}", ISSUE_READ, help="show an issue"))
register(Cmd("issue", "create", "POST", ISSUES, ISSUE_RW, handler=_issue_create,
             args=(arg("--title", required=True), _DESC, arg("--body-file"),
                   arg("--kind"), arg("--priority")),
             help="create an issue"))
register(Cmd("issue", "update", "PUT", ISSUES + "/{id}", ISSUE_RW, handler=_issue_update,
             args=(arg("--title"), _DESC, arg("--body-file"), arg("--state")),
             help="update an issue"))
register(Cmd("issue", "comment", "POST", ISSUES + "/{id}/comments", ISSUE_RW,
             handler=_issue_comment, args=_TEXT_ARGS, help="comment on an issue"))


if __name__ == "__main__":
    sys.exit(main())
