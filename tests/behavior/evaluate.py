"""Check evaluation evidence directories and recompute their decisions.

Usage: python tests/behavior/evaluate.py tests/behavior/evidence/<eval-dir> [...]

Each directory holds contract.json (frozen before the runs), runs.json,
judgments.json, summary.json, and e5.json when host selection was checked.
With several directories the discordant pairs are also pooled. Model runs happen
outside this script with the host CLI recorded in the contract.

The checks are structural. Every run the contract calls for exists, completed
normally, and is metered; no run outside the contract is counted; every verdict
is pass/fail over exactly the contract's criteria and is transcribed from the
judge's recorded output; the generated skills come from the recorded authoring
runs; recorded prompt digests match prompts rebuilt from the contract where the
inputs are in the bundle; and the stored summary equals the recomputed one.
Passing says nothing about whether a verdict is semantically right.
"""

import hashlib
import json
import sys
from pathlib import Path

VALUE_WINS = 5
NO_VALUE_MIN_CASES = 10
E5_POSITIVE_MIN = 4
# Pre-registered design (contract value_rules.authoring and value_rules.B):
# three authoring arms, two runs each, task runs use run 1 of an arm.
AUTHOR_ARMS = {"A0": "A0", "A-guide": "Ag", "A1": "A1"}  # arm -> run id prefix
AUTHOR_REPS = (1, 2)
BASE_ARMS = ("A0", "A-guide")
USAGE_FIELDS = ("input_tokens", "output_tokens", "thinking_tokens", "duration_api_ms")
E5_COMPLETED = "success"
PACKAGE_DIR = Path(__file__).resolve().parents[2] / "skills" / "work-to-skill"
PACKAGE_FILES = ("SKILL.md", "references/validation.md")


def decide(wins, losses, discriminating_cases):
    """Pre-registered discordant-pair rule from epic #9 section 6."""
    if wins >= VALUE_WINS and losses == 0:
        return "value"
    if discriminating_cases >= NO_VALUE_MIN_CASES and wins - losses <= 0:
        return "no value"
    return "inconclusive"


