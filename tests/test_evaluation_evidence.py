import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "behavior"))

import evaluate  # noqa: E402

EVIDENCE = ROOT / "tests" / "behavior" / "evidence"
EVALUATIONS = sorted(path.parent for path in EVIDENCE.glob("*/contract.json"))


class DecisionRuleTests(unittest.TestCase):
    def test_value_needs_five_wins_and_no_loss(self):
        self.assertEqual(evaluate.decide(5, 0, 5), "value")
        self.assertEqual(evaluate.decide(4, 0, 4), "inconclusive")
        self.assertEqual(evaluate.decide(7, 1, 12), "inconclusive")

    def test_no_value_needs_ten_discriminating_cases(self):
        self.assertEqual(evaluate.decide(3, 3, 10), "no value")
        self.assertEqual(evaluate.decide(0, 2, 9), "inconclusive")


class RecordedEvaluationTests(unittest.TestCase):
    def test_recorded_evaluations_recompute_to_their_summaries(self):
        self.assertTrue(EVALUATIONS)
        for directory in EVALUATIONS:
            with self.subTest(evaluation=directory.name):
                _, errors = evaluate.check(directory)
                self.assertEqual(errors, [])

    def test_changed_verdict_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / EVALUATIONS[0].name
            shutil.copytree(EVALUATIONS[0], copy)
            path = copy / "judgments.json"
            judged = json.loads(path.read_text(encoding="utf-8"))
            pair_judge = json.loads((copy / "summary.json").read_text(encoding="utf-8"))["judges"]["pair"]
            verdict = next(v for v in judged["verdicts"] if v["judge"] == pair_judge and v["run"].startswith("B-"))
            verdict["overall"] = "fail"
            verdict["criteria"][0]["verdict"] = "fail"
            path.write_text(json.dumps(judged), encoding="utf-8")
            _, errors = evaluate.check(copy)
            self.assertTrue(any("generated_skill_vs_source" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
