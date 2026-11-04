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

    def test_local_links_must_resolve_and_outside_links_warn(self):
        body = ("Read [rules](references/rules.md), [missing](references/gone.md), "
                "[gone outside](../x.md), and [sibling](../sibling/SKILL.md).\n\n"
                "```cpp\nauto f = [&db](...) { return 1; };\n```\n\nInline `[a](b.md)` is code.\n")
        make_skill(self.tmp.name, "sibling", "name: sibling\ndescription: Sibling.")
        skill = make_skill(self.tmp.name, "links", "name: links\ndescription: Linked.", body=body,
                           files={"references/rules.md": "Rules.\n"})
        errors, warnings = self.run_check(skill)
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("gone.md" in e for e in errors))
        self.assertTrue(any("x.md" in e for e in errors))
        self.assertTrue(any("sibling" in w and "outside" in w for w in warnings))

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

    def test_unreadable_yaml_is_unchecked_not_invalid(self):
        installed = check_skill.yaml
        check_skill.yaml = None
        try:
            frontmatters = {
                "anchored": "name: anchored\ndescription: &d Shared text.",
                "unclosed-flow": "name: unclosed-flow\ndescription: Good.\nmetadata: {",
                "flow-mapping": "name: flow-mapping\ndescription: Good.\nmetadata: {owner: team}",
                "indented-flow": "name: indented-flow\ndescription: Good.\nmetadata:\n  {owner: team",
                "inline-list": "name: inline-list\ndescription: Good.\nallowed-tools: [Read",
                "leading-bracket": "name: leading-bracket\ndescription: ] Reviews changes.",
                "leading-dash": "name: leading-dash\ndescription: - Reviews changes.",
                "folded-marker-on-next-line": "name: folded-marker-on-next-line\ndescription:\n  > Reviews changes.",
                "tab-in-quoted": "name: tab-in-quoted\ndescription: \"Reviews\n\tchanges.\"",
            }
            for folder, frontmatter in frontmatters.items():
                with self.subTest(folder):
                    skill = make_skill(self.tmp.name, folder, frontmatter)
                    errors, warnings = self.run_check(skill)
                    self.assertEqual(errors, [])
                    self.assertTrue(warnings[0].startswith(check_skill.UNCHECKED))
                    self.assertEqual(check_skill.main([str(skill)]), 2)
        finally:
            check_skill.yaml = installed

    def test_unchecked_value_does_not_hide_other_errors(self):
        installed = check_skill.yaml
        check_skill.yaml = None
        try:
            skill = make_skill(self.tmp.name, "folder", "name: Bad_Name\ndescription: Good.\nallowed-tools: [Read, Grep]",
                               body="Read [rules](references/gone.md).\n")
            errors, warnings = self.run_check(skill)
            self.assertEqual(len(errors), 3, errors)
            self.assertTrue(any("allowed-tools" in w and w.startswith(check_skill.UNCHECKED) for w in warnings))
            self.assertEqual(check_skill.main([str(skill)]), 1)
        finally:
            check_skill.yaml = installed

    def test_cli_exit_status(self):
        good = make_skill(self.tmp.name, "good", "name: good\ndescription: Good.")
        bad = make_skill(self.tmp.name, "anthropic-tool", "name: anthropic-tool\ndescription: Bad on Anthropic.")
        self.assertEqual(check_skill.main([str(good)]), 0)
        self.assertEqual(check_skill.main([str(bad)]), 0)
        self.assertEqual(check_skill.main([str(bad), "--host", "anthropic"]), 1)


class TabIndentationTests(unittest.TestCase):
    def test_tab_after_block_indentation_is_content(self):
        installed = check_skill.yaml
        check_skill.yaml = None
        try:
            with tempfile.TemporaryDirectory() as root:
                skill = make_skill(root, "good", "name: good\ndescription: |\n  Reviews.\n  \tIndented example.")
                self.assertEqual(check_skill.check(skill), ([], []))
        finally:
            check_skill.yaml = installed


