import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "tests" / "regression_ledger.json"


class RegressionLedgerTests(unittest.TestCase):
    """Each decision from a closed review keeps a guard that still exists."""

    @classmethod
    def setUpClass(cls):
        cls.entries = json.loads(LEDGER.read_text(encoding="utf-8"))

    def test_every_closed_review_source_has_decisions(self):
        sources = " ".join(entry["source"] for entry in self.entries)
        for source in ("#7", "#9", "#13", "write-for-work#2"):
            self.assertIn(source, sources)

    def test_entries_are_unique_and_guarded(self):
        ids = [entry["id"] for entry in self.entries]
        self.assertEqual(len(ids), len(set(ids)))
        for entry in self.entries:
            with self.subTest(entry=entry["id"]):
                self.assertTrue(entry["decision"].strip())
                self.assertTrue(entry["checks"])
                for check in entry["checks"]:
                    self.assertIn(check["kind"], {"auto", "model", "unverified"})
                    if check["kind"] != "auto":
                        self.assertTrue(check["why"].strip())

    def test_automatic_guards_name_existing_tests(self):
        loader = unittest.TestLoader()
        for entry in self.entries:
            for check in entry["checks"]:
                if check["kind"] != "auto":
                    continue
                for name in check["tests"]:
                    with self.subTest(entry=entry["id"], test=name):
                        suite = loader.loadTestsFromName(name)
                        self.assertEqual(suite.countTestCases(), 1)
                        self.assertNotIn("_FailedTest", type(next(iter(suite))).__name__)

    def test_model_guards_point_at_recorded_evidence(self):
        for entry in self.entries:
            for check in entry["checks"]:
                if check["kind"] != "model":
                    continue
                with self.subTest(entry=entry["id"]):
                    path = ROOT / check["evidence"]
                    self.assertTrue(path.is_file(), check["evidence"])
                    text = path.read_text(encoding="utf-8")
                    for criterion in check["criteria"]:
                        self.assertIn(criterion, text)


if __name__ == "__main__":
    unittest.main()
