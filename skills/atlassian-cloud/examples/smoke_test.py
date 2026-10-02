#!/usr/bin/env python3
"""Offline smoke test for atlassian_cloud.py.

Spins up a tiny local HTTP server that mimics the shape of Jira/Confluence
Cloud responses, points ATLASSIAN_SITE at it, and runs commands through the
real script (subprocess, not mocks) to check request construction, auth
headers, multipart uploads, and JSON passthrough end-to-end without needing
live credentials.

Run: python3 examples/smoke_test.py
"""
import base64
import email
import email.policy
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "atlassian_cloud.py")

EXPECTED_AUTH = "Basic " + base64.b64encode(b"test@example.com:faketoken").decode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _check_auth(self):
        if self.headers.get("Authorization") != EXPECTED_AUTH:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error": "bad auth"}')
            return False
        return True

    def _reply(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def do_GET(self):
        if not self._check_auth():
            return
        path = self.path
        if path.startswith("/rest/api/3/issue/PROJ-1?fields=attachment"):
            self._reply(200, {"fields": {"attachment": [{"id": "999", "filename": "x.txt"}]}})
        elif path.startswith("/rest/api/3/issue/PROJ-1/transitions"):
            self._reply(200, {"transitions": [{"id": "31", "name": "Done"}]})
        elif path.startswith("/rest/api/3/issue/PROJ-1"):
            self._reply(200, {"key": "PROJ-1", "fields": {"summary": "Test issue"}})
        elif path.startswith("/wiki/api/v2/pages/42"):
            self._reply(200, {"id": "42", "title": "Page", "version": {"number": 3}})
        else:
            self._reply(404, {"error": "not found", "path": path})

    def do_POST(self):
        if not self._check_auth():
            return
        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        if ctype.startswith("multipart/form-data"):
            raw = self.rfile.read(length)
            msg = email.message_from_bytes(
                f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode() + raw,
                policy=email.policy.default,
            )
            uploaded = None
            for part in msg.iter_parts():
                if part.get_param("name", header="Content-Disposition") == "file":
                    uploaded = part.get_filename()
            if uploaded:
                self._reply(200, {"uploaded": uploaded})
            else:
                self._reply(400, {"error": "no file field found"})
            return
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/rest/api/3/search/jql":
            assert body["jql"] == "project = PROJ"
            self._reply(200, {"issues": [{"key": "PROJ-1"}]})
        elif self.path == "/rest/api/3/issue/PROJ-1/transitions":
            assert body["transition"]["id"] == "31"
            self._reply(204, {})
        else:
            self._reply(404, {"error": "not found", "path": self.path})

    def do_PUT(self):
        if not self._check_auth():
            return
        self._reply(200, {"ok": True})

    def do_DELETE(self):
        if not self._check_auth():
            return
        self.send_response(204)
        self.end_headers()


def run_cmd(env, *args):
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        env=env,
        capture_output=True,
        text=True,
    )


def main():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()

    env = dict(os.environ)
    env["ATLASSIAN_SITE"] = f"http://127.0.0.1:{port}"
    env["ATLASSIAN_EMAIL"] = "test@example.com"
    env["ATLASSIAN_API_TOKEN"] = "faketoken"

    checks = []

    def check(name, r, predicate):
        ok = r.returncode == 0 and predicate(r.stdout)
        checks.append((name, ok, r.returncode, r.stdout, r.stderr))

    check("jira issue-get", run_cmd(env, "jira", "issue-get", "PROJ-1"), lambda o: "Test issue" in o)
    check("jira issue-search", run_cmd(env, "jira", "issue-search", "project = PROJ"), lambda o: "PROJ-1" in o)
    check(
        "jira transition --to Done",
        run_cmd(env, "jira", "transition", "PROJ-1", "--to", "Done"),
        lambda o: True,
    )
    check("jira issue-delete", run_cmd(env, "jira", "issue-delete", "PROJ-1"), lambda o: True)
    check("jira attachment-list", run_cmd(env, "jira", "attachment-list", "PROJ-1"), lambda o: "x.txt" in o)

    tmp_file = os.path.join(HERE, "_smoke_upload.txt")
    with open(tmp_file, "w") as fh:
        fh.write("hello world")
    check(
        "jira attachment-add (multipart)",
        run_cmd(env, "jira", "attachment-add", "PROJ-1", tmp_file),
        lambda o: "_smoke_upload.txt" in o,
    )
    check(
        "confluence attachment-add (multipart)",
        run_cmd(env, "confluence", "attachment-add", "42", tmp_file),
        lambda o: "_smoke_upload.txt" in o,
    )
    os.remove(tmp_file)

    check("confluence page-get", run_cmd(env, "confluence", "page-get", "42"), lambda o: '"id": "42"' in o)
    check("confluence page-delete", run_cmd(env, "confluence", "page-delete", "42"), lambda o: True)

    r = run_cmd(env, "confluence", "macro-wrap", "info", "--plain-body", "note text")
    check(
        "confluence macro-wrap",
        r,
        lambda o: '<ac:structured-macro ac:name="info"' in o and "CDATA[note text]" in o,
    )

    bad_env = dict(env)
    bad_env["ATLASSIAN_API_TOKEN"] = ""
    r = run_cmd(bad_env, "jira", "issue-get", "PROJ-1")
    checks.append(
        (
            "missing token should fail",
            r.returncode != 0 and "ATLASSIAN_API_TOKEN" in r.stderr,
            r.returncode,
            r.stdout,
            r.stderr,
        )
    )

    # Config-file fallback: no env vars at all, credentials come only from
    # a config file written by `configure`.
    config_path = os.path.join(HERE, "_smoke_config.json")
    config_env = {k: v for k, v in os.environ.items() if not k.startswith("ATLASSIAN_")}
    config_env["ATLASSIAN_CLOUD_CONFIG"] = config_path

    r = run_cmd(
        config_env,
        "configure",
        "--site", f"http://127.0.0.1:{port}",
        "--email", "test@example.com",
        "--token", "faketoken",
    )
    checks.append(("configure writes config file", r.returncode == 0 and os.path.exists(config_path), r.returncode, r.stdout, r.stderr))

    r = run_cmd(config_env, "jira", "issue-get", "PROJ-1")
    checks.append(("config-file-only auth works", r.returncode == 0 and "Test issue" in r.stdout, r.returncode, r.stdout, r.stderr))

    if os.path.exists(config_path):
        os.remove(config_path)

    server.shutdown()

    failures = [c for c in checks if not c[1]]
    for name, ok, code, out, err in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failures:
        print(file=sys.stderr)
        for name, ok, code, out, err in failures:
            print(f"--- FAIL detail: {name} (exit={code}) ---\nstdout={out}\nstderr={err}", file=sys.stderr)
        sys.exit(1)
    print(f"\nAll {len(checks)} smoke tests passed.")


if __name__ == "__main__":
    main()
