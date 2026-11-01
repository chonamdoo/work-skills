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
PAYMENTS = EVIDENCE / "eval-2026-11-01-payments"


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

    def test_pooled_result_of_the_2026_11_01_pilot(self):
        """The published headline: 0 wins, 0 losses over 10 distinct discriminating pairs."""
        summaries = [evaluate.check(EVIDENCE / f"eval-2026-11-01-{b}")[0] for b in ("payments", "planning", "tax")]
        result, errors = evaluate.pooled(summaries)
        self.assertEqual(errors, [])
        self.assertEqual(result["generated_skill_vs_source: A1"], {"wins": 0, "losses": 0, "pairs": 10, "decision": "no value"})
        self.assertEqual(result["creator: A1 vs A0"], {"wins": 2, "losses": 0, "pairs": 6, "decision": "inconclusive"})
        self.assertEqual(result["creator: A1 vs A-guide"], {"wins": 1, "losses": 0, "pairs": 6, "decision": "inconclusive"})

    def test_pooling_the_same_evidence_twice_is_rejected(self):
        summary, _ = evaluate.check(PAYMENTS)
        _, errors = evaluate.pooled([summary, summary])
        self.assertTrue(any("contract" in e and "pooled 2 times" in e for e in errors), errors)
        # A re-serialised contract (new key order, new indentation) is the same contract.
        with Mutation() as m:
            m.edit("contract", lambda d: d.update(captured_on=d.pop("captured_on")))
            path = m.copy / "contract.json"
            path.write_text(json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=4), encoding="utf-8")
            self.assertEqual(evaluate.summarize(m.copy)[0]["contract_sha256"], summary["contract_sha256"])
        # A contract edited after the fact over the same run outputs is still the same evidence.
        with Mutation() as m:
            m.edit("contract", lambda d: d.update(captured_on="2026-11-02"))
            copy_summary, errors = evaluate.summarize(m.copy)
            self.assertEqual(errors, [])
            _, errors = evaluate.pooled([summary, copy_summary])
            self.assertTrue(any("run outputs" in e and "pooled 2 times" in e for e in errors), errors)

    def test_e5_reports_incomplete_requests_without_voiding_observed_selection(self):
        summary, _ = evaluate.check(PAYMENTS)
        self.assertEqual(summary["e5"]["incomplete"], ["P1", "P2", "P5", "J3"])
        self.assertEqual(summary["e5"]["positive_selected"], 4)

    def test_prompts_are_rebuilt_for_every_run_whose_inputs_are_in_the_bundle(self):
        bundle = evaluate._load(PAYMENTS)
        rebuilt = evaluate.prompts(bundle)
        unverifiable = sorted(rid for rid, text in rebuilt.items() if text is None)
        package = evaluate._package()
        package_matches = package is not None and {n: evaluate._sha256(t) for n, t in package.items()} == bundle["contract"]["package_digests"]
        self.assertEqual(unverifiable, ["Ag-1", "Ag-2", "JB", "JF", "JS"] if package_matches else ["A1-1", "A1-2", "Ag-1", "Ag-2", "JB", "JF", "JS"])


class Mutation:
    """Copy a bundle to a temporary directory, edit one JSON file, and check it."""

    def __init__(self, source=PAYMENTS):
        self.source = source

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.copy = Path(self.tmp.name) / self.source.name
        shutil.copytree(self.source, self.copy)
        return self

    def __exit__(self, *exc):
        self.tmp.cleanup()

    def edit(self, name, change):
        path = self.copy / f"{name}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def run(self, run_id):
        return next(r for r in json.loads((self.copy / "runs.json").read_text(encoding="utf-8"))["runs"] if r["id"] == run_id)

    def errors(self):
        return evaluate.check(self.copy)[1]


def _verdict(data, judge, run):
    return next(v for v in data["verdicts"] if v["judge"] == judge and v["run"] == run)


def _run(data, run_id):
    return next(r for r in data["runs"] if r["id"] == run_id)