VALID_FRONTMATTER = {
    "blank line after a field": 'name: good\n\ndescription: Good.',
    "inline comments": 'name: "good" # folder name\ndescription: Reviews things # short',
    "escapes and colons": 'name: good\ndescription: "Use when: a \\"quoted\\" rule applies"',
    "single quotes": "name: 'good'\ndescription: 'It''s a review: rules apply.'",
    "folded and literal blocks": "name: good\ndescription: >-\n  Reviews changes.\n\n  Use when reviewing.\nlicense: |\n  MIT\n",
    "nested metadata and lists": "name: good\ndescription: Good.\nmetadata:\n  owner: team\n  tags:\n    - a\nallowed-tools:\n  - Read\n",
    "YAML hex escape": 'name: good\ndescription: "\\x41 review"',
    "plain value on indented lines": "name: good\ndescription:\n  Reviews changes. Use when\n  reviewing pull requests.",
    "bracketed text in a plain continuation": "name: good\ndescription:\n  Review these examples.\n  [a] is first.",
    "bracketed text in a nested literal": "name: good\ndescription: Good.\nmetadata:\n  note: |\n    [a] is text.",
    "tab inside a nested literal": "name: good\ndescription: Good.\nmetadata:\n  note: |\n    Reviews.\n    \tIndented example.",
    "tab inside a nested quoted value": "name: good\ndescription: Good.\nmetadata:\n  note: \"Reviews\n\tchanges.\"",
}
INVALID_FRONTMATTER = {
    "numeric description": "name: good\ndescription: 42",
    "boolean description": "name: good\ndescription: true",
    "mapping description": "name: good\ndescription:\n  text: Good.",
    "list name": "name:\n  - good\ndescription: Good.",
    "empty description": "name: good\ndescription:",
    "indented number": "name: good\ndescription:\n  42",
    "indented boolean": "name: good\ndescription:\n  true",
    "comment-only value": "name: good\ndescription: # none yet",
    "unquoted colon": "name: good\ndescription: Reviews rules. Static review only: do not run code.",
    "unquoted colon on a continuation line": "name: good\ndescription: Reviews rules.\n  Use when: reviewing.",
    "text after a block scalar header": "name: good\ndescription: >- Reviews\n  changes.",
    "tab-indented continuation": "name: good\ndescription: Reviews\n\tchanges.",
    "space then tab continuation": "name: good\ndescription: Reviews\n \tchanges.",
    "tab-only line between keys": "name: good\ndescription: Good.\n\t\nlicense: MIT",
    "tab before a quoted value on the next line": "name: good\ndescription:\n\t\"Reviews.\"",
}


class FrontmatterParsingTests(unittest.TestCase):
    """The standard-library fallback must agree with YAML on skill frontmatter."""

    def check_with_each_parser(self, frontmatter):
        results = {}
        installed = check_skill.yaml
        parsers = {"stdlib": None}
        if installed is not None:
            parsers["pyyaml"] = installed
        for label, parser in parsers.items():
            check_skill.yaml = parser
            try:
                with tempfile.TemporaryDirectory() as root:
                    skill = make_skill(root, "good", frontmatter)
                    results[label] = check_skill.check(skill)
            finally:
                check_skill.yaml = installed
        return results

    def test_valid_frontmatter_passes(self):
        for label, frontmatter in VALID_FRONTMATTER.items():
            for parser, (errors, warnings) in self.check_with_each_parser(frontmatter).items():
                with self.subTest(label, parser=parser):
                    self.assertEqual(errors, [])
                    self.assertFalse([w for w in warnings if w.startswith(check_skill.UNCHECKED)])

    def test_wrong_types_and_missing_values_fail(self):
        for label, frontmatter in INVALID_FRONTMATTER.items():
            for parser, (errors, _) in self.check_with_each_parser(frontmatter).items():
                with self.subTest(label, parser=parser):
                    self.assertEqual(len(errors), 1, errors)

    def test_fallback_values_match_yaml(self):
        if check_skill.yaml is None:
            self.skipTest("PyYAML not installed")
        installed = check_skill.yaml
        for label, frontmatter in {**VALID_FRONTMATTER, **INVALID_FRONTMATTER}.items():
            with self.subTest(label):
                try:
                    expected = installed.safe_load(frontmatter)
                except installed.YAMLError:
                    expected = None
                check_skill.yaml = None
                try:
                    if expected is None:
                        with self.assertRaises(ValueError):
                            check_skill.parse_fields(frontmatter)
                        continue
                    actual = check_skill.parse_fields(frontmatter)
                finally:
                    check_skill.yaml = installed
                for key in ("name", "description"):
                    if isinstance(expected.get(key), (str, int, float, bool)) or expected.get(key) is None:
                        self.assertEqual(actual.get(key), expected.get(key), key)
                    else:
                        self.assertIs(type(actual.get(key)), type(expected.get(key)), key)


if __name__ == "__main__":
    unittest.main()
