"""Check evaluation evidence directories and recompute their decisions.

Usage: python tests/behavior/evaluate.py tests/behavior/evidence/<eval-dir> [...]

Each directory holds contract.json (frozen before the runs), runs.json,
judgments.json, summary.json, and e5.json when host selection was checked.
With several directories the discordant pairs are also pooled. Model runs happen
outside this script with the host CLI recorded in the contract. This script only
checks that the recorded runs, verdicts, and decisions agree; passing it says
nothing about whether a verdict is semantically right.
"""

import json
import sys
from pathlib import Path

VALUE_WINS = 5
NO_VALUE_MIN_CASES = 10
E5_POSITIVE_MIN = 4


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


def summarize(directory):
    """Return (summary, errors) recomputed from the evidence files."""
    directory = Path(directory)
    load = lambda name: json.loads((directory / name).read_text(encoding="utf-8"))
    contract, runs, judged = (load(n) for n in ("contract.json", "runs.json", "judgments.json"))
    e5 = load("e5.json") if (directory / "e5.json").is_file() else None
    judges = load("summary.json")["judges"]
    errors = []

    ids = [run["id"] for run in runs["runs"]]
    if len(ids) != len(set(ids)):
        errors.append("duplicate run ids")
    by_id = {run["id"]: run for run in runs["runs"]}
    for run in runs["runs"]:
        if not run["served_model"] or run["is_error"] or not isinstance(run["total_cost_usd"], (int, float)):
            errors.append(f"{run['id']}: failed or unmetered run")

    verdicts = {}
    for verdict in judged["verdicts"]:
        key = (verdict["judge"], verdict["run"])
        if verdict["run"] not in by_id:
            errors.append(f"{key}: verdict for unknown run")
        if key in verdicts:
            errors.append(f"{key}: duplicate verdict")
        if verdict["overall"] == "pass" and any(c["verdict"] != "pass" for c in verdict["criteria"]):
            errors.append(f"{key}: pass with a non-passing required criterion")
        verdicts[key] = verdict["overall"]

    def runs_of(kind, **fields):
        return [r["id"] for r in runs["runs"] if r["kind"] == kind and all(r.get(k) == v for k, v in fields.items())]

    required = [(judges["screen"], r) for r in runs_of("screen")]
    required += [(judges["fidelity"], r) for r in runs_of("author")]
    required += [(judges["pair"], r) for r in runs_of("task")]
    cases = list(contract["cases"])
    discriminating = [c for c in cases if verdicts.get((judges["screen"], f"S-{c}-empty")) == "fail"]
    required += [(judges["pair"], f"S-{c}-source") for c in discriminating]
    for key in required:
        if key not in verdicts:
            errors.append(f"{key}: missing verdict")
    if errors:
        return None, errors

    for run in runs_of("task"):
        if by_id[run]["case"] not in discriminating:
            errors.append(f"{run}: skill arm run on a non-discriminating case")

    task_arms = sorted({by_id[r]["arm"] for r in runs_of("task")})
    generated = {}
    for arm in task_arms:
        arm_cases = [c for c in discriminating if f"B-{c}-{arm}" in by_id]
        pairs = _pairs(verdicts, judges["pair"], [f"B-{c}-{arm}" for c in arm_cases], [f"S-{c}-source" for c in arm_cases])
        generated[arm] = {**pairs, "decision": decide(pairs["wins"], pairs["losses"], len(discriminating))}

    fidelity = {r: verdicts[(judges["fidelity"], r)] for r in runs_of("author")}
    creator = {}
    for base in ("A0", "A-guide"):
        reps = sorted(by_id[r]["rep"] for r in runs_of("author", arm=base))
        a1 = [r for rep in reps for r in runs_of("author", arm="A1", rep=rep)]
        pairs = _pairs(verdicts, judges["fidelity"], a1, [r for rep in reps for r in runs_of("author", arm=base, rep=rep)])
        creator[f"A1 vs {base}"] = {**pairs, "decision": decide(pairs["wins"], pairs["losses"], len(reps))}

    model_cost = sum(r["total_cost_usd"] for r in runs["runs"])
    summary = {
        "judges": judges,
        "discriminating_cases": discriminating,
        "fidelity": fidelity,
        "generated_skill_vs_source": generated,
        "creator": creator,
        "calls": len(runs["runs"]),
        "cost_usd": round(model_cost, 2),
    }
    if e5 is not None:
        requests = e5["requests"]
        summary["e5"] = _e5_summary(requests)
        summary["calls"] += len(requests)
        summary["cost_usd"] = round(model_cost + sum(v["cost"] for v in requests.values()), 2)
    return summary, errors


def _e5_summary(requests):
    """Host selection counts; P = should select work-to-skill, N/J = should not."""
    selected = {k: "work-to-skill" in v["skills"] for k, v in requests.items()}
    positive = [k for k in requests if k.startswith("P")]
    result = {
        "positive_selected": sum(selected[k] for k in positive),
        "positive_total": len(positive),
        "negative_false": sum(selected[k] for k in requests if k.startswith("N")),
        "adjacent_false": sum(selected[k] for k in requests if k.startswith("J")),
        "missed": [k for k in positive if not selected[k]],
    }
    result["pass"] = result["positive_selected"] >= E5_POSITIVE_MIN and result["negative_false"] == 0
    return result


def pooled(summaries):
    """Sum discordant pairs across bundles; each bundle's own counts stay reportable."""
    result = {}
    comparisons = [("generated_skill_vs_source", "A1")] + [("creator", key) for key in ("A1 vs A0", "A1 vs A-guide")]
    for section, key in comparisons:
        parts = [s[section][key] for s in summaries if key in s[section]]
        wins = sum(p["wins"] for p in parts)
        losses = sum(p["losses"] for p in parts)
        cases = sum(p["wins"] + p["losses"] + p["ties"] for p in parts)
        result[f"{section}: {key}"] = {"wins": wins, "losses": losses, "pairs": cases, "decision": decide(wins, losses, cases)}
    return result


def check(directory):
    summary, errors = summarize(directory)
    if summary is not None:
        stored = json.loads((Path(directory) / "summary.json").read_text(encoding="utf-8"))
        for key, value in summary.items():
            if stored.get(key) != value:
                errors.append(f"summary.json {key} disagrees with recomputed value {value!r}")
    return summary, errors


if __name__ == "__main__":
    all_summaries, problems = [], []
    for path in sys.argv[1:]:
        result, errors = check(path)
        print(Path(path).name, json.dumps(result, indent=2))
        all_summaries.append(result)
        problems += [f"{Path(path).name}: {e}" for e in errors]
    if len(all_summaries) > 1 and not problems:
        print("pooled", json.dumps(pooled(all_summaries), indent=2))
    for problem in problems:
        print("ERROR:", problem, file=sys.stderr)
    sys.exit(1 if problems else 0)
