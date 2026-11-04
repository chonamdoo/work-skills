import contextlib
import datetime
import importlib.util
import io
import random
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

    def test_optional_specification_fields_are_accepted(self):
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

    def test_optional_field_limits_fail_and_loose_types_warn(self):
        long = make_skill(self.tmp.name, "compat", "name: compat\ndescription: C.\ncompatibility: " + "x" * 501)
        flat = make_skill(self.tmp.name, "flat", "name: flat\ndescription: F.\nmetadata: owner")
        loose = make_skill(self.tmp.name, "loose", "name: loose\ndescription: L.\nmetadata:\n  tags:\n    - a\n"
                           "allowed-tools:\n  - Read")
        fits = make_skill(self.tmp.name, "fits", "name: fits\ndescription: F.\ncompatibility: " + "x" * 500)
        self.assertEqual(len(self.run_check(long)[0]), 1)
        self.assertEqual(len(self.run_check(flat)[0]), 1)
        errors, warnings = self.run_check(loose)
        self.assertEqual(errors, [])
        self.assertTrue(any(w.startswith("metadata:") for w in warnings))
        self.assertTrue(any(w.startswith("allowed-tools:") for w in warnings))
        self.assertEqual(self.run_check(fits), ([], []))

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

    def test_link_destinations_with_parentheses_and_angles_resolve(self):
        body = ("Read [v2](references/rules(v2).md), [spaced](<references/my rules.md>),\n"
                "and [escaped](<references/rules\\(v2\\).md>).\n")
        skill = make_skill(self.tmp.name, "parens", "name: parens\ndescription: P.", body=body,
                           files={"references/rules(v2).md": "V2.\n", "references/my rules.md": "Spaced.\n"})
        self.assertEqual(self.run_check(skill), ([], []))

    def test_link_syntax_is_parsed_to_the_end(self):
        body = ("Split [c](\nmissing-split.md\n) and hard-wrapped [payment\nrules](missing-wrapped.md).\n\n"
                "Linked image [![d](missing-image.png)](missing-outer.md) and [step [1]](missing-nested.md).\n\n"
                "Not links: an [example](missing-open.md is unclosed, a [gap\n\nline](missing-gap.md),\n"
                "<!-- [old](missing-comment.md) -->\n\n"
                "A link inside link text voids the outer one: [outer [inner](missing-inner.md)](not-a-link.md),\n"
                "also after an escaped bang: [a \\![b](missing-escaped.md)](not-a-link-either.md),\n"
                "or around an empty destination: [o [i]()](not-a-link-3.md) [o [i](<>)](not-a-link-4.md).\n\n"
                "An image description may hold a link: ![o [i](SKILL.md)](missing-described.png).\n\n"
                "Malformed targets are reported, not fatal: [x](<//[>) and [y](a%00.md).\n\n"
                "Code and escapes are not links: ``[a](missing-code.md)``, `the [b](missing-code2.md)\nform`,\n"
                "and \\[c](missing-escaped-open.md). Entities are decoded: [d](a&amp;b.md), [e](SKILL&#46;md).\n\n"
                "Removed spans join nothing: [f]<!-- x -->(missing-joined.md), [g]`x`(missing-joined2.md).\n\n"
                "Titles hold no links: [h](SKILL.md \"[i](missing-title.md)\"), and a title with a\n"
                "blank line ends nothing: [j](missing-blank-title.md \"a\n \nb\").\n\n"
                "Template lines and definitions are not checked:\n\n[Severity]: high\n\n[r]: missing-ref.md\n")
        skill = make_skill(self.tmp.name, "syntax", "name: syntax\ndescription: S.", body=body,
                           files={"a&b.md": "Entity.\n"})
        self.assertEqual(sorted(self.run_check(skill)[0]), sorted([
            f"SKILL.md: link '{name}' does not resolve"
            for name in ("missing-described.png", "missing-escaped.md", "missing-image.png", "missing-inner.md",
                         "missing-nested.md", "missing-outer.md", "missing-split.md", "missing-wrapped.md")
        ] + [f"SKILL.md: link '{name}' is not a valid local path" for name in ("//[", "a%00.md")]))

    def test_unreadable_markdown_is_reported_not_a_crash(self):
        skill = make_skill(self.tmp.name, "odd", "name: odd\ndescription: O.")
        (skill / "references").mkdir()
        (skill / "references" / "legacy.md").write_bytes("가".encode("cp949"))
        (skill / "folder.md").mkdir()
        (skill / "examples").mkdir()
        (skill / "linked-dir.md").symlink_to(skill / "examples")
        (skill / "dangling.md").symlink_to(skill / "nowhere.md")
        errors, warnings = self.run_check(skill)
        self.assertEqual(errors, ["dangling.md: broken symbolic link"])
        self.assertTrue(any("legacy.md" in w and "UTF-8" in w for w in warnings))

    def test_byte_order_mark_is_named(self):
        skill = make_skill(self.tmp.name, "bom", "name: bom\ndescription: B.")
        (skill / "SKILL.md").write_bytes(b"\xef\xbb\xbf" + (skill / "SKILL.md").read_bytes())
        errors = self.run_check(skill)[0]
        self.assertEqual(len(errors), 1)
        self.assertIn("byte-order mark", errors[0])

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

    def test_unreadable_yaml_is_unchecked_and_body_is_still_checked(self):
        installed = check_skill.yaml
        check_skill.yaml = None
        try:
            skill = make_skill(self.tmp.name, "anchored", "name: anchored\ndescription: &d Shared text.",
                               body="Read [gone](references/gone.md).\n")
            errors, warnings = self.run_check(skill)
            self.assertEqual(errors, ["SKILL.md: link 'references/gone.md' does not resolve"])
            self.assertTrue(warnings[0].startswith(check_skill.UNCHECKED))
            clean = make_skill(self.tmp.name, "clean", "name: clean\ndescription: &d Shared text.")
            self.assertEqual(check_skill.main([str(clean)]), 3)
        finally:
            check_skill.yaml = installed

    def test_cli_survives_unencodable_names(self):
        skill = make_skill(self.tmp.name, "odd-name", 'name: "\\uD800"\ndescription: Good.')
        with contextlib.redirect_stdout(io.TextIOWrapper(io.BytesIO(), encoding="utf-8")):
            self.assertEqual(check_skill.main([str(skill)]), 1)

    def test_cli_exit_status(self):
        good = make_skill(self.tmp.name, "good", "name: good\ndescription: Good.")
        bad = make_skill(self.tmp.name, "anthropic-tool", "name: anthropic-tool\ndescription: Bad on Anthropic.")
        self.assertEqual(check_skill.main([str(good)]), 0)
        self.assertEqual(check_skill.main([str(bad)]), 0)
        self.assertEqual(check_skill.main([str(bad), "--host", "anthropic"]), 1)


