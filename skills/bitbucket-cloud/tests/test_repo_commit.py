import json
import unittest
import urllib.parse

from support import CliCase, bb

R = "https://api.bitbucket.org/2.0/repositories/ws/r"
EMPTY = (200, '{"values": []}')


def scopes_of(key):
    return {c.key: c.scopes for c in bb.COMMANDS}[key]


class RepoCommitTests(CliCase):
    def get(self, argv, response=EMPTY):
        code, out, err, opener = self.run_main(argv, [response])
        self.assertEqual(code, 0, err)
        return out, opener.calls[0]

    def test_repo_list(self):
        out, call = self.get(["repo", "list"])
        self.assertEqual((call[0], call[1].split("?")[0]), ("GET", "https://api.bitbucket.org/2.0/repositories/ws"))
        self.assertEqual(json.loads(out), [])
        self.assertEqual(scopes_of("repo list"), ("read:repository:bitbucket",))

    def test_repo_get(self):
        _, call = self.get(["repo", "get", "r"], (200, "{}"))
        self.assertEqual((call[0], call[1]), ("GET", R))

    def test_repo_branches_and_query(self):
        _, call = self.get(["repo", "branches", "r"])
        self.assertTrue(call[1].startswith(R + "/refs/branches"))
        _, call = self.get(["repo", "branches", "r", "--query", 'fe"at'])
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(call[1]).query)
        self.assertEqual(qs["q"], ['name~"fe\\"at"'])

    def test_repo_tags(self):
        _, call = self.get(["repo", "tags", "r"])
        self.assertTrue(call[1].startswith(R + "/refs/tags"))

    def test_branch_create_body(self):
        code, _, _, opener = self.run_main(
            ["repo", "branch-create", "r", "feature/한글", "--from", "abc123"], [(201, "{}")]
        )
        self.assertEqual(code, 0)
        self.assertEqual((opener.calls[0][0], opener.calls[0][1]), ("POST", R + "/refs/branches"))
        self.assertEqual(
            self.sent_json(opener), {"name": "feature/한글", "target": {"hash": "abc123"}}
        )
        self.assertEqual(
            scopes_of("repo branch-create"),
            ("write:repository:bitbucket", "read:repository:bitbucket"),
        )

    def test_branch_create_requires_from(self):
        code, *_ = self.run_main(["repo", "branch-create", "r", "x"])
        self.assertEqual(code, 2)

    def test_commit_list_default_and_revision(self):
        _, call = self.get(["commit", "list", "r"])
        self.assertTrue(call[1].startswith(R + "/commits?"))
        _, call = self.get(["commit", "list", "r", "--revision", "feature/한글"])
        self.assertTrue(call[1].startswith(R + "/commits/feature%2F%ED%95%9C%EA%B8%80?"))

    def test_commit_get(self):
        _, call = self.get(["commit", "get", "r", "abc"], (200, "{}"))
        self.assertEqual(call[1], R + "/commit/abc")

    def test_commit_diff_returns_raw_text(self):
        out, call = self.get(["commit", "diff", "r", "a..b"], (200, "diff --git 한글\n"))
        self.assertEqual(call[1], R + "/diff/a..b")
        self.assertEqual(out, "diff --git 한글\n")

    def test_commit_diff_spec_quoted(self):
        _, call = self.get(["commit", "diff", "r", "feature/x..main"], (200, ""))
        self.assertEqual(call[1], R + "/diff/feature%2Fx..main")

    def test_commit_file_path_and_ref_quoted(self):
        out, call = self.get(
            ["commit", "file", "r", "a/b c/한글.txt", "--ref", "feature/한글"],
            (200, "내용\n"),
        )
        self.assertEqual(
            call[1],
            R + "/src/feature%2F%ED%95%9C%EA%B8%80/a/b%20c/%ED%95%9C%EA%B8%80.txt",
        )
        self.assertEqual(out, "내용\n")

    def test_commit_file_requires_ref(self):
        code, *_ = self.run_main(["commit", "file", "r", "a.txt"])
        self.assertEqual(code, 2)

    def test_empty_repo_list_prints_empty_array(self):
        out, _ = self.get(["repo", "list"])
        self.assertEqual(out.strip(), "[]")

    def test_all_rows_registered_with_read_scope(self):
        for key in ("repo get", "repo branches", "repo tags", "commit list",
                    "commit get", "commit diff", "commit file"):
            self.assertIn("read:repository:bitbucket", scopes_of(key), key)


if __name__ == "__main__":
    unittest.main()