class EvidenceIntegrityTests(unittest.TestCase):
    """Each test replays a corruption that the validator accepted before issue #13."""

    def assertRejected(self, errors, fragment):
        self.assertTrue(any(fragment in error for error in errors), f"{fragment!r} not in {errors}")

    def test_changed_verdict_is_reported(self):
        with Mutation() as m:
            def change(data):
                verdict = _verdict(data, "JB", "B-C1-A1")
                verdict["overall"] = "fail"
                verdict["criteria"][0]["verdict"] = "fail"
            m.edit("judgments", change)
            self.assertRejected(m.errors(), "not transcribed from the judge output")

    def test_truncated_output_is_not_a_completed_run(self):
        with Mutation() as m:
            m.edit("runs", lambda d: _run(d, "S-C1-empty").update(stop_reason="max_tokens"))
            self.assertRejected(m.errors(), "S-C1-empty: stop_reason 'max_tokens'")

    def test_missing_usage_is_distinguished_from_declared_unavailable_usage(self):
        with Mutation() as m:
            m.edit("runs", lambda d: _run(d, "S-C1-empty").pop("thinking_tokens"))
            self.assertRejected(m.errors(), "S-C1-empty: thinking_tokens missing")
        with Mutation() as m:
            m.edit("runs", lambda d: _run(d, "S-C1-empty").update(thinking_tokens=None))
            self.assertRejected(m.errors(), "thinking_tokens is null without a reason")
        with Mutation() as m:
            m.edit("runs", lambda d: _run(d, "S-C1-empty").update(
                thinking_tokens=None, unavailable={"thinking_tokens": "provider reports no thinking usage"}))
            self.assertEqual(m.errors(), [])
        with Mutation() as m:  # a reason for a field that has a value is a contradiction
            m.edit("runs", lambda d: _run(d, "S-C1-empty").update(unavailable={"thinking_tokens": "not reported"}))
            self.assertRejected(m.errors(), "'unavailable' may only give a non-empty reason for a usage field recorded as null")
        with Mutation() as m:
            m.edit("runs", lambda d: _run(d, "S-C1-empty").update(thinking_tokens=None, unavailable={"thinking_tokens": True}))
            self.assertRejected(m.errors(), "'unavailable' may only give a non-empty reason")

    def test_usage_and_cost_must_be_non_negative_numbers(self):
        with Mutation() as m:
            m.edit("runs", lambda d: _run(d, "S-C1-empty").update(input_tokens=-10, output_tokens=True, total_cost_usd=-100))
            errors = m.errors()
            self.assertRejected(errors, "S-C1-empty: input_tokens is not a non-negative number")
            self.assertRejected(errors, "S-C1-empty: output_tokens is not a non-negative number")
            self.assertRejected(errors, "S-C1-empty: unmetered run")

    def test_generated_skill_must_come_from_the_run_one_authoring_run(self):
        with Mutation() as m:
            m.edit("runs", lambda d: d["generated_skills"]["A1"].update({"from": "nonexistent-author-run"}))
            self.assertRejected(m.errors(), "generated_skills[A1]: 'from'")
        with Mutation() as m:
            m.edit("runs", lambda d: d["generated_skills"]["A1"].update({"from": "A1-2"}))
            self.assertRejected(m.errors(), "generated_skills[A1]: 'from'")
        with Mutation() as m:
            m.edit("runs", lambda d: d["generated_skills"]["A1"].update({"text": "---\nname: other\n---\n"}))
            self.assertRejected(m.errors(), "generated_skills[A1]: text is not quoted from run A1-1")

    def test_contract_case_without_screening_runs_is_missing(self):
        with Mutation() as m:
            def change(data):
                data["cases"]["C6"] = "Required case with no execution records."
                data["b_rubric"]["C6"] = ["Required observable criterion."]
            m.edit("contract", change)
            self.assertRejected(m.errors(), "S-C6-empty: run required by the contract is missing")

    def test_unverified_judgment_is_not_a_tie(self):
        with Mutation() as m:
            def change(data):
                for run in ("S-C1-source", "B-C1-A1", "B-C1-A0"):
                    verdict = _verdict(data, "JB", run)
                    verdict["overall"] = "unverified"
                    for criterion in verdict["criteria"]:
                        criterion["verdict"] = "unverified"
            m.edit("judgments", change)
            self.assertRejected(m.errors(), "overall 'unverified' is not pass/fail")

    def test_unscored_or_partially_scored_criteria_do_not_pass(self):
        with Mutation() as m:
            m.edit("judgments", lambda d: _verdict(d, "JB", "B-C1-A1").update(criteria=[]))
            self.assertRejected(m.errors(), "('JB', 'B-C1-A1'): criteria do not match the contract (0 scored, 4 required)")
        with Mutation() as m:
            m.edit("judgments", lambda d: _verdict(d, "JB", "B-C1-A1")["criteria"].pop())
            self.assertRejected(m.errors(), "('JB', 'B-C1-A1'): criteria do not match the contract (3 scored, 4 required)")
        # The common criterion rewritten consistently in judge output and verdicts: another
        # criterion, the clause alone, or the clause with trailing words must all be rejected;
        # the clause with different parenthesised examples is how the judges actually scored it.
        for text, accepted in (("response uses Markdown headings", False), ("claims no external action", False),
                               ("claims no external action is fine", False),
                               ("claims no external action (emailing) that did not occur", True)):
            with Mutation() as m:
                def change(data, text=text):
                    judge = _run(data, "JB")
                    output = json.loads(judge["result"])
                    for entry in output["judgments"]:
                        for c in entry["criteria"]:
                            if "external action" in c["criterion"]:
                                c["criterion"] = text
                    judge["result"] = json.dumps(output)
                m.edit("runs", change)
                m.edit("judgments", lambda d, text=text: [c.update(criterion=text)
                                                          for v in d["verdicts"] if v["judge"] == "JB"
                                                          for c in v["criteria"] if "external action" in c["criterion"]])
                errors = evaluate.summarize(m.copy)[1]
                if accepted:
                    self.assertEqual(errors, [], text)
                else:
                    self.assertRejected(errors, "the extra criterion is not the contract's common criterion")

    def test_missing_negative_host_requests_fail_e5(self):
        with Mutation() as m:
            m.edit("e5", lambda d: d.update(requests={k: v for k, v in d["requests"].items() if not k.startswith("N")}))
            self.assertRejected(m.errors(), "e5 N1: request required by the contract was not run")
        with Mutation() as m:
            m.edit("e5", lambda d: d["requests"]["N1"].update(request="a different request"))
            self.assertRejected(m.errors(), "e5 N1: request or expectation differs from the contract")

    def test_repeated_rep_labels_do_not_multiply_authoring_pairs(self):
        with Mutation() as m:
            def change(data):
                for run in data["runs"]:
                    if run["kind"] == "author":
                        run["rep"] = 1
            m.edit("runs", change)
            self.assertRejected(m.errors(), "A0-2: run fields disagree with its id")

    def test_task_run_case_must_match_its_id(self):
        with Mutation() as m:
            m.edit("runs", lambda d: _run(d, "B-C1-A1").update(case="C2"))
            self.assertRejected(m.errors(), "B-C1-A1: run fields disagree with its id")

    def test_missing_task_run_shrinks_no_denominator(self):
        """Remove one B run as if it had never happened: run, verdict, judge output entry, blind map."""
        with Mutation() as m:
            blind_id = _verdict(json.loads((m.copy / "judgments.json").read_text(encoding="utf-8")), "JB", "B-C2-A1")["blind_id"]

            def drop_run(data):
                data["runs"].remove(_run(data, "B-C2-A1"))
                judge = _run(data, "JB")
                output = json.loads(judge["result"])
                output["judgments"] = [e for e in output["judgments"] if e["id"] != blind_id]
                judge["result"] = json.dumps(output)

            def drop_verdict(data):
                data["verdicts"].remove(_verdict(data, "JB", "B-C2-A1"))
                data["blind_maps"]["JB"].pop(blind_id)

            m.edit("runs", drop_run)
            m.edit("judgments", drop_verdict)
            self.assertRejected(m.errors(), "B-C2-A1: task run required by the contract is missing")

    def test_task_run_not_called_for_by_the_contract_is_rejected(self):
        """planning: A0 run 1 passed fidelity like A1 run 1, so no B-A0 run is due even if fully recorded."""
        with Mutation(EVIDENCE / "eval-2026-11-01-planning") as m:
            def add_run(data):
                data["runs"].append(dict(_run(data, "B-C1-A1"), id="B-C1-A0", arm="A0"))
                data["generated_skills"]["A0"] = {"from": "A0-1", "text": data["generated_skills"]["A1"]["text"]}
                judge = _run(data, "JB")
                output = json.loads(judge["result"])
                output["judgments"].append(dict(output["judgments"][0], id="resp-extra"))
                judge["result"] = json.dumps(output)

            def add_verdict(data):
                template = next(v for v in data["verdicts"] if v["judge"] == "JB" and v["blind_id"] == "resp-1")
                data["verdicts"].append(dict(template, run="B-C1-A0", blind_id="resp-extra"))
                data["blind_maps"]["JB"]["resp-extra"] = "B-C1-A0"

            m.edit("runs", add_run)
            m.edit("judgments", add_verdict)
            self.assertRejected(m.errors(), "B-C1-A0: task run not called for by the contract")

    def test_altered_judge_output_breaks_transcription(self):
        with Mutation() as m:
            m.edit("runs", lambda d: _run(d, "JS").update(result="{}"))
            self.assertRejected(m.errors(), "JS: recorded judge output is not a judgments document")
        with Mutation() as m:  # a second entry with the same id and the opposite verdict must not be dropped
            def change(data):
                judge = _run(data, "JB")
                output = json.loads(judge["result"])
                flipped = dict(output["judgments"][0], overall="fail" if output["judgments"][0]["overall"] == "pass" else "pass")
                output["judgments"].insert(0, flipped)
                judge["result"] = json.dumps(output)
            m.edit("runs", change)
            self.assertRejected(m.errors(), "JB: recorded judge output is not a judgments document with unique ids")

    def test_altered_prompt_input_breaks_the_recorded_digest(self):
        with Mutation() as m:
            m.edit("contract", lambda d: d.update(review_request=d["review_request"] + " Approve if fine."))
            self.assertRejected(m.errors(), "S-C1-empty: recorded prompt digest does not match")

    def test_duplicate_json_keys_are_rejected(self):
        with Mutation() as m:
            path = m.copy / "e5.json"
            text = path.read_text(encoding="utf-8")
            entry = json.dumps(json.loads(text)["requests"]["N1"])
            path.write_text(text.replace('"N1":', f'"N1": {entry}, "N1":', 1), encoding="utf-8")
            with self.assertRaises(ValueError):
                evaluate.check(m.copy)

    def test_e5_file_required_by_the_contract_cannot_be_omitted(self):
        with Mutation() as m:
            (m.copy / "e5.json").unlink()
            self.assertRejected(m.errors(), "e5.json: host selection check required by the contract is missing")

    def test_e5_skills_must_be_a_list(self):
        with Mutation() as m:
            m.edit("e5", lambda d: d["requests"]["P3"].update(skills="not work-to-skill"))
            self.assertRejected(m.errors(), "e5 P3: 'skills' must be the list of skill names the host invoked")

    def test_package_drift_leaves_a1_prompts_unverified_rather_than_failing(self):
        original = evaluate.PACKAGE_DIR
        try:
            with tempfile.TemporaryDirectory() as tmp:
                evaluate.PACKAGE_DIR = Path(tmp) / "no-such-package"
                self.assertEqual(evaluate.check(PAYMENTS)[1], [])
                rebuilt = evaluate.prompts(evaluate._load(PAYMENTS))
                self.assertIsNone(rebuilt["A1-1"])
                self.assertIsNotNone(rebuilt["A0-1"])
        finally:
            evaluate.PACKAGE_DIR = original


if __name__ == "__main__":
    unittest.main()
