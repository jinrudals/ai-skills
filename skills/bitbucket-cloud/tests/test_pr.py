import json
import os
import tempfile
import unittest
from pathlib import Path

from support import CliCase, bb

PR = "https://api.bitbucket.org/2.0/repositories/ws/r/pullrequests"
EMPTY = (200, '{"values": []}')
READ = "read:pullrequest:bitbucket"
WRITE = "write:pullrequest:bitbucket"


def scopes_of(key):
    return {c.key: c.scopes for c in bb.COMMANDS}[key]


class PrTests(CliCase):
    def send(self, argv, response=(200, "{}")):
        code, out, err, opener = self.run_main(argv, [response])
        self.assertEqual(code, 0, err)
        return out, opener

    def test_pr_list_default_state_open(self):
        out, opener = self.send(["pr", "list", "r"], EMPTY)
        method, url, *_ = opener.calls[0]
        self.assertEqual(method, "GET")
        self.assertTrue(url.startswith(PR + "?"))
        self.assertIn("state=OPEN", url)
        self.assertEqual(json.loads(out), [])

    def test_pr_list_state_choice(self):
        _, opener = self.send(["pr", "list", "r", "--state", "MERGED"], EMPTY)
        self.assertIn("state=MERGED", opener.calls[0][1])
        code, *_ = self.run_main(["pr", "list", "r", "--state", "BOGUS"])
        self.assertEqual(code, 2)

    def test_pr_get(self):
        _, opener = self.send(["pr", "get", "r", "7"])
        self.assertEqual((opener.calls[0][0], opener.calls[0][1]), ("GET", PR + "/7"))

    def test_pr_create_body_full(self):
        _, opener = self.send(
            ["pr", "create", "r", "--title", "T 한글", "--source", "feature/x",
             "--dest", "main", "--description", "desc", "--reviewer", "{u1}",
             "--reviewer", "{u2}", "--close-source-branch"],
            (201, "{}"),
        )
        self.assertEqual((opener.calls[0][0], opener.calls[0][1]), ("POST", PR))
        self.assertEqual(
            self.sent_json(opener),
            {
                "title": "T 한글",
                "source": {"branch": {"name": "feature/x"}},
                "destination": {"branch": {"name": "main"}},
                "description": "desc",
                "reviewers": [{"uuid": "{u1}"}, {"uuid": "{u2}"}],
                "close_source_branch": True,
            },
        )

    def test_pr_create_omits_dest_when_not_given(self):
        _, opener = self.send(
            ["pr", "create", "r", "--title", "T", "--source", "b"], (201, "{}")
        )
        body = self.sent_json(opener)
        self.assertNotIn("destination", body)
        self.assertNotIn("description", body)
        self.assertEqual(body["reviewers"], [])
        self.assertFalse(body["close_source_branch"])

    def test_pr_update_sends_only_given_fields(self):
        _, opener = self.send(["pr", "update", "r", "7", "--title", "New"])
        self.assertEqual((opener.calls[0][0], opener.calls[0][1]), ("PUT", PR + "/7"))
        self.assertEqual(self.sent_json(opener), {"title": "New"})

    def test_pr_update_dest_and_description(self):
        _, opener = self.send(
            ["pr", "update", "r", "7", "--dest", "dev", "--description", "d"]
        )
        self.assertEqual(
            self.sent_json(opener),
            {"destination": {"branch": {"name": "dev"}}, "description": "d"},
        )

    def test_pr_update_with_nothing_is_usage_error(self):
        code, _, err, opener = self.run_main(["pr", "update", "r", "7"])
        self.assertEqual(code, 2)
        self.assertEqual(opener.calls, [])

    def test_pr_diff_returns_raw_text(self):
        out, opener = self.send(["pr", "diff", "r", "7"], (200, "diff 한글\n"))
        self.assertEqual(opener.calls[0][1], PR + "/7/diff")
        self.assertEqual(out, "diff 한글\n")

    def test_pr_comments_list(self):
        out, opener = self.send(["pr", "comments", "r", "7"], EMPTY)
        self.assertTrue(opener.calls[0][1].startswith(PR + "/7/comments"))
        self.assertEqual(json.loads(out), [])

    def test_comment_add_body_and_parent(self):
        _, opener = self.send(
            ["pr", "comment-add", "r", "7", "--body", "hi 한글", "--parent", "42"],
            (201, "{}"),
        )
        self.assertEqual((opener.calls[0][0], opener.calls[0][1]), ("POST", PR + "/7/comments"))
        self.assertEqual(
            self.sent_json(opener), {"content": {"raw": "hi 한글"}, "parent": {"id": 42}}
        )

    def test_comment_add_requires_body(self):
        code, _, _, opener = self.run_main(["pr", "comment-add", "r", "7"])
        self.assertEqual(code, 2)
        self.assertEqual(opener.calls, [])

    def test_comment_body_from_file_with_bom_and_crlf(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.md"
            p.write_bytes("첫 줄\r\n둘째 줄\r\n".encode("utf-8-sig"))
            _, opener = self.send(
                ["pr", "comment-add", "r", "7", "--body-file", str(p)], (201, "{}")
            )
        raw = opener.calls[0][3]
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(
            json.loads(raw.decode("utf-8"))["content"]["raw"], "첫 줄\r\n둘째 줄\r\n"
        )

    def test_comment_body_korean_roundtrip_bytes(self):
        _, opener = self.send(
            ["pr", "comment-add", "r", "7", "--body", "한글"], (201, "{}")
        )
        self.assertIn("한글".encode("utf-8"), opener.calls[0][3])

    def test_approve_unapprove_request_changes(self):
        for argv, method, suffix in (
            (["pr", "approve", "r", "7"], "POST", "/7/approve"),
            (["pr", "unapprove", "r", "7"], "DELETE", "/7/approve"),
            (["pr", "request-changes", "r", "7"], "POST", "/7/request-changes"),
        ):
            out, opener = self.send(argv, (204, ""))
            self.assertEqual((opener.calls[0][0], opener.calls[0][1]), (method, PR + suffix))
            self.assertEqual(json.loads(out), {"ok": True})

    def test_merge_requires_yes(self):
        code, out, err, opener = self.run_main(["pr", "merge", "r", "7"])
        self.assertEqual(code, 5)
        self.assertEqual(opener.calls, [])
        self.assertTrue(json.loads(out)["dry_run"])

    def test_merge_with_yes_posts_to_merge_endpoint(self):
        _, opener = self.send(
            ["pr", "merge", "r", "7", "--yes", "--strategy", "squash",
             "--message", "msg", "--close-source-branch"]
        )
        self.assertEqual((opener.calls[0][0], opener.calls[0][1]), ("POST", PR + "/7/merge"))
        self.assertEqual(
            self.sent_json(opener),
            {"type": "pullrequest_merge_parameters", "merge_strategy": "squash",
             "message": "msg", "close_source_branch": True},
        )

    def test_merge_minimal_body(self):
        _, opener = self.send(["pr", "merge", "r", "7", "--yes"])
        self.assertEqual(self.sent_json(opener), {"type": "pullrequest_merge_parameters"})

    def test_merge_strategy_choices(self):
        code, *_ = self.run_main(["pr", "merge", "r", "7", "--yes", "--strategy", "nope"])
        self.assertEqual(code, 2)

    def test_decline_requires_yes(self):
        code, _, _, opener = self.run_main(["pr", "decline", "r", "7", "--reason", "x"])
        self.assertEqual(code, 5)
        self.assertEqual(opener.calls, [])

    def test_decline_with_yes(self):
        _, opener = self.send(["pr", "decline", "r", "7", "--yes", "--reason", "dup"])
        self.assertEqual((opener.calls[0][0], opener.calls[0][1]), ("POST", PR + "/7/decline"))
        self.assertEqual(self.sent_json(opener), {"reason": "dup"})

    def test_scopes_match_api_reference(self):
        read_only = ("list", "get", "diff", "comments", "comment-add")
        for a in read_only:
            self.assertEqual(scopes_of(f"pr {a}"), (READ,), a)
        for a in ("create", "update", "approve", "request-changes", "merge", "decline"):
            self.assertEqual(scopes_of(f"pr {a}"), (READ, WRITE), a)
        self.assertEqual(scopes_of("pr unapprove"), (WRITE,))


class TaskTests(CliCase):
    def send(self, argv, response=(200, "{}")):
        code, out, err, opener = self.run_main(argv, [response])
        self.assertEqual(code, 0, err)
        return out, opener

    def test_task_list(self):
        out, opener = self.send(["task", "list", "r", "7"], EMPTY)
        self.assertTrue(opener.calls[0][1].startswith(PR + "/7/tasks"))
        self.assertEqual(json.loads(out), [])

    def test_task_add(self):
        _, opener = self.send(
            ["task", "add", "r", "7", "--body", "do it", "--comment", "9"], (201, "{}")
        )
        self.assertEqual((opener.calls[0][0], opener.calls[0][1]), ("POST", PR + "/7/tasks"))
        self.assertEqual(
            self.sent_json(opener), {"content": {"raw": "do it"}, "comment": {"id": 9}}
        )

    def test_task_add_requires_body(self):
        code, *_ = self.run_main(["task", "add", "r", "7"])
        self.assertEqual(code, 2)

    def test_task_update_only_given_fields(self):
        _, opener = self.send(["task", "update", "r", "7", "3", "--state", "RESOLVED"])
        self.assertEqual((opener.calls[0][0], opener.calls[0][1]), ("PUT", PR + "/7/tasks/3"))
        self.assertEqual(self.sent_json(opener), {"state": "RESOLVED"})
        _, opener = self.send(["task", "update", "r", "7", "3", "--body", "new"])
        self.assertEqual(self.sent_json(opener), {"content": {"raw": "new"}})

    def test_task_update_with_nothing_is_usage_error(self):
        code, *_ = self.run_main(["task", "update", "r", "7", "3"])
        self.assertEqual(code, 2)

    def test_task_delete_gated(self):
        code, _, _, opener = self.run_main(["task", "delete", "r", "7", "3"])
        self.assertEqual((code, opener.calls), (5, []))
        out, opener = self.send(["task", "delete", "r", "7", "3", "--yes"], (204, ""))
        self.assertEqual((opener.calls[0][0], opener.calls[0][1]), ("DELETE", PR + "/7/tasks/3"))

    def test_task_scopes(self):
        for a in ("list", "add", "update", "delete"):
            self.assertEqual(scopes_of(f"task {a}"), (READ,), a)


if __name__ == "__main__":
    unittest.main()
