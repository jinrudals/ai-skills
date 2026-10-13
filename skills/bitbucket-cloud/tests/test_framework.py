import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import bb, env, fake_urlopen

TOKEN = "SECRET123"
META_AREAS = {"api", "configure", "scopes", "check"}


class FrameworkTests(unittest.TestCase):
    def setUp(self):
        self._saved = list(bb.COMMANDS)
        self.addCleanup(self._restore)
        bb.register(
            bb.Cmd(
                area="demo",
                action="remove",
                method="DELETE",
                path="/repositories/{ws}/{repo}/things/{id}",
                scopes=("write:repository:bitbucket",),
                destructive=True,
            )
        )
        bb.register(
            bb.Cmd(
                area="demo",
                action="list",
                method="GET",
                path="/repositories/{ws}/{repo}/things",
                scopes=("read:repository:bitbucket",),
                list_result=True,
            )
        )
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = str(Path(self.tmp.name) / "credentials.json")

    def _restore(self):
        bb.COMMANDS[:] = self._saved

    def run_main(self, argv, responses=(), **envvars):
        opener = fake_urlopen(list(responses))
        out, err = io.StringIO(), io.StringIO()
        base = dict(
            BITBUCKET_EMAIL="a@b.c",
            BITBUCKET_API_TOKEN=TOKEN,
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

    def test_destructive_without_yes_prints_dry_run_and_exits_5(self):
        code, out, _, opener = self.run_main(["demo", "remove", "r", "7"])
        self.assertEqual(code, 5)
        self.assertEqual(opener.calls, [])
        data = json.loads(out)
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["method"], "DELETE")
        self.assertEqual(data["url"], "https://api.bitbucket.org/2.0/repositories/ws/r/things/7")

    def test_dry_run_has_no_credentials(self):
        _, out, err, _ = self.run_main(["demo", "remove", "r", "7"])
        self.assertNotIn(TOKEN, out + err)
        self.assertNotIn("Basic", out + err)

    def test_destructive_with_yes_sends_request(self):
        code, out, _, opener = self.run_main(["demo", "remove", "r", "7", "--yes"], [(204, "")])
        self.assertEqual(code, 0)
        self.assertEqual(opener.calls[0][0], "DELETE")
        self.assertEqual(json.loads(out), {"ok": True})

    def test_list_honours_limit_and_prints_empty_array(self):
        code, out, _, _ = self.run_main(["demo", "list", "r"], [(200, '{"values": []}')])
        self.assertEqual((code, json.loads(out)), (0, []))
        code, out, _, opener = self.run_main(
            ["demo", "list", "r", "--limit", "2"], [(200, '{"values": [1,2,3]}')]
        )
        self.assertEqual(json.loads(out), [1, 2])

    def test_api_non_get_requires_yes(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            code, out, err, opener = self.run_main(["api", method, "/repositories/ws/r"])
            self.assertEqual(code, 5, method)
            self.assertEqual(opener.calls, [])
            self.assertNotIn(TOKEN, out + err)

    def test_api_get_does_not_require_yes(self):
        code, out, _, opener = self.run_main(["api", "GET", "/user"], [(200, '{"a": 1}')])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"a": 1})

    def test_api_post_with_yes_sends_body(self):
        code, _, _, opener = self.run_main(
            ["api", "POST", "/x", "--body", '{"k": "한글"}', "--yes"], [(200, "{}")]
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(opener.calls[0][3].decode("utf-8")), {"k": "한글"})

    def test_403_returns_3_and_prints_scope_hint(self):
        code, _, err, _ = self.run_main(
            ["demo", "remove", "r", "7", "--yes"], [(403, '{"error":{"message":"no"}}')]
        )
        self.assertEqual(code, 3)
        self.assertIn("write:repository:bitbucket", err)
        self.assertNotIn(TOKEN, err)

    def test_401_returns_3(self):
        code, _, err, _ = self.run_main(["demo", "list", "r"], [(401, "{}")])
        self.assertEqual(code, 3)
        self.assertIn("token", err.lower())

    def test_other_api_error_returns_4(self):
        code, _, err, _ = self.run_main(["demo", "list", "r"], [(404, '{"error":{"message":"gone"}}')])
        self.assertEqual(code, 4)
        self.assertIn("gone", err)

    def test_missing_config_returns_2_with_setup_hint(self):
        code, _, err, opener = self.run_main(
            ["demo", "list", "r"], BITBUCKET_API_TOKEN=""
        )
        self.assertEqual(code, 2)
        self.assertIn("configure", err)
        self.assertEqual(opener.calls, [])

    def test_missing_workspace_returns_2(self):
        code, _, err, _ = self.run_main(["demo", "list", "r"], BITBUCKET_WORKSPACE="")
        self.assertEqual(code, 2)
        self.assertIn("workspace", err)

    def test_workspace_flag_overrides_config(self):
        _, _, _, opener = self.run_main(
            ["demo", "list", "r", "--workspace", "other"], [(200, '{"values": []}')]
        )
        self.assertIn("/repositories/other/r/things", opener.calls[0][1])

    def test_path_values_are_quoted(self):
        _, _, _, opener = self.run_main(
            ["demo", "remove", "r", "a/b 한", "--yes"], [(204, "")]
        )
        self.assertTrue(opener.calls[0][1].endswith("/things/a%2Fb%20%ED%95%9C"))

    def test_scopes_command_lists_every_registered_command(self):
        code, out, _, _ = self.run_main(["scopes"])
        keys = {row["command"] for row in json.loads(out)}
        self.assertEqual(code, 0)
        self.assertIn("demo remove", keys)
        self.assertIn("demo list", keys)

    def test_scopes_preset_prints_scope_list(self):
        code, out, _, _ = self.run_main(["scopes", "--preset", "dev"])
        data = json.loads(out)
        self.assertEqual(data["preset"], "dev")
        self.assertIn("write:pullrequest:bitbucket", data["scopes"])

    def test_check_reports_ok(self):
        code, out, _, opener = self.run_main(
            ["check"], [(200, '{"display_name": "x"}'), (200, '{"slug": "ws"}')]
        )
        self.assertEqual(code, 0)
        self.assertEqual([c[1].rsplit("/", 1)[-1] for c in opener.calls], ["user", "ws"])
        self.assertTrue(all(r["ok"] for r in json.loads(out)))

    def test_check_reports_scope_hint_on_403(self):
        code, out, _, _ = self.run_main(
            ["check"], [(200, "{}"), (403, '{"error":{"message":"no"}}')]
        )
        self.assertEqual(code, 3)
        rows = json.loads(out)
        self.assertFalse(rows[1]["ok"])
        self.assertIn("read:workspace:bitbucket", rows[1]["hint"])


