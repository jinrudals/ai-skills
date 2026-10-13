import re
import unittest
from pathlib import Path

from support import bb

SKILL = Path(__file__).resolve().parents[1]
SKILL_MD = (SKILL / "SKILL.md").read_text(encoding="utf-8") if (SKILL / "SKILL.md").exists() else ""
SETUP_MD = (
    (SKILL / "references" / "setup.md").read_text(encoding="utf-8")
    if (SKILL / "references" / "setup.md").exists() else ""
)


class DocsTests(unittest.TestCase):
    def test_setup_md_lists_every_scope_used_by_commands(self):
        used = {s for c in bb.COMMANDS for s in c.scopes}
        missing = sorted(s for s in used if s not in SETUP_MD)
        self.assertEqual(missing, [])

    def test_setup_md_lists_each_preset_scope(self):
        for name, scopes in bb.PRESETS.items():
            for scope in scopes:
                self.assertIn(scope, SETUP_MD, f"{name}: {scope}")

    def test_admin_preset_covers_every_command_scope(self):
        used = {s for c in bb.COMMANDS for s in c.scopes}
        self.assertEqual(sorted(used - set(bb.PRESETS["admin"])), [])

    def test_skill_md_front_matter(self):
        self.assertTrue(SKILL_MD.startswith("---"))
        head = SKILL_MD.split("---")[1]
        self.assertIn("name: bitbucket-cloud", head)
        desc = head[head.index("description:"):]
        for word in ("Bitbucket", "pull request", "pipeline", "비트버킷"):
            self.assertIn(word, desc)

    def test_skill_md_mentions_every_area(self):
        for area in {c.area for c in bb.COMMANDS}:
            self.assertRegex(SKILL_MD, rf"\b{re.escape(area)}\b", area)

    def test_branch_query_example_is_a_plain_name_fragment(self):
        self.assertNotIn("--query 'name", SKILL_MD)

    def test_reference_files_exist(self):
        for rel in ("references/api-notes.md", "examples/smoke_test.py"):
            self.assertTrue((SKILL / rel).exists(), rel)


if __name__ == "__main__":
    unittest.main()
