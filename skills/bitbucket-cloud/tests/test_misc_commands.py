import json
import unittest
from urllib.parse import unquote

from support import CliCase, bb

R = "https://api.bitbucket.org/2.0/repositories/ws/r"
EMPTY = (200, '{"values": []}')


def scopes_of(key):
    return {c.key: c.scopes for c in bb.COMMANDS}[key]


class MiscTests(CliCase):
    def send(self, argv, response=(200, "{}"), **env):
        code, out, err, opener = self.run_main(argv, [response], **env)
        self.assertEqual(code, 0, err)
        return out, opener

    def gated(self, argv):
        code, out, err, opener = self.run_main(argv, [(200, "{}")])
        self.assertEqual(code, 5)
        self.assertEqual(opener.calls, [])

    def test_pipeline_list(self):
        _, opener = self.send(["pipeline", "list", "r"], EMPTY)
        method, url, *_ = opener.calls[0]
        self.assertEqual(method, "GET")
        self.assertTrue(url.startswith(R + "/pipelines/?"))
        self.assertIn("sort=-created_on", unquote(url))

    def test_pipeline_get(self):
        _, opener = self.send(["pipeline", "get", "r", "{abc}"])
        self.assertEqual(opener.calls[0][1], R + "/pipelines/%7Babc%7D")

    def test_pipeline_trigger_gated(self):
        self.gated(["pipeline", "trigger", "r", "--branch", "main"])

    def test_pipeline_trigger_body(self):
        _, opener = self.send(
            ["pipeline", "trigger", "r", "--branch", "main", "--pattern", "deploy",
             "--var", "A=1", "--var", "B=x=y", "--yes"]
        )
        self.assertEqual((opener.calls[0][0], opener.calls[0][1]), ("POST", R + "/pipelines/"))
        self.assertEqual(
            self.sent_json(opener),
            {
                "target": {
                    "type": "pipeline_ref_target", "ref_type": "branch", "ref_name": "main",
                    "selector": {"type": "custom", "pattern": "deploy"},
                },
                "variables": [{"key": "A", "value": "1"}, {"key": "B", "value": "x=y"}],
            },
        )

    def test_pipeline_trigger_minimal_body(self):
        _, opener = self.send(["pipeline", "trigger", "r", "--branch", "main", "--yes"])
        self.assertEqual(
            self.sent_json(opener),
            {"target": {"type": "pipeline_ref_target", "ref_type": "branch", "ref_name": "main"}},
        )

    def test_trigger_var_without_equals_is_usage_error(self):
        code, *_ = self.run_main(
            ["pipeline", "trigger", "r", "--branch", "m", "--var", "NOEQ", "--yes"]
        )
        self.assertEqual(code, 2)

    def test_pipeline_stop_gated(self):
        self.gated(["pipeline", "stop", "r", "{u}"])

    def test_pipeline_stop(self):
        _, opener = self.send(["pipeline", "stop", "r", "{u}", "--yes"])
        self.assertEqual(
            (opener.calls[0][0], opener.calls[0][1]),
            ("POST", R + "/pipelines/%7Bu%7D/stopPipeline"),
        )

    def test_pipeline_log_without_step_lists_steps(self):
        _, opener = self.send(["pipeline", "log", "r", "{u}"], EMPTY)
        self.assertTrue(opener.calls[0][1].startswith(R + "/pipelines/%7Bu%7D/steps/"))

    def test_pipeline_log_returns_raw_text(self):
        out, opener = self.send(
            ["pipeline", "log", "r", "{u}", "--step", "{s}"], (200, "빌드 시작\nnot json")
        )
        self.assertEqual(opener.calls[0][1], R + "/pipelines/%7Bu%7D/steps/%7Bs%7D/log")
        self.assertIn("빌드 시작", out)
        self.assertIn("not json", out)

    def test_webhook_list_and_create(self):
        _, opener = self.send(["webhook", "list", "r"], EMPTY)
        self.assertTrue(opener.calls[0][1].startswith(R + "/hooks"))
        _, opener = self.send(
            ["webhook", "create", "r", "--url", "https://x.example/h", "--event", "repo:push",
             "--event", "pullrequest:created", "--description", "d"],
            (201, "{}"),
        )
        self.assertEqual((opener.calls[0][0], opener.calls[0][1]), ("POST", R + "/hooks"))
        self.assertEqual(
            self.sent_json(opener),
            {"description": "d", "url": "https://x.example/h", "active": True,
             "events": ["repo:push", "pullrequest:created"]},
        )

    def test_webhook_delete_gated(self):
        self.gated(["webhook", "delete", "r", "{h}"])
        _, opener = self.send(["webhook", "delete", "r", "{h}", "--yes"], (204, ""))
        self.assertEqual(
            (opener.calls[0][0], opener.calls[0][1]), ("DELETE", R + "/hooks/%7Bh%7D")
        )

    def test_perm_list_combines_users_and_groups(self):
        code, out, err, opener = self.run_main(
            ["perm", "list", "r"],
            [(200, '{"values": [{"permission": "read"}]}'),
             (200, '{"values": [{"permission": "write"}]}')],
        )
        self.assertEqual(code, 0, err)
        urls = [c[1] for c in opener.calls]
        self.assertTrue(urls[0].startswith(R + "/permissions-config/users"))
        self.assertTrue(urls[1].startswith(R + "/permissions-config/groups"))
        self.assertEqual(
            json.loads(out),
            {"users": [{"permission": "read"}], "groups": [{"permission": "write"}]},
        )

    def test_perm_set_gated_and_body(self):
        self.gated(["perm", "set", "r", "--user", "acc1", "--permission", "read"])
        _, opener = self.send(
            ["perm", "set", "r", "--user", "acc1", "--permission", "write", "--yes"]
        )
        self.assertEqual(
            (opener.calls[0][0], opener.calls[0][1]),
            ("PUT", R + "/permissions-config/users/acc1"),
        )
        self.assertEqual(self.sent_json(opener), {"permission": "write"})
        _, opener = self.send(
            ["perm", "set", "r", "--group", "devs", "--permission", "admin", "--yes"]
        )
        self.assertEqual(opener.calls[0][1], R + "/permissions-config/groups/devs")

    def test_perm_remove_gated(self):
        self.gated(["perm", "remove", "r", "--group", "devs"])
        _, opener = self.send(["perm", "remove", "r", "--group", "devs", "--yes"], (204, ""))
        self.assertEqual(
            (opener.calls[0][0], opener.calls[0][1]),
            ("DELETE", R + "/permissions-config/groups/devs"),
        )

    def test_perm_requires_exactly_one_of_user_or_group(self):
        for extra in ([], ["--user", "a", "--group", "g"]):
            code, *_ = self.run_main(
                ["perm", "remove", "r", "--yes"] + extra, [(200, "{}")]
            )
            self.assertEqual(code, 2)

    def test_issue_commands(self):
        _, opener = self.send(["issue", "list", "r"], EMPTY)
        self.assertTrue(opener.calls[0][1].startswith(R + "/issues"))
        _, opener = self.send(["issue", "get", "r", "5"])
        self.assertEqual(opener.calls[0][1], R + "/issues/5")
        _, opener = self.send(
            ["issue", "create", "r", "--title", "버그", "--body", "b", "--kind", "bug",
             "--priority", "major"],
            (201, "{}"),
        )
        self.assertEqual((opener.calls[0][0], opener.calls[0][1]), ("POST", R + "/issues"))
        self.assertEqual(
            self.sent_json(opener),
            {"title": "버그", "content": {"raw": "b"}, "kind": "bug", "priority": "major"},
        )
        _, opener = self.send(["issue", "create", "r", "--title", "t"], (201, "{}"))
        self.assertEqual(self.sent_json(opener), {"title": "t"})

    def test_issue_update_and_comment(self):
        _, opener = self.send(["issue", "update", "r", "5", "--state", "resolved"])
        self.assertEqual((opener.calls[0][0], opener.calls[0][1]), ("PUT", R + "/issues/5"))
        self.assertEqual(self.sent_json(opener), {"state": "resolved"})
        code, *_ = self.run_main(["issue", "update", "r", "5"])
        self.assertEqual(code, 2)
        _, opener = self.send(["issue", "comment", "r", "5", "--body", "hi"], (201, "{}"))
        self.assertEqual(opener.calls[0][1], R + "/issues/5/comments")
        self.assertEqual(self.sent_json(opener), {"content": {"raw": "hi"}})
        code, *_ = self.run_main(["issue", "comment", "r", "5"])
        self.assertEqual(code, 2)

    def test_scopes_follow_api_reference(self):
        w = lambda *n: tuple(f"{x}:bitbucket" for x in n)
        self.assertEqual(scopes_of("pipeline stop"), w("write:pipeline"))
        self.assertEqual(scopes_of("pipeline trigger"), w("read:pipeline", "write:pipeline"))
        self.assertEqual(scopes_of("webhook delete"), w("delete:webhook"))
        self.assertEqual(scopes_of("perm list"), w("read:repository"))
        self.assertEqual(scopes_of("perm set"), w("admin:repository", "write:permission"))
        self.assertEqual(scopes_of("perm remove"), w("admin:repository", "delete:permission"))


if __name__ == "__main__":
    unittest.main()