VALID_FRONTMATTER = {
    "blank line after a field": 'name: good\n\ndescription: Good.',
    "inline comments": 'name: "good" # folder name\ndescription: Reviews things # short',
    "escapes and colons": 'name: good\ndescription: "Use when: a \\"quoted\\" rule applies"',
    "single quotes": "name: 'good'\ndescription: 'It''s a review: rules apply.'",
    "folded and literal blocks": "name: good\ndescription: >-\n  Reviews changes.\n\n  Use when reviewing.\nlicense: |\n  MIT\n",
    "nested metadata and lists": "name: good\ndescription: Good.\nmetadata:\n  owner: team\n  tags:\n    - a\nallowed-tools:\n  - Read\n",
    "metadata with a leading comment": "name: good\ndescription: Good.\nmetadata:\n  # who owns it\n  owner: team\n",
    "quoted keys": "\"name\": good\n'description': Reviews changes.\nmetadata:\n  \"version\": \"1.0\"\n  'owner': team\n",
    "flow mapping": "name: good\ndescription: Good.\nmetadata: {author: x, version: \"1.0\"}",
    "kept and indented block lines": "name: good\ndescription: |+\n  Reviews changes.\n    Indented example.\n\nlicense: MIT",
    "folded with more-indented lines": "name: good\ndescription: >\n  Reviews changes.\n    - kept line\n  Use when reviewing.\n",
    "YAML hex escape": 'name: good\ndescription: "\\x41 review"',
    "plain value on indented lines": "name: good\ndescription:\n  Reviews changes. Use when\n  reviewing pull requests.",
    "plain value with a blank line": "name: good\ndescription: Reviews changes.\n\n  Use when reviewing.",
    "unindented sequences": "name: good\ndescription: Good.\nallowed-tools:\n- Read\n- Grep\nmetadata:\n  tags:\n  - a\n",
    "column-0 comment inside a mapping": "name: good\ndescription: Good.\nmetadata:\n  owner: t\n# old\n  team: x\n",
    "kept block scalar as the last field": "name: good\ndescription: |+\n  " + "x" * 1022 + "\n",
    "less-indented comment after a block": "name: good\ndescription: |\n  Reviews changes.\n # for the next field\nlicense: MIT",
    "merge key": "name: good\ndescription: Good.\nmetadata:\n  <<: &common\n    owner: team\n  version: \"1.0\"",
    "key containing a colon": "name: good\ndescription: Good.\nmetadata:\n  a:b: c",
    "YAML 1.1 scalars that stay strings": "name: good\ndescription: Good.\nlicense: 08\ncompatibility: 1e3",
    "comment before the value": "name: good\ndescription: # why the skill exists\n  Use when reviewing.",
    "integer and string keys": "name: good\ndescription: Good.\nmetadata:\n  42: x\n  \"42\": y",
    "document end marker": "name: good\ndescription: Good.\n...",
    "document end marker with a comment": "name: good\ndescription: Good.\n... # end",
    "tabs inside nested quoted and block values": "name: good\ndescription: Good.\nmetadata:\n  owner: \"a\tb\"\n"
    "license: |\n  a\tb",
    "tabs in nested block scalars and quoted list items": "name: good\ndescription: Good.\nmetadata:\n"
    "  notes: |\n    col1\tcol2\n  more: >-\n    a\tb\nallowed-tools:\n  - \"a\tb\"",
    "quoted value continued on the next line": "name: good\ndescription: \"Reviews changes\n  across lines.\"",
    "block indicator on the next line": "name: good\ndescription:\n  |\n  Use when: reviewing PRs.",
    "naive and UTC timestamps as distinct keys": "name: good\ndescription: Good.\nmetadata:\n"
    "  2026-11-04T10:00:00: x\n  2026-11-04T10:00:00Z: y\n  last: 0001-01-01T00:00:00+01:00",
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
    "sequence entry as a value": "name: good\ndescription: - Reviews rules.",
    "duplicate name": "name: claude-x\nname: good\ndescription: Good.",
    "date description": "name: good\ndescription: 2026-11-04",
}
UNCERTAIN_FRONTMATTER = {
    "tab in a valid quoted value": "name: good\ndescription: \"Reviews\tchanges.\"",
    "tab after a quoted value": "name: good\ndescription: 'Reviews changes.'\t# note",
    "tab-indented continuation": "name: good\ndescription: Reviews changes.\n\tUse when reviewing.",
    "tab before a quoted value": "name:\t'good'\ndescription: Good.",
    "quoted value continued at column 0": "name: good\ndescription: 'Reviews\nchanges.'",
    "column-0 comment inside a block value": "name: good\ndescription: >\n# c\n  Reviews changes.",
    "block indicator on the next line with a tab": "name: good\ndescription:\n  >\n  Reviews\tchanges.",
    "flow mapping": "name: good\ndescription: Good.\nmetadata: {a: b}",
    "quoted value on the next line continued at column 0": "name: good\ndescription:\n  \"Reviews\nchanges.\"",
    "Unicode space before a boolean word": "name: good\ndescription: \u00a0yes",
    "indented top-level mapping": "  name: good\n  description: Good.",
    "NUL character": "name: good\ndescription: Good.\x00",
}


