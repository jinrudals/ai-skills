#!/usr/bin/env python3
"""
atlassian_cloud.py — zero-dependency CLI for Jira Cloud and Confluence Cloud
REST APIs. No MCP, no third-party packages: only the Python 3 standard
library (urllib, json, base64, argparse).

For Bitbucket Cloud, use the separate bitbucket-cloud skill instead —
Bitbucket Cloud no longer accepts this account-level API token; it needs a
Bitbucket-scoped token and a different auth shape.

Auth — two layers, env vars always win over the config file:

  1. Env vars (good for CI/one-off overrides):
     ATLASSIAN_SITE, ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN

  2. A global config file (good for interactive/day-to-day use — set once,
     works in every new shell without re-exporting anything):
     ~/.config/atlassian-cloud/credentials.json (override the path with
     ATLASSIAN_CLOUD_CONFIG). Create/update it with:

       python3 scripts/atlassian_cloud.py configure --site yourco \
         --email you@yourco.com --token xxxx

     Written with mode 0600. See references/setup.md for the full guide.

All commands print raw JSON to stdout on success. Errors go to stderr and
set a non-zero exit code; HTTP error bodies are printed as-is (Atlassian
error payloads are already JSON).

See references/api-notes.md for endpoint details, ADF body format, and CQL/JQL
positional-argument conventions mirrored from this skill's SKILL.md.
"""
import re
import argparse
import base64
import json
import mimetypes
import os
import stat
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request

_CONFIG_KEYS = {
    "site": "ATLASSIAN_SITE",
    "email": "ATLASSIAN_EMAIL",
    "token": "ATLASSIAN_API_TOKEN",
}


def _config_path():
    return os.environ.get(
        "ATLASSIAN_CLOUD_CONFIG",
        os.path.expanduser("~/.config/atlassian-cloud/credentials.json"),
    )


def _load_config():
    path = _config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError) as e:
        _fail(f"could not read config file {path}: {e}")


def _setting(key):
    """Resolve one credential: env var first, then the config file."""
    env_name = _CONFIG_KEYS[key]
    val = os.environ.get(env_name, "").strip()
    if val:
        return val
    return str(_load_config().get(key, "")).strip()


def _site_base(kind):
    site = _setting("site")
    if not site:
        _fail(
            f"no site configured for {kind} — set ATLASSIAN_SITE or run "
            f"'atlassian_cloud.py configure --site ...'"
        )
    if site.startswith("http://") or site.startswith("https://"):
        return site.rstrip("/")
    return f"https://{site}.atlassian.net"


