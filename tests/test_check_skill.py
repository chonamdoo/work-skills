import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "work-to-skill" / "scripts" / "check_skill.py"
spec = importlib.util.spec_from_file_location("check_skill", SCRIPT)
check_skill = importlib.util.module_from_spec(spec)
_write_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # keep the skill folder free of __pycache__
spec.loader.exec_module(check_skill)
sys.dont_write_bytecode = _write_bytecode


def make_skill(root, folder, frontmatter, body="# Skill\n\nApply the rules.\n", files=None):
    skill = Path(root) / folder
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n{body}", encoding="utf-8")
    for rel, text in (files or {}).items():
        path = skill / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return skill


class CheckSkillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_check(self, skill, host="generic"):
        return check_skill.check(skill, host)

    def test_distributed_skill_passes_every_host(self):
        for host in ("generic", "anthropic"):
            errors, _ = self.run_check(ROOT / "skills" / "work-to-skill", host)
            self.assertEqual(errors, [], host)

    def test_optional_specification_fields_are_preserved_not_rejected(self):
        skill = make_skill(
            self.tmp.name,
            "payments-review",
            "name: payments-review\n"
            "description: >\n  Reviews payments changes against team rules.\n  Use when reviewing payments PRs.\n"
            "license: MIT\nallowed-tools: Read Grep\nmetadata:\n  owner: payments\n  version: \"2\"",
        )
        for host in ("generic", "anthropic"):
            self.assertEqual(self.run_check(skill, host), ([], []), host)

    def test_reserved_words_fail_only_for_anthropic_hosts(self):
        skill = make_skill(self.tmp.name, "claude-api-review", "name: claude-api-review\ndescription: Reviews API calls.")
        self.assertEqual(self.run_check(skill, "generic")[0], [])
        errors = self.run_check(skill, "anthropic")[0]
        self.assertEqual(len(errors), 1)
        self.assertIn("claude", errors[0])

    def test_xml_tags_fail_only_for_anthropic_hosts_and_comparisons_do_not(self):
        tagged = make_skill(self.tmp.name, "tagged", "name: tagged\ndescription: Use for <system> prompts.")
        compare = make_skill(self.tmp.name, "compare", "name: compare\ndescription: Flags amounts where a < b or b > c.")
        self.assertEqual(self.run_check(tagged, "generic")[0], [])
        self.assertTrue(self.run_check(tagged, "anthropic")[0])
        self.assertEqual(self.run_check(compare, "anthropic")[0], [])

    def test_body_length_is_advice_not_failure(self):
        skill = make_skill(self.tmp.name, "long", "name: long\ndescription: Long reference.", body="line\n" * 600)
        errors, warnings = self.run_check(skill)
        self.assertEqual(errors, [])
        self.assertTrue(any("500" in w for w in warnings))

    def test_invalid_names_are_rejected(self):
        cases = {
            "mismatch": ("folder-a", "name: folder-b"),
            "upper": ("Upper", "name: Upper"),
            "double-hyphen": ("a--b", "name: a--b"),
            "edge-hyphen": ("-a", "name: -a"),
            "too-long": ("a" * 65, "name: " + "a" * 65),
            "missing": ("unnamed", "title: unnamed"),
        }
        for label, (folder, line) in cases.items():
            with self.subTest(label):
                skill = make_skill(self.tmp.name, folder, line + "\ndescription: Does a thing.")
                self.assertTrue(self.run_check(skill)[0])

    def test_description_must_exist_and_fit(self):
        empty = make_skill(self.tmp.name, "empty", "name: empty\ndescription: \"\"")
        long = make_skill(self.tmp.name, "long-desc", "name: long-desc\ndescription: " + "x" * 1025)
        self.assertTrue(self.run_check(empty)[0])
        self.assertTrue(self.run_check(long)[0])

    def test_local_links_must_resolve_inside_the_skill(self):
        body = "Read [rules](references/rules.md), [missing](references/gone.md), and [outside](../x.md).\n"
        skill = make_skill(self.tmp.name, "links", "name: links\ndescription: Linked.", body=body,
                           files={"references/rules.md": "Rules.\n"})
        errors = self.run_check(skill)[0]
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("gone.md" in e for e in errors))
        self.assertTrue(any("outside" in e for e in errors))

    def test_unlinked_nested_reference_and_placeholders_warn(self):
        body = "Read [rules](references/rules.md).\n\nTODO: add tax rules\n"
        skill = make_skill(self.tmp.name, "nested", "name: nested\ndescription: Nested.", body=body,
                           files={"references/rules.md": "See [deep](deep/more.md).\n",
                                  "references/deep/more.md": "Deep.\n"})
        errors, warnings = self.run_check(skill)
        self.assertEqual(errors, [])
        self.assertTrue(any("deep/more.md" in w for w in warnings))
        self.assertTrue(any("placeholder" in w for w in warnings))

    def test_prose_mentioning_todo_is_not_a_placeholder(self):
        body = "Do not manufacture an issue, owner, TODO, or future optimization.\n"
        skill = make_skill(self.tmp.name, "prose", "name: prose\ndescription: Prose.", body=body)
        self.assertEqual(self.run_check(skill), ([], []))

    def test_cli_exit_status(self):
        good = make_skill(self.tmp.name, "good", "name: good\ndescription: Good.")
        bad = make_skill(self.tmp.name, "anthropic-tool", "name: anthropic-tool\ndescription: Bad on Anthropic.")
        self.assertEqual(check_skill.main([str(good)]), 0)
        self.assertEqual(check_skill.main([str(bad)]), 0)
        self.assertEqual(check_skill.main([str(bad), "--host", "anthropic"]), 1)


if __name__ == "__main__":
    unittest.main()