def shape(value):
    """Comparable form that keeps types, time zones, and nested values; lists keep only their type."""
    if isinstance(value, list):
        return ("list",)
    if isinstance(value, dict):
        return {shape(k): shape(v) for k, v in value.items()}
    if isinstance(value, datetime.datetime):
        return ("datetime", value.replace(tzinfo=None), value.utcoffset())
    if isinstance(value, float) and value != value:
        return ("float", "nan")
    return (type(value).__name__, value)


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
                    results[label] = check_skill.check(skill)[0]
            finally:
                check_skill.yaml = installed
        return results

    def test_valid_frontmatter_passes(self):
        for label, frontmatter in VALID_FRONTMATTER.items():
            for parser, errors in self.check_with_each_parser(frontmatter).items():
                with self.subTest(label, parser=parser):
                    self.assertEqual(errors, [])

    def test_wrong_types_and_missing_values_fail(self):
        for label, frontmatter in INVALID_FRONTMATTER.items():
            for parser, errors in self.check_with_each_parser(frontmatter).items():
                with self.subTest(label, parser=parser):
                    self.assertEqual(len(errors), 1, errors)

    def assert_parity(self, label, frontmatter):
        installed = check_skill.yaml
        with self.subTest(label, frontmatter=frontmatter):
            try:
                expected = installed.load(frontmatter, Loader=check_skill.yaml_loader())
            except installed.YAMLError:
                expected = None
            check_skill.yaml = None
            try:
                if expected is None:
                    with self.assertRaises(ValueError):
                        check_skill.parse_fields(frontmatter)
                    return
                actual = check_skill.parse_fields(frontmatter)
            except check_skill.Unsupported:
                return  # the fallback reports these as unchecked rather than guessing
            finally:
                check_skill.yaml = installed
            for key in ("name", "description", "license", "compatibility", "metadata"):
                self.assertEqual(shape(actual.get(key)), shape(expected.get(key)), key)

    def test_fallback_reports_uncertain_yaml_as_unchecked(self):
        installed = check_skill.yaml
        check_skill.yaml = None
        try:
            for label, frontmatter in UNCERTAIN_FRONTMATTER.items():
                with self.subTest(label), tempfile.TemporaryDirectory() as root:
                    errors, warnings = check_skill.check(make_skill(root, "good", frontmatter))
                    self.assertEqual(errors, [])
                    self.assertTrue(warnings and warnings[0].startswith(check_skill.UNCHECKED), warnings)
        finally:
            check_skill.yaml = installed

    def test_fallback_values_match_yaml(self):
        if check_skill.yaml is None:
            self.skipTest("PyYAML not installed")
        for label, frontmatter in {**VALID_FRONTMATTER, **INVALID_FRONTMATTER, **UNCERTAIN_FRONTMATTER}.items():
            self.assert_parity(label, frontmatter + "\n")

    def test_fallback_matches_yaml_on_generated_frontmatter(self):
        if check_skill.yaml is None:
            self.skipTest("PyYAML not installed")
        scalars = ["Reviews changes.", "08", "1e3", "1.5e+3", "on", "Off", "0x1f", "0b101", "1_000", "1:20",
                   ".inf", "~", "nUll", "yes please", "a # note", "a#b", "-x", "- x", "? x", "Use: it",
                   "\"a: b\"", "'it''s'", "", "[]", "{}", "*ref", "2026-11-04", "2026-1-4",
                   "2026-11-04 10:00:00", "2026-11-04T10:00:00.5+09:00", "\tx", "x\t", "=", "<<", ",x", "]x",
                   "}x", "|x", ">x", "#x", "%x", "&x", "@x", "`x", ":x", "-", "?", "a\x1bb", "a\x85b",
                   "a\u2028b", "\"unterminated", "x: ", "a: b: c"]
        descriptions = [
            lambda r: "description: " + r.choice(scalars),
            lambda r: "description:\n  " + r.choice(scalars) + "\n  " + r.choice(scalars),
            lambda r: "description: " + r.choice(scalars) + "\n\n  " + r.choice(scalars),
            lambda r: "description: # why\n  " + r.choice(scalars) + r.choice(["", "\n  more", "\n  # c\n  more"]),
            lambda r: "description: " + r.choice(["|", ">", "|-", ">-", "|+", ">+"]) + "\n  "
            + r.choice(scalars) + r.choice(["", "\n    more", "\n\n  next", "\n # note"]) + r.choice(["", "\n", "\n\n"]),
        ]
        extras = [
            lambda r: "license: " + r.choice(scalars),
            lambda r: "metadata:\n  owner: " + r.choice(scalars) + r.choice(["", "\n# c\n  v: '1'", "\n  tags:\n  - a"]),
            lambda r: "metadata:\n  " + r.choice(["42", "\"42\"", "yes", "'yes'", "a:b"]) + ": x\n  "
            + r.choice(["42", "\"42\"", "yes", "on"]) + ": y",
            lambda r: "allowed-tools:\n" + r.choice(["- Read", "  - Read", "  - Read\n  - Grep"]),
            lambda r: "allowed-tools:\n  - " + r.choice(scalars) + r.choice(["", "\n  - " + r.choice(scalars),
                                                                     "\n    more", "\n  # c\n  - x"]),
            lambda r: "metadata:\n  owner: " + r.choice(scalars) + r.choice(["\n  # c\n    b", "\n# c\n    b",
                                                                        "\n  # c\n  v: x", "\n    b"]),
            lambda r: "compatibility: " + r.choice(scalars),
            lambda r: "metadata:\n  notes: " + r.choice(["|\n    a\tb", ">-\n    a\tb", "\"a\tb\"", "'a'\t", "a\tb"]),
            lambda r: r.choice(["...", "# done\n...", "...\nlicense: MIT", "\tlicense: MIT"]),
        ]
        rng = random.Random(7)
        for n in range(400):
            parts = ["name: good", rng.choice(descriptions)(rng)] + [rng.choice(extras)(rng) for _ in range(rng.randrange(3))]
            rng.shuffle(parts)
            self.assert_parity(f"generated {n}", "\n".join(parts) + "\n")


if __name__ == "__main__":
    unittest.main()
