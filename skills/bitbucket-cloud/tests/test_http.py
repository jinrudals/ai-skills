import contextlib
import io
import json
import tempfile
import unittest
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from support import bb, env, fake_urlopen

TOKEN = "SECRET123"


class HttpTests(unittest.TestCase):
    def call(self, responses, fn, *a, **kw):
        opener = fake_urlopen(responses)
        with env(BITBUCKET_EMAIL="a@b.c", BITBUCKET_API_TOKEN=TOKEN), mock.patch.object(
            bb, "_open", opener
        ):
            return opener, fn(*a, **kw)

    def test_request_sets_auth_and_json_headers(self):
        opener, res = self.call([(200, '{"ok": true}')], bb.request, "GET", "/user")
        method, url, headers, data = opener.calls[0]
        self.assertEqual((method, url), ("GET", "https://api.bitbucket.org/2.0/user"))
        self.assertTrue(headers["Authorization"].startswith("Basic "))
        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(res, {"ok": True})

    def test_request_dict_body_is_utf8_json(self):
        opener, _ = self.call(
            [(200, "{}")], bb.request, "POST", "/x", body={"t": "한글"}
        )
        _, _, headers, data = opener.calls[0]
        self.assertEqual(headers["Content-type"], "application/json")
        self.assertEqual(json.loads(data.decode("utf-8")), {"t": "한글"})

    def test_empty_response_returns_none(self):
        _, res = self.call([(204, "")], bb.request, "DELETE", "/x")
        self.assertIsNone(res)

    def test_raw_returns_text(self):
        _, res = self.call([(200, "diff 한글\n")], bb.request, "GET", "/x", raw=True)
        self.assertEqual(res, "diff 한글\n")

    def test_params_are_encoded(self):
        opener, _ = self.call(
            [(200, "{}")], bb.request, "GET", "/x", params={"q": 'name~"a b"'}
        )
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(opener.calls[0][1]).query)
        self.assertEqual(qs["q"], ['name~"a b"'])

    def test_paginate_follows_next(self):
        nxt = "https://api.bitbucket.org/2.0/repositories/w?page=2"
        pages = [
            (200, json.dumps({"values": [1, 2], "next": nxt})),
            (200, json.dumps({"values": [3, 4]})),
        ]
        opener, items = self.call(pages, bb.paginate, "/repositories/w", limit=100)
        self.assertEqual(items, [1, 2, 3, 4])
        self.assertEqual(opener.calls[1][1], nxt)

    def test_paginate_limit_smaller_than_page(self):
        page = (200, json.dumps({"values": [1, 2, 3, 4, 5], "next": "https://api.bitbucket.org/2.0/n"}))
        opener, items = self.call([page], bb.paginate, "/x", limit=2)
        self.assertEqual(items, [1, 2])
        self.assertEqual(len(opener.calls), 1)

    def test_paginate_pagelen_capped_at_50(self):
        opener, _ = self.call([(200, '{"values": []}')], bb.paginate, "/x", limit=100)
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(opener.calls[0][1]).query)
        self.assertEqual(qs["pagelen"], ["50"])

    def test_paginate_empty_returns_empty_list(self):
        _, items = self.call([(200, '{"values": []}')], bb.paginate, "/x")
        self.assertEqual(items, [])

    def test_paginate_next_on_other_host_rejected(self):
        page = (200, json.dumps({"values": [1], "next": "https://evil.example/n"}))
        with self.assertRaises(bb.ApiError):
            self.call([page], bb.paginate, "/x", limit=100)

    def test_error_json_message(self):
        with self.assertRaises(bb.ApiError) as cm:
            self.call([(404, '{"error":{"message":"nope"}}')], bb.request, "GET", "/x")
        self.assertEqual(cm.exception.status, 404)
        self.assertIn("nope", cm.exception.message)

    def test_error_non_json_body(self):
        for status, body in ((502, "<html>Bad Gateway</html>"), (500, "")):
            with self.assertRaises(bb.ApiError) as cm:
                self.call([(status, body)], bb.request, "GET", "/x")
            self.assertEqual(cm.exception.status, status)

    def test_token_not_in_error_message(self):
        body = json.dumps({"error": {"message": f"bad token {TOKEN}"}})
        with self.assertRaises(bb.ApiError) as cm:
            self.call([(401, body)], bb.request, "GET", "/x")
        self.assertNotIn(TOKEN, cm.exception.message)
        self.assertNotIn(TOKEN, str(cm.exception))

    def test_absolute_url_other_host_rejected(self):
        opener = fake_urlopen([(200, "{}")])
        with env(BITBUCKET_API_TOKEN=TOKEN), mock.patch.object(bb, "_open", opener):
            for url in ("https://evil.example/x", "http://api.bitbucket.org/2.0/x"):
                with self.assertRaises(bb.ApiError):
                    bb.request("GET", url)
        self.assertEqual(opener.calls, [])

    def test_redirect_drops_auth_on_other_host(self):
        handler = bb.SafeRedirectHandler()
        req = urllib.request.Request(
            "https://api.bitbucket.org/2.0/x", headers={"Authorization": "Bearer t"}
        )
        new = handler.redirect_request(
            req, None, 302, "Found", {}, "https://other.example/file"
        )
        self.assertNotIn("Authorization", dict(new.header_items()))
        same = handler.redirect_request(
            req, None, 302, "Found", {}, "https://api.bitbucket.org/2.0/y"
        )
        self.assertIn("Authorization", dict(same.header_items()))

    def test_redirect_drops_auth_on_http_downgrade(self):
        handler = bb.SafeRedirectHandler()
        req = urllib.request.Request(
            "https://api.bitbucket.org/2.0/x", headers={"Authorization": "******"}
        )
        new = handler.redirect_request(
            req, None, 302, "Found", {}, "http://api.bitbucket.org/2.0/y"
        )
        self.assertNotIn("Authorization", dict(new.header_items()))

    def test_quote_rejects_dot_segments(self):
        for bad in (".", ".."):
            with self.assertRaises(bb.ConfigError):
                bb.quote(bad)
        self.assertEqual(bb.quote("a..b"), "a..b")