def _pairs(verdicts, judge, arm_runs, base_runs):
    wins = losses = ties = 0
    for arm_run, base_run in zip(arm_runs, base_runs, strict=True):
        arm = verdicts[(judge, arm_run)] == "pass"
        base = verdicts[(judge, base_run)] == "pass"
        if arm and not base:
            wins += 1
        elif base and not arm:
            losses += 1
        else:
            ties += 1
    return {"wins": wins, "losses": losses, "ties": ties}


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _no_duplicate_keys(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError(f"duplicate JSON keys {sorted({k for k in keys if keys.count(k) > 1})}")
    return dict(pairs)


def _parse(text):
    """JSON without silent last-wins duplicate keys."""
    return json.loads(text, object_pairs_hook=_no_duplicate_keys)


def _fingerprint(value):
    """Digest of the canonical JSON form, stable across re-serialisation."""
    return _sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def _load(directory):
    directory = Path(directory)
    load = lambda name: _parse((directory / name).read_text(encoding="utf-8"))
    bundle = {name: load(f"{name}.json") for name in ("contract", "runs", "judgments", "summary")}
    bundle["e5"] = load("e5.json") if (directory / "e5.json").is_file() else None
    bundle["contract_sha256"] = _fingerprint(bundle["contract"])
    bundle["runs_sha256"] = _sha256("\n".join(sorted(_sha256(run["result"]) for run in bundle["runs"]["runs"])))
    return bundle


def _is_amount(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < float("inf")


def _check_run(run, errors):
    rid = run["id"]
    if not run["served_model"] or run["is_error"]:
        errors.append(f"{rid}: failed run")
    if run.get("stop_reason") != "end_turn":
        errors.append(f"{rid}: stop_reason {run.get('stop_reason')!r} is not a normal completion")
    if not _is_amount(run.get("total_cost_usd")):
        errors.append(f"{rid}: unmetered run; total_cost_usd must be a non-negative number")
    unavailable = run.get("unavailable", {})
    for field, reason in unavailable.items():
        if field not in USAGE_FIELDS or run.get(field) is not None or not isinstance(reason, str) or not reason.strip():
            errors.append(f"{rid}: 'unavailable' may only give a non-empty reason for a usage field recorded as null ({field})")
    for field in USAGE_FIELDS:
        if field not in run:
            errors.append(f"{rid}: {field} missing; record a number, or null with its reason under 'unavailable'")
        elif run[field] is None and field not in unavailable:
            errors.append(f"{rid}: {field} is null without a reason under 'unavailable'")
        elif run[field] is not None and not _is_amount(run[field]):
            errors.append(f"{rid}: {field} is not a non-negative number")


def _expected_runs(contract, judges):
    """Run id -> fields fixed by the contract, before the task runs are known."""
    expected = {}
    for case in contract["cases"]:
        for arm in ("empty", "source"):
            expected[f"S-{case}-{arm}"] = {"kind": "screen", "case": case, "arm": arm}
    for arm, prefix in AUTHOR_ARMS.items():
        for rep in AUTHOR_REPS:
            expected[f"{prefix}-{rep}"] = {"kind": "author", "arm": arm, "rep": rep}
    for judge in judges.values():
        expected[judge] = {"kind": "judge"}
    return expected


def _expected_task_runs(discriminating, fidelity):
    """value_rules.B: A1 run 1 on every discriminating case; a base arm's run 1 only
    when its fidelity verdict differs from A1 run 1."""
    arms = ["A1"] + [arm for arm in BASE_ARMS if fidelity[f"{AUTHOR_ARMS[arm]}-1"] != fidelity["A1-1"]]
    return {f"B-{case}-{AUTHOR_ARMS[arm]}": {"kind": "task", "case": case, "arm": arm} for arm in arms for case in discriminating}


def _check_verdict(verdict, run, contract, errors):
    key = (verdict["judge"], verdict["run"])
    if verdict["overall"] not in ("pass", "fail"):
        errors.append(f"{key}: overall {verdict['overall']!r} is not pass/fail; unverified or unscored judgments cannot be counted")
    if any(c["verdict"] not in ("pass", "fail") for c in verdict["criteria"]):
        errors.append(f"{key}: a criterion verdict is not pass/fail")
    all_pass = all(c["verdict"] == "pass" for c in verdict["criteria"])
    if (verdict["overall"] == "pass") != all_pass:
        errors.append(f"{key}: overall verdict disagrees with its criteria")
    if run["kind"] == "author":
        required, extra = contract["fidelity_gate"], 0
    else:
        required, extra = contract["b_rubric"].get(run.get("case"), []), 1  # the extra one is b_common
    scored = [c["criterion"] for c in verdict["criteria"]]
    # A criterion may be scored under its full contract text or its id ("F1" for "F1: ...").
    covered = [c for c in required if c in scored or c.split(":", 1)[0] in scored]
    if len(scored) != len(set(scored)) or len(scored) != len(required) + extra or len(covered) != len(required):
        errors.append(f"{key}: criteria do not match the contract ({len(scored)} scored, {len(required) + extra} required)")
    elif extra:
        # b_common reads "every case: <clause> (<examples>) ..."; the judges scored it under the
        # clause with varying examples, optionally prefixed "common: ".
        clause = contract["b_common"].split(": ", 1)[-1].split(" (", 1)[0]
        common = [c for c in scored if c not in required and c.split(":", 1)[0] not in [r.split(":", 1)[0] for r in required]]
        if len(common) != 1 or not common[0].removeprefix("common: ").startswith(clause):
            errors.append(f"{key}: the extra criterion is not the contract's common criterion ({common})")


def _check_transcription(judged, by_id, errors):
    """Every verdict is a verbatim copy of an entry in the judge's recorded output,
    the blind map points that entry at the verdict's run, and no entry is dropped."""
    outputs = {}
    for judge, mapping in judged["blind_maps"].items():
        try:
            entries = _parse(by_id[judge]["result"])["judgments"]
            if len({e["id"] for e in entries}) != len(entries):
                raise ValueError("duplicate judgment ids")
            outputs[judge] = {entry["id"]: entry for entry in entries}
        except (KeyError, ValueError, TypeError):
            errors.append(f"{judge}: recorded judge output is not a judgments document with unique ids")
            outputs[judge] = {}
    transcribed = {judge: set() for judge in outputs}
    for verdict in judged["verdicts"]:
        judge, blind_id = verdict["judge"], verdict.get("blind_id")
        entry = outputs.get(judge, {}).get(blind_id)
        if judged["blind_maps"].get(judge, {}).get(blind_id) != verdict["run"]:
            errors.append(f"{(judge, verdict['run'])}: blind map does not point {blind_id!r} at this run")
        if entry is None or entry["overall"] != verdict["overall"] or entry["criteria"] != verdict["criteria"]:
            errors.append(f"{(judge, verdict['run'])}: verdict is not transcribed from the judge output entry {blind_id!r}")
        transcribed.setdefault(judge, set()).add(blind_id)
    for judge, entries in outputs.items():
        for blind_id in entries.keys() - transcribed[judge]:
            errors.append(f"{judge}: output entry {blind_id!r} has no verdict")


def _package():
    """Current work-to-skill files, or None when they are not where this checkout keeps them."""
    try:
        return {name: (PACKAGE_DIR / name).read_text(encoding="utf-8") for name in PACKAGE_FILES}
    except OSError:
        return None


def prompts(bundle):
    """Rebuild each recorded prompt from the contract, following runs.json 'composition'.

    None marks a prompt the bundle cannot rebuild: A-guide runs (guide kept as a
    digest only), judge runs (blinded responses), and A1 runs when the checkout's
    package no longer matches the contract's package digests.
    """
    contract, runs = bundle["contract"], bundle["runs"]
    package = _package()
    package_ok = package is not None and {n: _sha256(t) for n, t in package.items()} == contract["package_digests"]
    rebuilt = {}
    for run in runs["runs"]:
        kind, text = run["kind"], None
        if kind == "screen" and run.get("case") in contract["cases"]:
            material = "\n\nSupplied review material:\n" + contract["source"] if run.get("arm") == "source" else ""
            text = contract["review_request"] + contract["cases"][run["case"]] + material
        elif kind == "task" and run.get("case") in contract["cases"] and run.get("arm") in runs["generated_skills"]:
            text = contract["review_request"] + contract["cases"][run["case"]] + "\n\nSupplied review material:\n" + runs["generated_skills"][run["arm"]]["text"]
        elif kind == "author" and run.get("arm") == "A0":
            text = contract["author_request"]
        elif kind == "author" and run.get("arm") == "A1" and package_ok:
            text = contract["author_request"] + (
                "\n\nUse this supplied authoring skill package:\n<SKILL.md>\n" + package["SKILL.md"]
                + "\n</SKILL.md>\n<references/validation.md>\n" + package["references/validation.md"] + "\n</references/validation.md>"
            )
        rebuilt[run["id"]] = text
    return rebuilt


def _check_prompts(bundle, by_id, errors):
    for rid, text in prompts(bundle).items():
        if text is not None and (_sha256(text) != by_id[rid]["prompt_sha256"] or len(text) != by_id[rid]["prompt_chars"]):
            errors.append(f"{rid}: recorded prompt digest does not match the prompt rebuilt from the contract")


def _check_generated_skills(runs, task_arms, by_id, errors):
    """Each generated skill names the run-1 authoring run of its arm and is quoted from that run's output."""
    generated = runs["generated_skills"]
    for arm in task_arms:
        if arm not in generated:
            errors.append(f"generated_skills[{arm}]: missing for an arm with task runs")
    for arm, skill in generated.items():
        source = by_id.get(skill.get("from"))
        if source is None or source["kind"] != "author" or source.get("arm") != arm or source.get("rep") != 1:
            errors.append(f"generated_skills[{arm}]: 'from' {skill.get('from')!r} is not the run-1 authoring run of arm {arm}")
        elif skill.get("text") not in source["result"]:
            errors.append(f"generated_skills[{arm}]: text is not quoted from run {skill['from']}")


def _check_e5(e5, contract_e5, errors):
    expected, actual = contract_e5["requests"], e5["requests"]
    for key in sorted(expected.keys() - actual.keys()):
        errors.append(f"e5 {key}: request required by the contract was not run")
    for key in sorted(actual.keys() - expected.keys()):
        errors.append(f"e5 {key}: request not in the contract")
    for key in sorted(expected.keys() & actual.keys()):
        entry = actual[key]
        if entry.get("request") != expected[key] or entry.get("expected") != contract_e5["expected"].get(key):
            errors.append(f"e5 {key}: request or expectation differs from the contract")
        skills = entry.get("skills")
        if not isinstance(skills, list) or not all(isinstance(s, str) for s in skills):
            errors.append(f"e5 {key}: 'skills' must be the list of skill names the host invoked")
        if not entry.get("subtype") or not entry.get("model") or not _is_amount(entry.get("cost")):
            errors.append(f"e5 {key}: missing completion status, model, or cost")


def summarize(directory):
    """Return (summary, errors) recomputed from the evidence files."""
    bundle = _load(directory)
    contract, runs, judged = bundle["contract"], bundle["runs"], bundle["judgments"]
    judges = bundle["summary"]["judges"]
    errors = []

    ids = [run["id"] for run in runs["runs"]]
    if len(ids) != len(set(ids)):
        errors.append("duplicate run ids")
    by_id = {run["id"]: run for run in runs["runs"]}
    for run in runs["runs"]:
        _check_run(run, errors)
    expected = _expected_runs(contract, judges)
    task_ids = [r["id"] for r in runs["runs"] if r["kind"] == "task"]
    prefixes = {prefix: arm for arm, prefix in AUTHOR_ARMS.items()}
    for rid in task_ids:  # B-<case>-<arm prefix>; which task runs are due is settled after screening
        parts = rid.split("-")
        if len(parts) == 3 and parts[0] == "B" and parts[2] in prefixes:
            expected[rid] = {"kind": "task", "case": parts[1], "arm": prefixes[parts[2]]}
    for rid, fields in expected.items():
        if rid not in by_id:
            errors.append(f"{rid}: run required by the contract is missing")
        elif any(by_id[rid].get(k) != v for k, v in fields.items()):
            errors.append(f"{rid}: run fields disagree with its id, expected {fields}")
    for rid in by_id.keys() - expected.keys():
        errors.append(f"{rid}: run not called for by the contract")

    verdicts = {}
    for verdict in judged["verdicts"]:
        key = (verdict["judge"], verdict["run"])
        if verdict["run"] not in by_id:
            errors.append(f"{key}: verdict for unknown run")
            continue
        if key in verdicts:
            errors.append(f"{key}: duplicate verdict")
        _check_verdict(verdict, by_id[verdict["run"]], contract, errors)
        verdicts[key] = verdict["overall"]
    _check_transcription(judged, by_id, errors)

    def runs_of(kind, **fields):
        return [r["id"] for r in runs["runs"] if r["kind"] == kind and all(r.get(k) == v for k, v in fields.items())]

    required = [(judges["screen"], r) for r in runs_of("screen")]
    required += [(judges["fidelity"], r) for r in runs_of("author")]
    required += [(judges["pair"], r) for r in task_ids]
    cases = list(contract["cases"])
    discriminating = [c for c in cases if verdicts.get((judges["screen"], f"S-{c}-empty")) == "fail"]
    required += [(judges["pair"], f"S-{c}-source") for c in discriminating]
    for key in required:
        if key not in verdicts:
            errors.append(f"{key}: missing verdict")
    if errors:
        return None, errors

    fidelity = {r: verdicts[(judges["fidelity"], r)] for r in runs_of("author")}
    expected_tasks = _expected_task_runs(discriminating, fidelity)
    for rid, fields in expected_tasks.items():
        if rid not in by_id:
            errors.append(f"{rid}: task run required by the contract is missing")
        elif any(by_id[rid].get(k) != v for k, v in fields.items()):
            errors.append(f"{rid}: run fields disagree with its id, expected {fields}")
    for rid in set(task_ids) - expected_tasks.keys():
        errors.append(f"{rid}: task run not called for by the contract (case not discriminating, or the arm's run-1 fidelity equals A1's)")
    task_arms = sorted({by_id[r]["arm"] for r in task_ids})
    _check_generated_skills(runs, task_arms, by_id, errors)
    _check_prompts(bundle, by_id, errors)
    if "e5" in contract and bundle["e5"] is None:
        errors.append("e5.json: host selection check required by the contract is missing")
    elif bundle["e5"] is not None:
        _check_e5(bundle["e5"], contract.get("e5", {"requests": {}, "expected": {}}), errors)
    if errors:
        return None, errors

    generated = {}
    for arm in task_arms:
        arm_runs = [f"B-{c}-{AUTHOR_ARMS[arm]}" for c in discriminating]
        pairs = _pairs(verdicts, judges["pair"], arm_runs, [f"S-{c}-source" for c in discriminating])
        generated[arm] = {**pairs, "decision": decide(pairs["wins"], pairs["losses"], len(discriminating))}

    creator = {}
    for base in BASE_ARMS:
        a1 = [f"A1-{rep}" for rep in AUTHOR_REPS]
        pairs = _pairs(verdicts, judges["fidelity"], a1, [f"{AUTHOR_ARMS[base]}-{rep}" for rep in AUTHOR_REPS])
        creator[f"A1 vs {base}"] = {**pairs, "decision": decide(pairs["wins"], pairs["losses"], len(AUTHOR_REPS))}

    calls, cost = len(runs["runs"]), sum(r["total_cost_usd"] for r in runs["runs"])
    summary = {
        "contract_sha256": bundle["contract_sha256"],
        "runs_sha256": bundle["runs_sha256"],
        "judges": judges,
        "discriminating_cases": discriminating,
        "fidelity": fidelity,
        "generated_skill_vs_source": generated,
        "creator": creator,
    }
    if bundle["e5"] is not None:
        requests = bundle["e5"]["requests"]
        summary["e5"] = _e5_summary(requests)
        calls += len(requests)
        cost += sum(v["cost"] for v in requests.values())
    summary.update(calls=calls, cost_usd=round(cost, 2))
    return summary, errors


def _e5_summary(requests):
    """Host selection counts; P = should select work-to-skill, N/J = should not.

    Selection is read from the recorded Skill events, so it is valid even when the
    request later stopped without completing; those requests are listed under
    'incomplete' and are not counted as task completions.
    """
    selected = {k: "work-to-skill" in v["skills"] for k, v in requests.items()}
    positive = [k for k in requests if k.startswith("P")]
    result = {
        "positive_selected": sum(selected[k] for k in positive),
        "positive_total": len(positive),
        "negative_false": sum(selected[k] for k in requests if k.startswith("N")),
        "adjacent_false": sum(selected[k] for k in requests if k.startswith("J")),
        "missed": [k for k in positive if not selected[k]],
        "incomplete": [k for k, v in requests.items() if v["subtype"] != E5_COMPLETED],
    }
    result["pass"] = result["positive_selected"] >= E5_POSITIVE_MIN and result["negative_false"] == 0
    return result


def pooled(summaries):
    """Sum discordant pairs across distinct bundles; each bundle's own counts stay reportable.

    Returns (result, errors). Two bundles with the same contract content, or the same
    set of run outputs, are the same evidence: pooling it twice would inflate the pair
    count toward the no-value threshold.
    """
    errors = []
    for field, label in (("contract_sha256", "contract"), ("runs_sha256", "run outputs")):
        digests = [s[field] for s in summaries]
        for digest in sorted({d for d in digests if digests.count(d) > 1}):
            errors.append(f"{label} {digest[:12]} pooled {digests.count(digest)} times")
    result = {}
    comparisons = [("generated_skill_vs_source", "A1")] + [("creator", key) for key in ("A1 vs A0", "A1 vs A-guide")]
    for section, key in comparisons:
        parts = [s[section][key] for s in summaries if key in s[section]]
        wins = sum(p["wins"] for p in parts)
        losses = sum(p["losses"] for p in parts)
        cases = sum(p["wins"] + p["losses"] + p["ties"] for p in parts)
        result[f"{section}: {key}"] = {"wins": wins, "losses": losses, "pairs": cases, "decision": decide(wins, losses, cases)}
    return result, errors


def check(directory):
    summary, errors = summarize(directory)
    if summary is not None:
        stored = _parse((Path(directory) / "summary.json").read_text(encoding="utf-8"))
        for key in sorted(stored.keys() | summary.keys()):
            if stored.get(key) != summary.get(key):
                errors.append(f"summary.json {key} disagrees with recomputed value {summary.get(key)!r}")
    return summary, errors


if __name__ == "__main__":
    all_summaries, problems = [], []
    for path in sys.argv[1:]:
        result, errors = check(path)
        print(Path(path).name, json.dumps(result, indent=2))
        unverified = sorted(rid for rid, text in prompts(_load(path)).items() if text is None)
        print(Path(path).name, "prompts not rebuilt from the bundle:", ", ".join(unverified) or "none")
        all_summaries.append(result)
        problems += [f"{Path(path).name}: {e}" for e in errors]
    if len(all_summaries) > 1 and not problems:
        result, errors = pooled(all_summaries)
        print("pooled", json.dumps(result, indent=2))
        problems += [f"pooled: {e}" for e in errors]
    for problem in problems:
        print("ERROR:", problem, file=sys.stderr)
    sys.exit(1 if problems else 0)
