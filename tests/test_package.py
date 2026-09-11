import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


class PackageTests(unittest.TestCase):
    def test_skill_metadata_and_body(self):
        entries = sorted(SKILLS.glob("*/SKILL.md"))
        self.assertTrue(entries, "No installable skills")
        names = []
        for entry in entries:
            with self.subTest(skill=entry.parent.name):
                text = entry.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                _, header, body = text.split("---", 2)
                metadata = yaml.safe_load(header)
                self.assertIsInstance(metadata, dict)
                self.assertEqual(set(metadata), {"name", "description"})
                name = metadata["name"]
                description = metadata["description"]
                self.assertIsInstance(name, str)
                self.assertRegex(name, r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                self.assertLessEqual(len(name), 64)
                self.assertEqual(name, entry.parent.name)
                self.assertIsInstance(description, str)
                self.assertTrue(description.strip())
                self.assertLessEqual(len(description), 1024)
                self.assertTrue(body.strip())
                names.append(name)
        self.assertEqual(len(names), len(set(names)))

    def test_skill_files_are_self_contained(self):
        for skill in SKILLS.iterdir():
            self.assertTrue(skill.is_dir())
            for path in skill.rglob("*"):
                with self.subTest(path=path.relative_to(ROOT)):
                    self.assertFalse(path.is_symlink(), "Release must not depend on symlinks")
                    if path.suffix != ".md":
                        continue
                    text = path.read_text(encoding="utf-8")
                    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                        url = urlsplit(target)
                        if url.scheme or not url.path:
                            continue
                        resolved = (path.parent / unquote(url.path)).resolve()
                        self.assertTrue(resolved.is_relative_to(skill.resolve()), target)
                        self.assertTrue(resolved.is_file(), target)

    def test_maintainer_dependencies_are_outside_skills(self):
        forbidden = {"tests", ".github", ".git", ".venv", "__pycache__", "node_modules"}
        for path in SKILLS.rglob("*"):
            self.assertFalse(forbidden.intersection(path.relative_to(SKILLS).parts), str(path))
        self.assertTrue((ROOT / "tests" / "behavior" / "cases.json").is_file())

    def test_behavior_case_ids_are_unique(self):
        import json

        cases = json.loads((ROOT / "tests" / "behavior" / "cases.json").read_text())
        ids = [case["id"] for case in cases]
        self.assertTrue(ids)
        self.assertEqual(len(ids), len(set(ids)))
        for case in cases:
            self.assertTrue(case["request"].strip())
            self.assertTrue(case["acceptance"])


if __name__ == "__main__":
    unittest.main()