def _fail(msg, code=2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def _auth_header(kind):
    email = _setting("email")
    if not email:
        _fail(
            f"no email configured for {kind} — set ATLASSIAN_EMAIL or run "
            f"'atlassian_cloud.py configure --email ...'"
        )
    token = _setting("token")
    if not token:
        _fail(
            "no API token configured — set ATLASSIAN_API_TOKEN or run "
            "'atlassian_cloud.py configure --token ...'"
        )
    raw = f"{email}:{token}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def configure(args):
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cfg = _load_config()
    updates = {
        "site": args.site,
        "email": args.email,
        "token": args.token,
    }
    for key, value in updates.items():
        if value is not None:
            cfg[key] = value
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600 — it holds a secret
    redacted = dict(cfg)
    if redacted.get("token"):
        redacted["token"] = "***redacted***"
    print(f"wrote {path} (mode 0600):")
    print(json.dumps(redacted, indent=2))


def _request(method, url, kind, body=None, extra_headers=None):
    headers = {
        "Authorization": _auth_header(kind),
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, raw


def _print_result(status, raw):
    text = raw.decode("utf-8", errors="replace") if raw else ""
    if text:
        try:
            parsed = json.loads(text)
            print(json.dumps(parsed, indent=2, ensure_ascii=False))
        except ValueError:
            print(text)
    if status >= 400:
        sys.exit(1)


def _build_multipart(files, fields=None):
    """Build a multipart/form-data body with the stdlib only.

    files: dict of field-name -> (filename, bytes, content_type)
    fields: optional dict of field-name -> str, for plain form fields
    """
    boundary = uuid.uuid4().hex
    chunks = []
    for name, value in (fields or {}).items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    for name, (filename, content, content_type) in files.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        chunks.append(content)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return boundary, b"".join(chunks)


def _request_multipart(url, kind, file_path, field_name="file", extra_headers=None):
    """POST a single file as multipart/form-data. Used for Jira/Confluence
    attachment uploads, both of which also require X-Atlassian-Token: no-check
    (CSRF guard against unsolicited uploads) in addition to Basic auth."""
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as fh:
        content = fh.read()
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    boundary, body = _build_multipart({field_name: (filename, content, content_type)})
    headers = {
        "Authorization": _auth_header(kind),
        "Accept": "application/json",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "X-Atlassian-Token": "no-check",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _download(url, kind, out_path):
    req = urllib.request.Request(url, headers={"Authorization": _auth_header(kind)})
    try:
        with urllib.request.urlopen(req) as resp:
            with open(out_path, "wb") as fh:
                fh.write(resp.read())
        print(f"saved: {out_path}")
    except urllib.error.HTTPError as e:
        _print_result(e.code, e.read())


_INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|https?://[^\s<>)]+)")
_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _inline(text):
    """Inline markup: **bold**, `code`, bare URLs -> link; rest plain text."""
    nodes = []
    for part in _INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            nodes.append({"type": "text", "text": part[2:-2], "marks": [{"type": "strong"}]})
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            nodes.append({"type": "text", "text": part[1:-1], "marks": [{"type": "code"}]})
        elif part.startswith(("http://", "https://")):
            nodes.append({"type": "text", "text": part, "marks": [{"type": "link", "attrs": {"href": part}}]})
        else:
            nodes.append({"type": "text", "text": part})
    return nodes


def _paragraph(lines):
    nodes = []
    for i, line in enumerate(lines):
        if i:
            nodes.append({"type": "hardBreak"})
        nodes.extend(_inline(line))
    return {"type": "paragraph", "content": nodes}


def _build_list(items, i, indent):
    """items: [(indent, ordered, text)]. Returns (listNode, next_index)."""
    ordered = items[i][1]
    node = {"type": "orderedList" if ordered else "bulletList", "content": []}
    while i < len(items) and items[i][0] >= indent:
        ind, _, txt = items[i]
        if ind > indent:  # deeper than this list level without a parent: treat as sibling
            ind = indent
        li = {"type": "listItem", "content": [{"type": "paragraph", "content": _inline(txt)}]}
        i += 1
        if i < len(items) and items[i][0] > indent:
            sub, i = _build_list(items, i, items[i][0])
            li["content"].append(sub)
        node["content"].append(li)
    return node, i


def _text_to_adf(text):
    """Convert light Markdown-style text into Atlassian Document Format.
    Supports: blank-line paragraphs, single newline = line break, `# ` headings,
    `-`/`*`/`1.` lists with indentation-based nesting, **bold**, `code`, and
    bare URLs. Anything richer (mentions, panels, tables): build ADF by hand
    via --fields-json — see references/api-notes.md."""
    if not text:
        return {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": []}]}
    content, para, items = [], [], []

    def flush_para():
        if para:
            content.append(_paragraph(para))
            para.clear()

    def flush_list():
        i = 0
        while i < len(items):
            node, i = _build_list(items, i, items[i][0])
            content.append(node)
        items.clear()

    for line in text.split("\n"):
        m_list = _LIST_RE.match(line)
        m_head = _HEADING_RE.match(line)
        if not line.strip():
            flush_para()
            flush_list()
        elif m_list:
            flush_para()
            items.append((len(m_list.group(1).expandtabs(4)), m_list.group(2)[0].isdigit(), m_list.group(3)))
        elif m_head:
            flush_para()
            flush_list()
            content.append({"type": "heading", "attrs": {"level": len(m_head.group(1))},
                            "content": _inline(m_head.group(2))})
        else:
            flush_list()
            para.append(line.strip())
    flush_para()
    flush_list()
    return {"type": "doc", "version": 1, "content": content}


# ---------------------------------------------------------------- Jira ----

def jira_issue_get(args):
    base = _site_base("jira")
    url = f"{base}/rest/api/3/issue/{urllib.parse.quote(args.key)}"
    if args.fields:
        url += "?" + urllib.parse.urlencode({"fields": args.fields})
    status, raw = _request("GET", url, "jira")
    _print_result(status, raw)


def jira_issue_create(args):
    base = _site_base("jira")
    fields = {
        "project": {"key": args.project},
        "summary": args.summary,
        "issuetype": {"name": args.type},
    }
    if args.description:
        fields["description"] = _text_to_adf(args.description)
    if args.fields_json:
        fields.update(json.loads(args.fields_json))
    status, raw = _request("POST", f"{base}/rest/api/3/issue", "jira", {"fields": fields})
    _print_result(status, raw)


def jira_issue_update(args):
    base = _site_base("jira")
    fields = {}
    if args.summary:
        fields["summary"] = args.summary
    if args.description:
        fields["description"] = _text_to_adf(args.description)
    if args.fields_json:
        fields.update(json.loads(args.fields_json))
    url = f"{base}/rest/api/3/issue/{urllib.parse.quote(args.key)}"
    status, raw = _request("PUT", url, "jira", {"fields": fields})
    _print_result(status if status else 204, raw)


def jira_issue_search(args):
    base = _site_base("jira")
    body = {"jql": args.jql, "maxResults": args.max_results}
    if args.fields:
        body["fields"] = args.fields.split(",")
    status, raw = _request("POST", f"{base}/rest/api/3/search/jql", "jira", body)
    _print_result(status, raw)


def jira_comment_add(args):
    base = _site_base("jira")
    url = f"{base}/rest/api/3/issue/{urllib.parse.quote(args.key)}/comment"
    status, raw = _request("POST", url, "jira", {"body": _text_to_adf(args.text)})
    _print_result(status, raw)


def jira_comment_get(args):
    base = _site_base("jira")
    url = f"{base}/rest/api/3/issue/{urllib.parse.quote(args.key)}/comment/{args.comment_id}"
    status, raw = _request("GET", url, "jira")
    _print_result(status, raw)


def jira_comment_update(args):
    base = _site_base("jira")
    url = f"{base}/rest/api/3/issue/{urllib.parse.quote(args.key)}/comment/{args.comment_id}"
    status, raw = _request("PUT", url, "jira", {"body": _text_to_adf(args.text)})
    _print_result(status, raw)


def jira_transition(args):
    base = _site_base("jira")
    key = urllib.parse.quote(args.key)
    if args.list:
        status, raw = _request("GET", f"{base}/rest/api/3/issue/{key}/transitions", "jira")
        _print_result(status, raw)
        return
    status, raw = _request(
        "GET", f"{base}/rest/api/3/issue/{key}/transitions", "jira"
    )
    if status >= 400:
        _print_result(status, raw)
        return
    transitions = json.loads(raw).get("transitions", [])
    match = next((t for t in transitions if t["name"].lower() == args.to.lower()), None)
    if not match:
        names = [t["name"] for t in transitions]
        _fail(f"no transition named {args.to!r}; available: {names}")
    body = {"transition": {"id": match["id"]}}
    if args.comment:
        body["update"] = {"comment": [{"add": {"body": _text_to_adf(args.comment)}}]}
    status, raw = _request("POST", f"{base}/rest/api/3/issue/{key}/transitions", "jira", body)
    _print_result(status if status else 204, raw or b"{}")


def jira_issue_delete(args):
    base = _site_base("jira")
    url = f"{base}/rest/api/3/issue/{urllib.parse.quote(args.key)}"
    if args.delete_subtasks:
        url += "?" + urllib.parse.urlencode({"deleteSubtasks": "true"})
    status, raw = _request("DELETE", url, "jira")
    _print_result(status if status else 204, raw or b"{}")


def jira_attachment_add(args):
    base = _site_base("jira")
    url = f"{base}/rest/api/3/issue/{urllib.parse.quote(args.key)}/attachments"
    status, raw = _request_multipart(url, "jira", args.file)
    _print_result(status, raw)


def jira_attachment_list(args):
    base = _site_base("jira")
    url = f"{base}/rest/api/3/issue/{urllib.parse.quote(args.key)}?fields=attachment"
    status, raw = _request("GET", url, "jira")
    _print_result(status, raw)


def jira_attachment_download(args):
    base = _site_base("jira")
    # the attachment's own "content" URL is absolute and already signed by
    # auth headers; fetched via the attachment metadata endpoint first.
    status, raw = _request("GET", f"{base}/rest/api/3/attachment/{args.id}", "jira")
    if status >= 400:
        _print_result(status, raw)
        return
    meta = json.loads(raw)
    out = args.output or meta["filename"]
    _download(meta["content"], "jira", out)


# ----------------------------------------------------------- Confluence ----

def confluence_page_get(args):
    base = _site_base("confluence")
    url = f"{base}/wiki/api/v2/pages/{args.id}?body-format=storage"
    status, raw = _request("GET", url, "confluence")
    _print_result(status, raw)


def confluence_page_create(args):
    base = _site_base("confluence")
    with open(args.body_file, encoding="utf-8") as fh:
        value = fh.read()
    body = {
        "spaceId": args.space_id,
        "status": "current",
        "title": args.title,
        "body": {"representation": "storage", "value": value},
    }
    if args.parent_id:
        body["parentId"] = args.parent_id
    status, raw = _request("POST", f"{base}/wiki/api/v2/pages", "confluence", body)
    _print_result(status, raw)


def confluence_page_update(args):
    base = _site_base("confluence")
    with open(args.body_file, encoding="utf-8") as fh:
        value = fh.read()
    body = {
        "id": str(args.id),
        "status": "current",
        "title": args.title,
        "body": {"representation": "storage", "value": value},
        "version": {"number": args.if_version + 1, "message": args.message or "updated via atlassian_cloud.py"},
    }
    status, raw = _request("PUT", f"{base}/wiki/api/v2/pages/{args.id}", "confluence", body)
    _print_result(status, raw)


def confluence_search(args):
    base = _site_base("confluence")
    url = f"{base}/wiki/rest/api/content/search?" + urllib.parse.urlencode(
        {"cql": args.cql, "limit": args.limit}
    )
    status, raw = _request("GET", url, "confluence")
    _print_result(status, raw)


def confluence_page_delete(args):
    base = _site_base("confluence")
    status, raw = _request("DELETE", f"{base}/wiki/api/v2/pages/{args.id}", "confluence")
    _print_result(status if status else 204, raw or b"{}")


def confluence_attachment_add(args):
    base = _site_base("confluence")
    # the v1 content/child/attachment endpoint is used here deliberately: it
    # is the stable multipart upload path; v2 has no equivalent yet.
    url = f"{base}/wiki/rest/api/content/{args.id}/child/attachment"
    status, raw = _request_multipart(url, "confluence", args.file, field_name="file")
    _print_result(status, raw)


def confluence_attachment_list(args):
    base = _site_base("confluence")
    url = f"{base}/wiki/rest/api/content/{args.id}/child/attachment"
    status, raw = _request("GET", url, "confluence")
    _print_result(status, raw)


def confluence_attachment_download(args):
    base = _site_base("confluence")
    status, raw = _request(
        "GET", f"{base}/wiki/rest/api/content/{args.id}/child/attachment", "confluence"
    )
    if status >= 400:
        _print_result(status, raw)
        return
    results = json.loads(raw).get("results", [])
    match = next((a for a in results if a["title"] == args.filename), None)
    if not match:
        _fail(f"no attachment named {args.filename!r} on page {args.id}; have: {[a['title'] for a in results]}")
    download_path = match["_links"]["download"]
    url = download_path if download_path.startswith("http") else f"{base}/wiki{download_path}"
    out = args.output or args.filename
    _download(url, "confluence", out)


def confluence_macro_wrap(args):
    """Print a <ac:structured-macro> XML snippet for any macro — built-in
    (info/note/warning/tip/panel/code/toc/expand/status/...) or one added by
    a marketplace app. Only the macro name and its parameter names need to be
    known; the storage-format wrapper is identical either way. Paste the
    output into a body file passed to page-create/page-update."""
    params_xml = ""
    for pair in args.param or []:
        key, _, value = pair.partition("=")
        params_xml += f'<ac:parameter ac:name="{key}">{value}</ac:parameter>'
    body_xml = ""
    if args.body_file:
        with open(args.body_file, encoding="utf-8") as fh:
            body_xml = f"<ac:rich-text-body>{fh.read()}</ac:rich-text-body>"
    elif args.plain_body is not None:
        body_xml = f"<ac:plain-text-body><![CDATA[{args.plain_body}]]></ac:plain-text-body>"
    print(
        f'<ac:structured-macro ac:name="{args.name}" ac:schema-version="1">'
        f"{params_xml}{body_xml}</ac:structured-macro>"
    )


# --------------------------------------------------------------- argparse ----

def build_parser():
    p = argparse.ArgumentParser(prog="atlassian_cloud.py", description=__doc__)
    sub = p.add_subparsers(dest="product", required=True)

    g = sub.add_parser(
        "configure",
        help="write/update the global credentials file (~/.config/atlassian-cloud/credentials.json)",
    )
    g.add_argument("--site", help="e.g. yourcompany, for https://yourcompany.atlassian.net")
    g.add_argument("--email")
    g.add_argument("--token", help="Atlassian API token")
    g.set_defaults(func=configure)

    # jira
    jira = sub.add_parser("jira").add_subparsers(dest="action", required=True)

    g = jira.add_parser("issue-get")
    g.add_argument("key")
    g.add_argument("--fields")
    g.set_defaults(func=jira_issue_get)

    g = jira.add_parser("issue-create")
    g.add_argument("--project", required=True)
    g.add_argument("--type", required=True)
    g.add_argument("--summary", required=True)
    g.add_argument("--description")
    g.add_argument("--fields-json", help="raw JSON merged into the fields object")
    g.set_defaults(func=jira_issue_create)

    g = jira.add_parser("issue-update")
    g.add_argument("key")
    g.add_argument("--summary")
    g.add_argument("--description")
    g.add_argument("--fields-json")
    g.set_defaults(func=jira_issue_update)

    g = jira.add_parser("issue-search")
    g.add_argument("jql")
    g.add_argument("--fields")
    g.add_argument("--max-results", type=int, default=50)
    g.set_defaults(func=jira_issue_search)

    g = jira.add_parser("comment-add")
    g.add_argument("key")
    g.add_argument("text")
    g.set_defaults(func=jira_comment_add)

    g = jira.add_parser("comment-get")
    g.add_argument("key")
    g.add_argument("comment_id")
    g.set_defaults(func=jira_comment_get)

    g = jira.add_parser("comment-update")
    g.add_argument("key")
    g.add_argument("comment_id")
    g.add_argument("text")
    g.set_defaults(func=jira_comment_update)

    g = jira.add_parser("transition")
    g.add_argument("key")
    g.add_argument("--to", help="target status/transition name")
    g.add_argument("--comment")
    g.add_argument("--list", action="store_true", help="list available transitions instead of applying one")
    g.set_defaults(func=jira_transition)

    g = jira.add_parser("issue-delete")
    g.add_argument("key")
    g.add_argument("--delete-subtasks", action="store_true")
    g.set_defaults(func=jira_issue_delete)

    g = jira.add_parser("attachment-add")
    g.add_argument("key")
    g.add_argument("file")
    g.set_defaults(func=jira_attachment_add)

    g = jira.add_parser("attachment-list")
    g.add_argument("key")
    g.set_defaults(func=jira_attachment_list)

    g = jira.add_parser("attachment-download")
    g.add_argument("id", help="attachment id, from attachment-list")
    g.add_argument("--output", help="output path; defaults to the original filename")
    g.set_defaults(func=jira_attachment_download)

    # confluence
    confluence = sub.add_parser("confluence").add_subparsers(dest="action", required=True)

    g = confluence.add_parser("page-get")
    g.add_argument("id")
    g.set_defaults(func=confluence_page_get)

    g = confluence.add_parser("page-create")
    g.add_argument("--space-id", required=True)
    g.add_argument("--title", required=True)
    g.add_argument("--body-file", required=True, help="file with Confluence storage-format (XHTML) body")
    g.add_argument("--parent-id")
    g.set_defaults(func=confluence_page_create)

    g = confluence.add_parser("page-update")
    g.add_argument("id")
    g.add_argument("--title", required=True)
    g.add_argument("--body-file", required=True)
    g.add_argument("--if-version", required=True, type=int, help="current version number read from page-get")
    g.add_argument("--message")
    g.set_defaults(func=confluence_page_update)

    g = confluence.add_parser("search")
    g.add_argument("cql")
    g.add_argument("--limit", type=int, default=25)
    g.set_defaults(func=confluence_search)

    g = confluence.add_parser("page-delete")
    g.add_argument("id")
    g.set_defaults(func=confluence_page_delete)

    g = confluence.add_parser("attachment-add")
    g.add_argument("id")
    g.add_argument("file")
    g.set_defaults(func=confluence_attachment_add)

    g = confluence.add_parser("attachment-list")
    g.add_argument("id")
    g.set_defaults(func=confluence_attachment_list)

    g = confluence.add_parser("attachment-download")
    g.add_argument("id")
    g.add_argument("filename", help="attachment title/filename, from attachment-list")
    g.add_argument("--output", help="output path; defaults to the attachment's filename")
    g.set_defaults(func=confluence_attachment_download)

    g = confluence.add_parser(
        "macro-wrap",
        help="print <ac:structured-macro> XML for any built-in or app-installed macro",
    )
    g.add_argument("name", help='macro name, e.g. "info", "code", "toc", or a marketplace app macro key')
    g.add_argument("--param", action="append", help='key=value, repeatable (e.g. --param language=python)')
    g.add_argument("--body-file", help="rich-text body: a file with storage-format XHTML content")
    g.add_argument("--plain-body", help="plain-text body (e.g. for the code macro), wrapped in CDATA")
    g.set_defaults(func=confluence_macro_wrap)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