class RegistryTests(unittest.TestCase):
    def test_presets_only_use_known_scopes(self):
        for name, scopes in bb.PRESETS.items():
            for s in scopes:
                self.assertIn(s, bb.KNOWN_SCOPES, f"{name}: {s}")

    def test_dev_preset_pairs_write_with_read(self):
        dev = set(bb.PRESETS["dev"])
        for s in dev:
            if s.startswith("write:"):
                self.assertIn("read:" + s[len("write:"):], dev, s)

    def test_presets_are_nested(self):
        self.assertLessEqual(set(bb.PRESETS["read-only"]), set(bb.PRESETS["dev"]))
        self.assertLessEqual(set(bb.PRESETS["dev"]), set(bb.PRESETS["admin"]))

    def test_every_command_scope_is_known(self):
        for cmd in bb.COMMANDS:
            for s in cmd.scopes:
                self.assertIn(s, bb.KNOWN_SCOPES, f"{cmd.area} {cmd.action}: {s}")

    def test_every_cmd_has_scopes_unless_meta(self):
        for cmd in bb.COMMANDS:
            if cmd.area not in META_AREAS:
                self.assertTrue(cmd.scopes, f"{cmd.area} {cmd.action} has no scopes")

    def test_destructive_commands_are_not_plain_gets(self):
        for cmd in bb.COMMANDS:
            if cmd.destructive:
                self.assertNotEqual(cmd.method, "GET")


if __name__ == "__main__":
    unittest.main()