class BodyAndOutputTests(unittest.TestCase):
    def test_read_body_strips_bom_and_reads_korean(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "b.txt"
            p.write_bytes("한글\r\n".encode("utf-8-sig"))
            args = SimpleNamespace(body=None, body_file=str(p))
            self.assertEqual(bb.read_body(args), "한글\r\n")

    def test_read_body_inline(self):
        self.assertEqual(bb.read_body(SimpleNamespace(body="x", body_file=None)), "x")

    def test_read_body_none(self):
        self.assertIsNone(bb.read_body(SimpleNamespace(body=None, body_file=None)))

    def test_read_body_stdin(self):
        args = SimpleNamespace(body=None, body_file="-")
        with mock.patch.object(bb.sys, "stdin", io.StringIO("한글 입력")):
            self.assertEqual(bb.read_body(args), "한글 입력")

    def test_emit_korean_on_cp949_stream(self):
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp949")
        with mock.patch.object(bb.sys, "stdout", stream):
            bb.setup_stdio()
            bb.emit({"t": "한글"})
            stream.flush()
        out = raw.getvalue().decode("utf-8")
        self.assertIn("한글", out)

    def test_emit_empty_list(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            bb.emit([])
        self.assertEqual(out.getvalue().strip(), "[]")

    def test_quote_branch_with_slash_and_korean(self):
        self.assertEqual(bb.quote("feature/한글 x"), "feature%2F%ED%95%9C%EA%B8%80%20x")

    def test_quote_path_keeps_slash(self):
        self.assertEqual(bb.quote_path("a b/한글.txt"), "a%20b/%ED%95%9C%EA%B8%80.txt")


if __name__ == "__main__":
    unittest.main()
