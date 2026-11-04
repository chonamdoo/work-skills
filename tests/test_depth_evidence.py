import copy
import hashlib
import json
import re
import statistics
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "behavior"))

import evaluate  # noqa: E402

EVIDENCE = ROOT / "tests" / "behavior" / "evidence" / "depth-2026-11-04"
DOC = ROOT / "docs" / "evaluation-2026-11-04-depth.md"
FILES = ("plan", "addendum-baseline", "addendum-2", "runs", "judgments", "addendum-runs", "addendum-2-runs",
         "addendum-2-judgments", "addendum-2-secondary-baseline", "posthoc-proposal-activation", "results")
PREREGISTERED = ("plan", "addendum-baseline", "addendum-2")
RUN_FILES = ("runs", "addendum-runs", "addendum-2-runs")
PRIMARY_MODEL = "claude-fable-5-1"
VERDICTS = ("pass", "fail")
DEPTH = {"D": ("D1", "D2", "D3"), "X1": ("X1", "X2", "X3"), "X2": ("Y1", "Y2", "Y3")}
GUARD_CASES = ("D", "X1", "X2")
SCREEN_FAILS = 2
SCOPE_INDEX = 5
FIDELITY_INDEXES = (3, 4, 6)
FIDELITY_MARGIN = 2
R_FAILS = 2
COST_ARMS = ("Abase", "Abase+F", "Amain", "Amin")
FENCED = re.compile(r"```json\n(.*)\n```", re.S)
ARM = r"(?:Abase\+F|Abase|Amain|Amin|A0|A1|A2)"
ARM_COUNTS = re.compile(rf"({ARM}) (\d+)/(\d+)")
CRITERION_CLAIM = re.compile(rf"\b([A-Z]\d):? ((?:{ARM} \d+/\d+(?:, )?)+)")
MISSING = object()


def _sha256(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def load(directory=EVIDENCE, doc=DOC):
    bundle = {name: evaluate._parse((directory / f"{name}.json").read_text(encoding="utf-8")) for name in FILES}
    bundle["raw"] = {name: (directory / f"{name}.json").read_bytes() for name in PREREGISTERED}
    bundle["digests"] = {name: (directory / f"{name}.sha256").read_text(encoding="utf-8") for name in PREREGISTERED}
    bundle["doc"] = doc.read_text(encoding="utf-8")
    return bundle


def read_judgment(text):
    match = FENCED.fullmatch(text)
    data = evaluate._parse(match.group(1) if match else text)
    if not isinstance(data, dict) or list(data) != ["criteria"] or not isinstance(data["criteria"], list):
        raise ValueError("not a criteria document")
    if not all(isinstance(c, dict) for c in data["criteria"]):
        raise ValueError("criteria entries are not objects")
    return data["criteria"]


def package_prompt(request, skill, validation):
    return (request + "\n\nUse this supplied authoring skill package:\n<SKILL.md>\n" + skill
            + "\n</SKILL.md>\n<references/validation.md>\n" + validation + "\n</references/validation.md>")


def felix_suffix(felix):
    return "\n\nAlso apply this instruction from the requester's prompting guide:\n<guide>\n" + felix + "\n</guide>"


def generated_skill(text):
    start = re.search(r"(?m)^---[ \t]*\n(?=name:)", text) or re.search(r"(?m)^---[ \t]*\n", text)
    if start is None:
        return None
    close = re.search(r"(?m)^---[ \t]*$", text[start.end():])
    if close is None:
        return None
    header = text[start.end():start.end() + close.start()]
    skill = text[start.start():]
    fence = re.search(r"(?m)^```[ \t]*$", skill)
    if fence:
        skill = skill[:fence.start()]
    return header, len(skill.split())


def unquoted_colon_description(header):
    for line in header.splitlines():
        if line.startswith("description:"):
            value = line[len("description:"):].strip()
            return bool(value) and value[0] not in "\"'|>" and ": " in value
    return False


def cases_of(bundle, errors):
    cases = {}
    for case, spec in bundle["plan"]["cases"].items():
        cases[case] = (spec["request"], [c.split(":", 1)[0] for c in spec["criteria"]])
    for case, spec in bundle["addendum-2"]["cases"].items():
        if "criteria" in spec:
            cases[case] = (spec["request"], [c.split(":", 1)[0] for c in spec["criteria"]])
        elif spec.get("from") != "plan.json" or case not in bundle["plan"]["cases"]:
            errors.append(f"addendum-2.json case {case}: neither defines criteria nor reuses a plan.json case")
    for case, (_, ids) in cases.items():
        if len(ids) != len(set(ids)):
            errors.append(f"case {case}: criterion ids are not unique {ids}")
    return cases


def planned_runs(bundle):
    def expand(arms_by_case):
        return [f"{case}-{arm}-{rep}" for case, arms in arms_by_case for arm, n in arms.items() for rep in range(1, n + 1)]

    baseline = bundle["addendum-baseline"]
    return {
        "runs": expand((c, s["arms"]) for c, s in bundle["plan"]["cases"].items()),
        "addendum-runs": expand((c, {arm: n for arm in baseline["new_arms"]}) for c, n in baseline["runs_per_arm"].items()),
        "addendum-2-runs": expand((c, s["arms"]) for c, s in bundle["addendum-2"]["cases"].items()),
    }


def check_digests(bundle, errors):
    for name in PREREGISTERED:
        parts = bundle["digests"][name].split()
        if len(parts) != 2 or parts[1] != f"{name}.json":
            errors.append(f"{name}.sha256: not a '<sha256>  {name}.json' record")
            continue
        actual = _sha256(bundle["raw"][name])
        if actual != parts[0]:
            errors.append(f"{name}.json: sha256 {actual} does not match {name}.sha256 {parts[0]}")
        if evaluate._parse(bundle["raw"][name].decode("utf-8")) != bundle[name]:
            errors.append(f"{name}.json: parsed content differs from the digested bytes")
    amin = bundle["addendum-2"]["arms"]["Amin"]
    for text, digest in (("SKILL.md_text", "SKILL.md"), ("validation.md_text", "references/validation.md")):
        if _sha256(amin[text]) != amin[digest]:
            errors.append(f"addendum-2.json Amin {text}: sha256 does not match the recorded {digest} digest")
    for arm, digests in bundle["addendum-baseline"]["new_arms"].items():
        if digests != bundle["addendum-2"]["arms"].get(arm):
            errors.append(f"{arm}: package digests differ between addendum-baseline.json and addendum-2.json")


def check_runs(bundle, errors):
    runs = {}
    for name, planned in planned_runs(bundle).items():
        recorded = Counter(run["id"] for run in bundle[name]["runs"])
        for rid in planned:
            if not recorded[rid]:
                errors.append(f"{name}.json: planned run {rid} is missing")
        for rid, n in recorded.items():
            if rid not in planned:
                errors.append(f"{name}.json: run {rid} is not in the pre-registered plan")
            if n > 1:
                errors.append(f"{name}.json: run {rid} recorded {n} times")
        for run in bundle[name]["runs"]:
            if run["id"] in runs and runs[run["id"]] is not run:
                errors.append(f"{name}.json: run {run['id']} also recorded in another run file")
            runs.setdefault(run["id"], run)
            _check_run(run, errors)
    return runs


def _check_run(run, errors):
    rid = run["id"]
    if not isinstance(run["rep"], int) or rid != f"{run['case']}-{run['arm']}-{run['rep']}":
        errors.append(f"{rid}: run fields disagree with its id")
    if run["kind"] != "author" or run["system"] != "author_system":
        errors.append(f"{rid}: not an author run with the author system prompt")
    if (run["stop_reason"], run["is_error"], run["terminal_reason"]) != ("end_turn", False, "completed"):
        errors.append(f"{rid}: truncated or failed run (stop_reason {run['stop_reason']!r}, "
                      f"is_error {run['is_error']!r}, terminal_reason {run['terminal_reason']!r})")
    if run["served_model"] != [PRIMARY_MODEL]:
        errors.append(f"{rid}: served by {run['served_model']}, not {PRIMARY_MODEL}")
    if not isinstance(run["result"], str) or not run["result"].strip():
        errors.append(f"{rid}: empty author output")
    for field in evaluate.USAGE_FIELDS:
        if not evaluate._is_amount(run.get(field)):
            errors.append(f"{rid}: {field} is not a non-negative number")
    if not evaluate._is_amount(run.get("total_cost_usd")) or not run["total_cost_usd"] > 0:
        errors.append(f"{rid}: unmetered run")


def check_prompts(bundle, runs, cases, errors):
    amin = bundle["addendum-2"]["arms"]["Amin"]
    overhead, digests = {}, {}
    for rid, run in runs.items():
        request = cases[run["case"]][0]
        rebuilt = None
        if run["arm"] == "A0":
            rebuilt = request
        elif run["arm"] == "Amin":
            rebuilt = package_prompt(request, amin["SKILL.md_text"], amin["validation.md_text"])
        if rebuilt is not None and (_sha256(rebuilt) != run["prompt_sha256"] or len(rebuilt) != run["prompt_chars"]):
            errors.append(f"{rid}: recorded prompt does not match the prompt rebuilt from the pre-registration")
        overhead.setdefault(run["arm"], set()).add(run["prompt_chars"] - len(request))
        digests.setdefault((run["case"], run["arm"]), set()).add(run["prompt_sha256"])
    for arm, values in overhead.items():
        if len(values) != 1:
            errors.append(f"{arm}: prompt length beyond the case request differs across runs {sorted(values)}")
    for (case, arm), values in digests.items():
        if len(values) != 1:
            errors.append(f"{case}-{arm}: reps of one arm were given different prompts")
    by_case = {}
    for (case, arm), values in digests.items():
        for digest in values:
            by_case.setdefault((case, digest), []).append(arm)
    for (case, _), arms in by_case.items():
        if len(arms) > 1:
            errors.append(f"case {case}: arms {sorted(arms)} were given the same prompt")
    plus, base = overhead.get("Abase+F", set()), overhead.get("Abase", set())
    suffix = felix_suffix(bundle["addendum-2"]["arms"]["Abase+F"]["FELIX"])
    if len(plus) == 1 and len(base) == 1 and next(iter(plus)) - next(iter(base)) != len(suffix):
        errors.append(f"Abase+F: prompt is not the Abase prompt plus the {len(suffix)}-character four-question suffix")


def judge_batches(bundle, runs):
    a2_runs = [r["id"] for r in bundle["addendum-2-runs"]["runs"]]
    baseline_runs = [r["id"] for r in bundle["addendum-runs"]["runs"]]
    plan_runs = [r["id"] for r in bundle["runs"]["runs"]]
    a0_runs = [rid for rid in plan_runs if runs.get(rid, {}).get("arm") == "A0"]
    j2, sb = bundle["addendum-2-judgments"], bundle["addendum-2-secondary-baseline"]
    return (
        ("judgments.json", "primary", "J-", bundle["judgments"]["judges"], bundle["judgments"]["blind_map"], plan_runs),
        ("addendum-runs.json", "primary", "J-", bundle["addendum-runs"]["judges"], bundle["addendum-runs"]["blind_map"], baseline_runs),
        ("addendum-2-judgments.json primary", "primary", "J-", j2["primary"], j2["blind_map"], a2_runs),
        ("addendum-2-judgments.json secondary", "secondary", "K-", j2["secondary"], j2["blind_map"], a2_runs),
        ("addendum-2-secondary-baseline.json", "secondary", "K-", sb["secondary"], sb["blind_map"], a0_runs + baseline_runs),
    )


def _check_judge_record(rec, judge, kind, run, blind, secondary_model, bindings, errors):
    if judge == "primary":
        expected = {"kind": kind, "system": "judge_system", "served_model": [PRIMARY_MODEL], "stop_reason": "end_turn",
                    "is_error": False, "terminal_reason": "completed", "case": run["case"], "arm": None, "rep": None}
    else:
        expected = {"kind": "judge-secondary", "model_flag": secondary_model, "exit": 0}
    for field, value in expected.items():
        actual = rec.get(field, MISSING)
        if actual != value:
            errors.append(f"{rec['id']} ({run['id']}): {field} {None if actual is MISSING else actual!r}, expected {value!r}")
    if judge == "primary" and (not evaluate._is_amount(rec.get("total_cost_usd")) or not rec["total_cost_usd"] > 0):
        errors.append(f"{rec['id']}: unmetered judge call")
    if judge == "primary" and not isinstance(rec.get("prompt_chars"), int):
        errors.append(f"{rec['id']} ({run['id']}): prompt_chars missing, so the record cannot be bound to the run output")
    elif judge == "primary":
        template = rec["prompt_chars"] - len(run["result"]) - len(blind)
        bindings.setdefault((kind, run["case"]), {}).setdefault(template, []).append(f"{rec['id']} ({run['id']})")


def _check_bindings(bindings, errors):
    for (kind, case), templates in bindings.items():
        if len(templates) > 1:
            usual = max(templates, key=lambda t: len(templates[t]))
            odd = sorted(r for t, recs in templates.items() if t != usual for r in recs)
            errors.append(f"{kind} {case}: judge prompt length does not fit the judged run output for {odd}")


def check_judgments(bundle, runs, cases, errors):
    secondary_model = re.search(r"-m (\S+)", bundle["addendum-2"]["judges"]["secondary"]).group(1)
    maps = {"judgments.json": bundle["judgments"]["blind_map"], "addendum-runs.json": bundle["addendum-runs"]["blind_map"],
            "addendum-2-judgments.json": bundle["addendum-2-judgments"]["blind_map"],
            "addendum-2-secondary-baseline.json": bundle["addendum-2-secondary-baseline"]["blind_map"]}
    owners = Counter(blind for blind_map in maps.values() for blind in blind_map)
    for blind, n in owners.items():
        if n > 1:
            errors.append(f"blind id {blind} is used in {n} blind maps")
    verdicts, bindings = {"primary": {}, "secondary": {}}, {}
    for label, judge, prefix, records, blind_map, expected in judge_batches(bundle, runs):
        mapped = Counter(blind_map.values())
        for rid in expected:
            if not mapped[rid]:
                errors.append(f"{label}: run {rid} has no blind id")
        for rid, n in mapped.items():
            if rid not in expected:
                errors.append(f"{label}: blind map names {rid}, which is not a run of this batch")
            elif n > 1:
                errors.append(f"{label}: run {rid} has {n} blind ids")
        judged = Counter(rec["id"][len(prefix):] if rec["id"].startswith(prefix) else rec["id"] for rec in records)
        for blind in blind_map:
            if judged[blind] != 1:
                errors.append(f"{label}: blind id {blind} judged {judged[blind]} times")
        for rec in records:
            blind = rec["id"][len(prefix):] if rec["id"].startswith(prefix) else None
            if blind not in blind_map:
                errors.append(f"{label}: {rec['id']} matches no blind id")
                continue
            run = runs.get(blind_map[blind])
            if run is None:
                errors.append(f"{label}: {rec['id']} maps to unrecorded run {blind_map[blind]}")
                continue
            _check_judge_record(rec, judge, "judge", run, blind, secondary_model, bindings, errors)
            _collect(rec, run, cases[run["case"]][1], verdicts[judge], judge, errors)
    _check_bindings(bindings, errors)
    return verdicts


def _collect(rec, run, criteria_ids, sink, judge, errors):
    try:
        criteria = read_judgment(rec["result"])
    except ValueError as exc:
        errors.append(f"{rec['id']} ({run['id']}): judge output is not a criteria document ({exc})")
        return
    ids = [c.get("id") for c in criteria]
    if Counter(ids) != Counter(criteria_ids):
        errors.append(f"{rec['id']} ({run['id']}): criteria {ids} do not equal case {run['case']} criteria {criteria_ids}")
        return
    for criterion in criteria:
        key = (run["id"], criterion["id"])
        if criterion.get("verdict") not in VERDICTS:
            errors.append(f"{rec['id']} ({run['id']}) {criterion['id']}: verdict {criterion.get('verdict')!r} is not pass/fail")
        elif key in sink:
            errors.append(f"{run['id']} {criterion['id']}: judged more than once by the {judge} judge")
        else:
            sink[key] = criterion["verdict"]


class Recount:
    def __init__(self, runs, cases, verdicts, errors):
        self.runs, self.cases, self.verdicts, self.errors = runs, cases, verdicts, errors
        self.case_of = {cid: case for case, (_, ids) in cases.items() for cid in ids}

    def runs_of(self, case, arm):
        return sorted((r for r in self.runs.values() if r["case"] == case and r["arm"] == arm), key=lambda r: r["rep"])

    def passes(self, judge, rid, cid):
        verdict = self.verdicts[judge].get((rid, cid))
        if verdict is None:
            message = f"{judge} judge: no verdict for {rid} {cid}"
            if message not in self.errors:
                self.errors.append(message)
        return verdict == "pass"

    def fails(self, judge, case, arm, cid):
        return sum(not self.passes(judge, r["id"], cid) for r in self.runs_of(case, arm))

    def tallies(self, judge):
        counts = {}
        for (rid, cid), verdict in self.verdicts[judge].items():
            run = self.runs[rid]
            cell = counts.setdefault(f"{run['case']}/{cid}", {}).setdefault(run["arm"], [0, 0])
            cell[0] += verdict == "pass"
            cell[1] += 1
        return {key: {arm: f"{p}/{n}" for arm, (p, n) in arms.items()} for key, arms in counts.items()}

    def screened(self):
        return [[case, cid] for case, ids in DEPTH.items() for cid in ids
                if self.fails("primary", case, "Abase", cid) >= SCREEN_FAILS]

    def compare(self, judge, arm, base):
        wins = losses = 0
        for case, cid in self.screened():
            arm_runs, base_runs = self.runs_of(case, arm), self.runs_of(case, base)
            if [r["rep"] for r in arm_runs] != [r["rep"] for r in base_runs]:
                self.errors.append(f"{case}: {arm} and {base} reps cannot be paired")
                continue
            for a, b in zip(arm_runs, base_runs):
                x, y = self.passes(judge, a["id"], cid), self.passes(judge, b["id"], cid)
                wins += x and not y
                losses += y and not x
        return [wins, losses, evaluate.decide(wins, losses, wins + losses)]

    def guard_trips(self, judge, arm):
        trips = []
        for case in GUARD_CASES:
            ids = self.cases[case][1]
            if not self.runs_of(case, arm):
                trips += [f"unevaluable scope {case}", f"unevaluable fidelity {case}"]
                continue
            if self.fails(judge, case, arm, ids[SCOPE_INDEX]) >= 1:
                trips.append(f"scope {case}/{ids[SCOPE_INDEX]}")
            trips += [f"fidelity {case}/{ids[i]}" for i in FIDELITY_INDEXES if self._worse(judge, case, arm, ids[i])]
        if not self.runs_of("P", arm):
            trips.append("unevaluable fidelity P")
        else:
            trips += [f"fidelity P/{cid}" for cid in self.cases["P"][1] if self._worse(judge, "P", arm, cid)]
        if not self.runs_of("N", arm):
            trips.append("unevaluable N")
        else:
            trips += [f"N N/{cid}" for cid in self.cases["N"][1] if self.fails(judge, "N", arm, cid) >= 1]
        if not self.runs_of("R", arm):
            trips.append("unevaluable R")
        elif self.fails(judge, "R", arm, "R1") >= R_FAILS:
            trips.append("R R/R1")
        return trips

    def _worse(self, judge, case, arm, cid):
        return self.fails(judge, case, arm, cid) - self.fails(judge, case, "Abase", cid) >= FIDELITY_MARGIN

    def scope_fails_in_every_arm(self, judge):
        arms = {self.runs[rid]["arm"] for rid, _ in self.verdicts[judge] if self.runs[rid]["case"] in GUARD_CASES}
        return bool(arms) and all(any(t.startswith("scope") for t in self.guard_trips(judge, arm)) for arm in arms)

    def ship(self, judge):
        for arm in ("Amin", "Amain"):
            if self.compare(judge, arm, "Abase")[2] == "value" and not self.guard_trips(judge, arm):
                return arm
        return "restore Abase"

    def agreement(self, run_ids):
        keys = [k for k in self.verdicts["primary"] if k[0] in run_ids and k in self.verdicts["secondary"]]
        return {"agree": sum(self.verdicts["primary"][k] == self.verdicts["secondary"][k] for k in keys), "total": len(keys)}

    def pooled_passes(self, judge, arm, picks):
        runs = [(r["id"], cid) for case, cid in picks for r in self.runs_of(case, arm)]
        return sum(self.passes(judge, rid, cid) for rid, cid in runs), len(runs)

    def runs_passing_all(self, judge, case, arm):
        runs = self.runs_of(case, arm)
        return sum(all(self.passes(judge, r["id"], cid) for cid in self.cases[case][1]) for r in runs), len(runs)


def cost_records(bundle):
    return {
        "plan": bundle["runs"]["runs"] + bundle["judgments"]["judges"],
        "addendum-baseline": bundle["addendum-runs"]["runs"] + bundle["addendum-runs"]["judges"],
        "addendum-2": bundle["addendum-2-runs"]["runs"] + bundle["addendum-2-judgments"]["primary"],
        "posthoc": bundle["posthoc-proposal-activation"]["judges"],
    }


def generated(runs, errors):
    skills = {}
    for rid, run in runs.items():
        skill = generated_skill(run["result"])
        if skill is None:
            errors.append(f"{rid}: no generated SKILL.md frontmatter")
        else:
            skills[rid] = skill
    return skills


def cost_table(runs, skills):
    table = {}
    for arm in COST_ARMS:
        chosen = [r for r in runs.values() if r["arm"] == arm and r["case"] in GUARD_CASES]
        table[arm] = {"runs": len(chosen),
                      "words": statistics.median(skills[r["id"]][1] for r in chosen if r["id"] in skills),
                      "output_tokens": statistics.median(r["output_tokens"] for r in chosen),
                      "mean_cost": round(statistics.mean(r["total_cost_usd"] for r in chosen), 3)}
    return table


def check_posthoc(bundle, runs, errors):
    posthoc = bundle["posthoc-proposal-activation"]
    blind_map = {**bundle["judgments"]["blind_map"], **bundle["addendum-runs"]["blind_map"]}
    judged, verdicts, bindings = Counter(), [], {}
    seen = Counter()
    for rec in posthoc["judges"]:
        blind = rec["id"].removeprefix("PX-")
        rid = blind_map.get(blind) if rec["id"].startswith("PX-") else None
        if rid not in runs:
            errors.append(f"posthoc {rec['id']}: matches no judged run")
            continue
        seen[rid] += 1
        run = runs[rid]
        _check_judge_record(rec, "primary", "judge-posthoc", run, blind, None, bindings, errors)
        sink = {}
        _collect(rec, run, ["PX"], sink, "posthoc", errors)
        judged[(run["case"], run["arm"])] += 1
        verdicts += sink.values()
    _check_bindings(bindings, errors)
    for rid, n in seen.items():
        if n > 1:
            errors.append(f"posthoc: {rid} judged {n} times")
    return judged, verdicts


def check_results(bundle, runs, recount, skills, judged, posthoc_verdicts, errors):
    results = bundle["results"]
    for judge in ("primary", "secondary"):
        stored, actual = results[f"tallies_{judge}"], recount.tallies(judge)
        for key in sorted(set(stored) | set(actual)):
            if stored.get(key) != actual.get(key):
                errors.append(f"results.json tallies_{judge} {key}: stored {stored.get(key)} recomputed {actual.get(key)}")
    screened = recount.screened()
    for judge in ("primary", "secondary"):
        if results[f"screened_{judge}"] != screened:
            errors.append(f"results.json screened_{judge}: stored {results[f'screened_{judge}']} recomputed {screened}")
        stored = results[f"comparisons_{judge}"]
        for name in bundle["addendum-2"]["decision_rules"]["comparisons"]:
            if name not in stored:
                errors.append(f"results.json comparisons_{judge}: pre-registered comparison {name!r} is missing")
        for name, value in stored.items():
            actual = recount.compare(judge, *name.split(" vs "))
            if value != actual:
                errors.append(f"results.json comparisons_{judge} {name}: stored {value} recomputed {actual}")
    primary_trips = recount.guard_trips("primary", "Amin")
    if (results["guards_primary"] == "no Amin guard failure") != (not primary_trips):
        errors.append(f"results.json guards_primary {results['guards_primary']!r}, recomputed Amin trips {primary_trips}")
    _check_secondary_risk(results["secondary_risk"], recount, errors)
    ships = {judge: recount.ship(judge) for judge in ("primary", "secondary")}
    if results["decision"].startswith("judge-dependent") != (ships["primary"] != ships["secondary"]):
        errors.append(f"results.json decision {results['decision'][:40]!r}..., recomputed ships {ships}")
    if f"primary judge ships {ships['primary']}" not in results["decision"]:
        errors.append(f"results.json decision does not say the primary judge ships {ships['primary']}")
    if ships["primary"] != ships["secondary"] and not re.search(r"chose (restore|narrow \(Amin\))\.?$", results["decision"]):
        errors.append(f"results.json decision: a judge-dependent result may only restore or narrow, got {results['decision'][-40:]!r}")
    if results["primary_judge"] != PRIMARY_MODEL:
        errors.append(f"results.json primary_judge {results['primary_judge']!r}")
    a2_runs = {r["id"] for r in bundle["addendum-2-runs"]["runs"]}
    agreement = recount.agreement(a2_runs)
    if results["judge_agreement_addendum2"] != agreement:
        errors.append(f"results.json judge_agreement_addendum2: stored {results['judge_agreement_addendum2']} recomputed {agreement}")
    costs = cost_records(bundle)
    total = round(sum(r["total_cost_usd"] for records in costs.values() for r in records), 2)
    if results["total_cost_usd"] != total:
        errors.append(f"results.json total_cost_usd: stored {results['total_cost_usd']} recomputed {total}")
    for batch, cap in (("plan", bundle["plan"]["cost_cap_usd"]), ("addendum-2", bundle["addendum-2"]["cost_cap_usd_additional"])):
        spent = sum(r["total_cost_usd"] for r in costs[batch])
        if spent > cap:
            errors.append(f"{batch}: spent {spent:.2f} USD over the pre-registered cap {cap}")
    bad = Counter(runs[rid]["arm"] for rid, (header, _) in skills.items() if unquoted_colon_description(header))
    frontmatter = {"count": sum(bad.values()), "of": len(runs), "by_arm": dict(bad)}
    if results["generated_frontmatter_yaml_invalid"] != frontmatter:
        errors.append(f"results.json generated_frontmatter_yaml_invalid: stored {results['generated_frontmatter_yaml_invalid']} recomputed {frontmatter}")
    scope = re.search(r"case (\w+) only, ([\w+/]+) x(\d+) = (\d+) runs, all fail", results["posthoc_scope"])
    claimed = {(scope.group(1), arm): int(scope.group(3)) for arm in scope.group(2).split("/")} if scope else None
    if claimed != dict(judged) or scope is None or int(scope.group(4)) != sum(judged.values()) or set(posthoc_verdicts) != {"fail"}:
        errors.append(f"results.json posthoc_scope {results['posthoc_scope']!r}, recomputed {dict(judged)} verdicts {Counter(posthoc_verdicts)}")


def _check_secondary_risk(text, recount, errors):
    claims = {}
    for cid, counts in CRITERION_CLAIM.findall(text.split(". ")[0]):
        for arm, p, n in ARM_COUNTS.findall(counts):
            claims[(cid, arm)] = f"{p}/{n}"
    tallies = recount.tallies("secondary")
    for (cid, arm), value in claims.items():
        actual = tallies.get(f"{recount.case_of.get(cid)}/{cid}", {}).get(arm)
        if actual != value:
            errors.append(f"results.json secondary_risk {cid} {arm} {value}, recomputed {actual}")
    named = {cid for cid, _ in claims}
    for arm in ("Amin", "Amain"):
        tripped = {t.split("/")[1] for t in recount.guard_trips("secondary", arm) if t.startswith("fidelity")}
        if tripped != named:
            errors.append(f"results.json secondary_risk names fidelity trips {sorted(named)}, recomputed {arm} {sorted(tripped)}")
    if ("fails in every arm" in text) != recount.scope_fails_in_every_arm("secondary"):
        errors.append(f"results.json secondary_risk: 'fails in every arm' is {'fails in every arm' in text}, "
                      f"recomputed {recount.scope_fails_in_every_arm('secondary')}")


def _table(doc, heading, errors):
    if heading not in doc:
        errors.append(f"doc: table heading {heading!r} not found")
        return [], []
    lines, rows = doc[doc.index(heading):].splitlines()[1:], []
    for line in lines:
        if line.startswith("|"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
        elif rows:
            break
    return (rows[0], rows[2:]) if len(rows) > 2 else ([], [])


def _number(cell):
    return float(cell.replace(",", "").strip("*")) if "." in cell else int(cell.replace(",", "").strip("*"))


def _claim(flat, pattern, errors):
    match = re.search(pattern, flat)
    if match is None:
        errors.append(f"doc: claim /{pattern}/ not found")
    return match


def check_doc(bundle, recount, skills, judged, posthoc_verdicts, errors):
    doc, flat = bundle["doc"], " ".join(bundle["doc"].split())
    primary, secondary = recount.tallies("primary"), recount.tallies("secondary")
    header, rows = _table(doc, "Depth criteria, passes out of 5, primary judge:", errors)
    seen = []
    for row in rows:
        cid = row[0].split()[0]
        seen.append(cid)
        for arm, cell in zip(header[1:], row[1:]):
            actual = primary.get(f"{recount.case_of.get(cid)}/{cid}", {}).get(arm)
            expected = None if cell == "—" else f"{_number(cell)}/5"
            if actual != expected:
                errors.append(f"doc results table {cid} {arm}: {cell}, recomputed {actual}")
    if seen != [cid for ids in DEPTH.values() for cid in ids]:
        errors.append(f"doc results table rows {seen} are not the depth criteria")
    match = _claim(flat, r"Screened in: ([\w ,]+?)\. Paired", errors)
    if match and re.split(r",\s*|\s+and\s+", match.group(1)) != [cid for _, cid in recount.screened()]:
        errors.append(f"doc: screened {match.group(1)!r}, recomputed {recount.screened()}")
    header, rows = _table(doc, "Paired comparisons:", errors)
    if header != ["Comparison", "Primary judge", "Secondary judge"]:
        errors.append(f"doc paired table columns {header}")
    if sorted(row[0] for row in rows) != sorted(bundle["results"]["comparisons_primary"]):
        errors.append(f"doc paired table rows {[row[0] for row in rows]} are not the stored comparisons")
    for row in rows:
        arm, base = row[0].split(" vs ")
        for judge, cell in zip(("primary", "secondary"), row[1:]):
            parsed = re.fullmatch(r"(\d+)\D+?(\d+)(?: losses)?: (value|no value|inconclusive)", cell)
            actual = recount.compare(judge, arm, base)
            if parsed is None or [int(parsed.group(1)), int(parsed.group(2)), parsed.group(3)] != actual:
                errors.append(f"doc paired table {row[0]} {judge}: {cell!r}, recomputed {actual}")
    match = _claim(flat, r"won (\d+) of (\d+) discordant pairs under the primary judge and (\d+) of (\d+) under the secondary judge, with no losses", errors)
    if match:
        for arm in ("Amin", "Amain"):
            for judge, wins, pairs in (("primary", match.group(1), match.group(2)), ("secondary", match.group(3), match.group(4))):
                w, l, _ = recount.compare(judge, arm, "Abase")
                if [w, w + l, l] != [int(wins), int(pairs), 0]:
                    errors.append(f"doc: {arm} vs Abase {judge} {wins} of {pairs} with no losses, recomputed {w} wins {l} losses")
    match = _claim(flat, r"Amin passed the scope criterion \(D6, X6, Y6\) in (\d+/\d+) runs, F1–F7 in (\d+/\d+), N1–N3 in (\d+/\d+), and the reserved-name check in (\d+/\d+)", errors)
    if match:
        scope = recount.pooled_passes("primary", "Amin", [(c, recount.cases[c][1][SCOPE_INDEX]) for c in GUARD_CASES])
        actual = [scope, recount.runs_passing_all("primary", "P", "Amin"), recount.runs_passing_all("primary", "N", "Amin"),
                  recount.runs_passing_all("primary", "R", "Amin")]
        if [f"{p}/{n}" for p, n in actual] != list(match.groups()):
            errors.append(f"doc primary guard bullet {match.groups()}, recomputed {actual}")
    if _claim(flat, r"Its 4th, 5th, and 7th criteria were not worse than Abase\.", errors):
        for case in GUARD_CASES:
            for index in FIDELITY_INDEXES:
                cid = recount.cases[case][1][index]
                if recount.fails("primary", case, "Amin", cid) > recount.fails("primary", case, "Abase", cid):
                    errors.append(f"doc says Amin's 4th, 5th, and 7th criteria were not worse than Abase, but {cid} is")
    start, end = flat.find("- Secondary judge: -"), flat.find("**Cost and size")
    block = flat[start:end] if 0 <= start < end else ""
    if not block:
        errors.append("doc: secondary judge guard bullets not found")
    bullets = block.split(" - ")[1:]
    fidelity = [b for b in bullets if "trips the fidelity guard" in b]
    if len(fidelity) != 1:
        errors.append(f"doc: expected one secondary fidelity guard bullet, found {len(fidelity)}")
    for bullet in bullets:
        claims = CRITERION_CLAIM.findall(bullet)
        parsed = sum(len(ARM_COUNTS.findall(counts)) for _, counts in claims)
        scope_claim = re.search(rf"Scope criterion \(D6, X6, Y6\): ((?:{ARM} \d+/\d+(?:, )?)+)", bullet)
        parsed += len(ARM_COUNTS.findall(scope_claim.group(1))) if scope_claim else 0
        if parsed != len(re.findall(r"\d+/\d+", bullet)):
            errors.append(f"doc secondary bullet has counts that are not '<arm> p/n' claims: {bullet!r}")
        for cid, counts in claims:
            for arm, p, n in ARM_COUNTS.findall(counts):
                actual = secondary.get(f"{recount.case_of.get(cid)}/{cid}", {}).get(arm)
                if actual != f"{p}/{n}":
                    errors.append(f"doc secondary bullet {cid} {arm} {p}/{n}, recomputed {actual}")
        if bullet in fidelity:
            named = sorted(cid for cid, _ in claims)
            for arm in ("Amin", "Amain"):
                tripped = sorted(t.split("/")[1] for t in recount.guard_trips("secondary", arm) if t.startswith("fidelity"))
                if named != tripped:
                    errors.append(f"doc secondary fidelity bullet names {named}, recomputed {arm} {tripped}")
    every = recount.scope_fails_in_every_arm("secondary")
    for text, phrase in ((block, "trips the scope guard in every arm"), (flat, "fails the scope guard in every arm")):
        if (phrase in text) != every:
            errors.append(f"doc: {phrase!r} present {phrase in text}, recomputed {every}")
    match = _claim(block, rf"Scope criterion \(D6, X6, Y6\): ((?:{ARM} \d+/\d+(?:, )?)+)", errors)
    if match:
        for arm, p, n in ARM_COUNTS.findall(match.group(1)):
            pooled = recount.pooled_passes("secondary", arm, [(c, recount.cases[c][1][SCOPE_INDEX]) for c in GUARD_CASES])
            if pooled != (int(p), int(n)):
                errors.append(f"doc secondary scope {arm} {p}/{n}, recomputed {pooled}")
    match = _claim(flat, r"\(medians, (\d+) runs per arm\)", errors)
    table = cost_table(recount.runs, skills)
    header, rows = _table(doc, "**Cost and size", errors)
    if match and any(v["runs"] != int(match.group(1)) for v in table.values()):
        errors.append(f"doc cost table: {match.group(1)} runs per arm, recomputed {table}")
    if header != ["Arm", "Generated `SKILL.md` words", "Output tokens", "Mean cost (USD)"]:
        errors.append(f"doc cost table columns {header}")
    if [row[0] for row in rows] != list(COST_ARMS):
        errors.append(f"doc cost table arms {[row[0] for row in rows]}")
    for row in rows:
        if row[0] in table and [_number(c) for c in row[1:]] != [table[row[0]][k] for k in ("words", "output_tokens", "mean_cost")]:
            errors.append(f"doc cost table {row[0]}: {row[1:]}, recomputed {table[row[0]]}")
    header, rows = _table(doc, "## Packages", errors)
    amin_words = len(bundle["addendum-2"]["arms"]["Amin"]["SKILL.md_text"].split())
    if not any(row[0] == "Amin" and _number(row[-1]) == amin_words for row in rows):
        errors.append(f"doc packages table: Amin word count is not {amin_words}")
    a2_runs = {r["id"] for r in bundle["addendum-2-runs"]["runs"]}
    agreement = recount.agreement(a2_runs)
    match = _claim(flat, r"agree on (\d+) of (\d+) addendum-2 verdicts \((\d+)%\)", errors)
    if match and [int(g) for g in match.groups()] != [agreement["agree"], agreement["total"], round(100 * agreement["agree"] / agreement["total"])]:
        errors.append(f"doc: agreement {match.groups()}, recomputed {agreement}")
    total = round(sum(r["total_cost_usd"] for records in cost_records(bundle).values() for r in records), 2)
    match = _claim(flat, r"Author spend: \$(\d+\.\d+)", errors)
    if match and float(match.group(1)) != total:
        errors.append(f"doc: author spend {match.group(1)}, recomputed {total}")
    bad = Counter(recount.runs[rid]["arm"] for rid, (h, _) in skills.items() if unquoted_colon_description(h))
    match = _claim(flat, r"(\d+) of the (\d+) generated skills had an unquoted `description`.*? (\d+) of these came from (\S+), (\d+) from (\S+), (\d+) from (\S+), and (\d+) from (\S+?)\.", errors)
    if match:
        g = match.groups()
        claimed = {g[i + 1]: int(g[i]) for i in range(2, 10, 2)}
        if [int(g[0]), int(g[1]), claimed] != [sum(bad.values()), len(recount.runs), dict(bad)]:
            errors.append(f"doc: frontmatter claim {g}, recomputed {dict(bad)} of {len(recount.runs)}")
    match = _claim(flat, r"failed all (\d+) runs it judged\. Those were case (\w+) only, (\d+) runs each of ([^.]+)\.", errors)
    if match:
        arms = re.split(r",\s*(?:and\s+)?|\s+and\s+", match.group(4))
        claimed = {(match.group(2), arm): int(match.group(3)) for arm in arms}
        if int(match.group(1)) != len(posthoc_verdicts) or claimed != dict(judged) or set(posthoc_verdicts) != {"fail"}:
            errors.append(f"doc: posthoc claim {match.groups()}, recomputed {dict(judged)} {Counter(posthoc_verdicts)}")


def audit(bundle):
    errors = []
    check_digests(bundle, errors)
    cases = cases_of(bundle, errors)
    runs = check_runs(bundle, errors)
    check_prompts(bundle, runs, cases, errors)
    verdicts = check_judgments(bundle, runs, cases, errors)
    recount = Recount(runs, cases, verdicts, errors)
    skills = generated(runs, errors)
    judged, posthoc_verdicts = check_posthoc(bundle, runs, errors)
    check_results(bundle, runs, recount, skills, judged, posthoc_verdicts, errors)
    check_doc(bundle, recount, skills, judged, posthoc_verdicts, errors)
    return errors


BUNDLE = load()


def _blind(data, run_id):
    return next(blind for blind, rid in data["blind_map"].items() if rid == run_id)


def _record(bundle, file, key, run_id, prefix="J-"):
    data = bundle[file]
    blind = _blind(data, run_id)
    return next(rec for rec in data[key] if rec["id"] == prefix + blind)


def _edit_criteria(record, change):
    criteria = read_judgment(record["result"])
    change(criteria)
    record["result"] = json.dumps({"criteria": criteria})


def _set_verdict(record, cid, verdict):
    _edit_criteria(record, lambda cs: next(c for c in cs if c["id"] == cid).update(verdict=verdict))


def _run(bundle, file, run_id):
    return next(r for r in bundle[file]["runs"] if r["id"] == run_id)


class RecordedDepthEvaluationTests(unittest.TestCase):
    def test_recorded_evidence_recomputes_to_every_stored_aggregate(self):
        self.assertEqual(audit(BUNDLE), [])

    def test_preregistered_guard_and_ship_rules_under_each_judge(self):
        errors = []
        cases = cases_of(BUNDLE, errors)
        runs = check_runs(BUNDLE, errors)
        recount = Recount(runs, cases, check_judgments(BUNDLE, runs, cases, errors), errors)
        self.assertEqual(recount.guard_trips("primary", "Amin"), [])
        self.assertEqual(recount.guard_trips("secondary", "Amin"),
                         ["scope D/D6", "scope X1/X6", "fidelity X1/X5", "scope X2/Y6", "fidelity X2/Y5", "N N/N3"])
        self.assertEqual(recount.guard_trips("secondary", "Amain"),
                         ["scope D/D6", "scope X1/X6", "fidelity X1/X5", "scope X2/Y6", "fidelity X2/Y5", "N N/N3", "unevaluable R"])
        self.assertEqual(recount.guard_trips("primary", "Amain"), ["unevaluable R"])
        self.assertTrue(recount.scope_fails_in_every_arm("secondary"))
        self.assertFalse(recount.scope_fails_in_every_arm("primary"))
        self.assertEqual({j: recount.ship(j) for j in ("primary", "secondary")}, {"primary": "Amin", "secondary": "restore Abase"})
        self.assertEqual(errors, [])

    def test_shipped_instructions_are_the_evaluated_candidate(self):
        # The pre-registered judge_disagreement rule ships no body change beyond the
        # narrowed candidate; a later edit needs a reproduced failure and a rerun.
        amin = BUNDLE["addendum-2"]["arms"]["Amin"]
        package = ROOT / "skills" / "work-to-skill"
        for rel in ("SKILL.md", "references/validation.md"):
            with self.subTest(rel):
                self.assertEqual(_sha256((package / rel).read_bytes()), amin[rel])


class DepthEvidenceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.bundle = copy.deepcopy(BUNDLE)

    def assertRejected(self, fragment, bundle=None):
        errors = audit(bundle or self.bundle)
        self.assertTrue(any(fragment in error for error in errors), f"{fragment!r} not in {errors}")

    def test_preregistration_edited_after_its_digest_is_rejected(self):
        self.bundle["raw"]["plan"] = self.bundle["raw"]["plan"].replace(b'"cost_cap_usd": 60', b'"cost_cap_usd": 90')
        self.assertRejected("plan.json: sha256")

    def test_digest_record_for_another_file_is_rejected(self):
        self.bundle["digests"]["addendum-2"] = self.bundle["digests"]["addendum-2"].replace("addendum-2.json", "plan.json")
        self.assertRejected("addendum-2.sha256: not a")

    def test_parsed_preregistration_must_be_the_digested_bytes(self):
        self.bundle["addendum-2"]["decision_rules"]["guards"] = "Amin never blocks"
        self.assertRejected("addendum-2.json: parsed content differs from the digested bytes")

    def test_candidate_package_text_must_match_its_recorded_digest(self):
        amin = self.bundle["addendum-2"]["arms"]["Amin"]
        amin["SKILL.md_text"] = amin["SKILL.md_text"].replace("work-to-skill", "work-to-skills", 1)
        self.assertRejected("Amin SKILL.md_text: sha256 does not match")
        self.assertRejected("X1-Amin-1: recorded prompt does not match the prompt rebuilt")

    def test_missing_run_is_reported(self):
        runs = self.bundle["addendum-2-runs"]["runs"]
        runs.remove(_run(self.bundle, "addendum-2-runs", "X2-Abase-3"))
        self.assertRejected("addendum-2-runs.json: planned run X2-Abase-3 is missing")

    def test_duplicated_and_unplanned_runs_are_reported(self):
        runs = self.bundle["runs"]["runs"]
        runs.append(copy.deepcopy(_run(self.bundle, "runs", "D-A1-1")))
        runs.append(dict(copy.deepcopy(_run(self.bundle, "runs", "D-A1-1")), id="D-A1-6", rep=6))
        self.assertRejected("runs.json: run D-A1-1 recorded 2 times")
        self.assertRejected("runs.json: run D-A1-6 is not in the pre-registered plan")

    def test_truncated_run_is_not_a_completed_run(self):
        _run(self.bundle, "addendum-runs", "D-Abase-2").update(stop_reason="max_tokens", terminal_reason="max_tokens")
        self.assertRejected("D-Abase-2: truncated or failed run (stop_reason 'max_tokens'")

    def test_run_fields_must_agree_with_its_id(self):
        _run(self.bundle, "addendum-2-runs", "X1-Amin-2").update(rep=3)
        self.assertRejected("X1-Amin-2: run fields disagree with its id")

    def test_unmetered_run_is_reported(self):
        _run(self.bundle, "addendum-2-runs", "X1-Amin-2").update(total_cost_usd=0)
        self.assertRejected("X1-Amin-2: unmetered run")

    def test_swapped_arm_labels_break_prompt_consistency(self):
        a, b = _run(self.bundle, "addendum-2-runs", "X1-Abase-1"), _run(self.bundle, "addendum-2-runs", "X1-Amain-1")
        a["id"], a["arm"], b["id"], b["arm"] = "X1-Amain-1", "Amain", "X1-Abase-1", "Abase"
        self.assertRejected("X1-Abase: reps of one arm were given different prompts")
        self.assertRejected("Abase: prompt length beyond the case request differs across runs")

    def test_four_question_arm_must_be_the_base_prompt_plus_the_guide(self):
        for run in self.bundle["addendum-2-runs"]["runs"]:
            if run["arm"] == "Abase+F":
                run["prompt_chars"] += 1
        self.assertRejected("Abase+F: prompt is not the Abase prompt plus")

    def test_blind_map_pointing_at_another_run_is_reported(self):
        data = self.bundle["addendum-2-judgments"]
        data["blind_map"][_blind(data, "X2-Amin-4")] = "X2-Amin-5"
        self.assertRejected("addendum-2-judgments.json primary: run X2-Amin-4 has no blind id")
        self.assertRejected("addendum-2-judgments.json primary: run X2-Amin-5 has 2 blind ids")

    def test_blind_id_reused_across_batches_is_reported(self):
        blind = _blind(self.bundle["judgments"], "D-A0-1")
        sb = self.bundle["addendum-2-secondary-baseline"]
        old = _blind(sb, "D-A0-1")
        sb["blind_map"][blind] = sb["blind_map"].pop(old)
        next(r for r in sb["secondary"] if r["id"] == "K-" + old)["id"] = "K-" + blind
        self.assertRejected(f"blind id {blind} is used in 2 blind maps")

    def test_each_judge_must_cover_every_planned_run(self):
        rec = _record(self.bundle, "addendum-2-secondary-baseline", "secondary", "N-Abase-2", "K-")
        self.bundle["addendum-2-secondary-baseline"]["secondary"].remove(rec)
        self.assertRejected(f"addendum-2-secondary-baseline.json: blind id {rec['id'][2:]} judged 0 times")
        self.assertRejected("secondary judge: no verdict for N-Abase-2 N3")

    def test_criterion_set_must_equal_the_plan(self):
        _edit_criteria(_record(self.bundle, "addendum-2-judgments", "primary", "X1-Amin-3"), lambda cs: cs.pop())
        _edit_criteria(_record(self.bundle, "addendum-runs", "judges", "P-Amain-1"),
                       lambda cs: cs.append(dict(cs[0], id="F8")))
        _edit_criteria(_record(self.bundle, "judgments", "judges", "N-A2-1"), lambda cs: cs.append(dict(cs[0])))
        self.assertRejected("(X1-Amin-3): criteria")
        self.assertRejected("(P-Amain-1): criteria")
        self.assertRejected("(N-A2-1): criteria")

    def test_verdict_outside_pass_fail_is_rejected(self):
        _set_verdict(_record(self.bundle, "addendum-2-judgments", "secondary", "D-Amin-1", "K-"), "D1", "partial")
        self.assertRejected("D1: verdict 'partial' is not pass/fail")

    def test_judge_output_with_duplicate_keys_is_rejected(self):
        rec = _record(self.bundle, "addendum-runs", "judges", "D-Abase-1")
        rec["result"] = rec["result"].replace('"verdict":', '"verdict":"fail","verdict":', 1)
        self.assertRejected("(D-Abase-1): judge output is not a criteria document")

    def test_judge_record_for_another_case_or_model_is_rejected(self):
        _record(self.bundle, "addendum-2-judgments", "primary", "X2-Abase-1").update(case="X1")
        _record(self.bundle, "addendum-2-judgments", "secondary", "X2-Abase-1", "K-").update(model_flag="gpt-5")
        _record(self.bundle, "judgments", "judges", "D-A1-1").update(arm="A1")
        self.assertRejected("(X2-Abase-1): case 'X1', expected 'X2'")
        self.assertRejected("(X2-Abase-1): model_flag 'gpt-5', expected 'gpt-6.1-sol'")
        self.assertRejected("(D-A1-1): arm 'A1', expected None")

    def test_one_flipped_raw_verdict_breaks_tallies_and_comparisons(self):
        _set_verdict(_record(self.bundle, "addendum-runs", "judges", "D-Abase-2"), "D1", "pass")
        self.assertRejected("results.json tallies_primary D/D1: stored")
        self.assertRejected("results.json comparisons_primary Amin vs Abase: stored [9, 0, 'value'] recomputed [8, 0, 'value']")
        self.assertRejected("doc results table D1 Abase")

    def test_screening_follows_the_primary_judge(self):
        for rep in (1, 2, 3, 4, 5):
            _set_verdict(_record(self.bundle, "addendum-2-judgments", "primary", f"X2-Abase-{rep}"), "Y3", "pass")
        self.assertRejected("results.json screened_primary: stored [['D', 'D1'], ['X2', 'Y3']] recomputed [['D', 'D1']]")
        self.assertRejected("results.json screened_secondary")

    def test_scope_fail_trips_the_primary_guard_and_the_ship_decision(self):
        _set_verdict(_record(self.bundle, "addendum-2-judgments", "primary", "X1-Amin-1"), "X6", "fail")
        self.assertRejected("results.json guards_primary 'no Amin guard failure', recomputed Amin trips ['scope X1/X6']")
        self.assertRejected("results.json decision does not say the primary judge ships restore Abase")
        self.assertRejected("results.json decision 'judge-dependent")

    def test_judge_dependent_result_may_only_restore_or_narrow(self):
        results = self.bundle["results"]
        results["decision"] = results["decision"].replace("chose narrow (Amin).", "chose Amain.")
        self.assertRejected("results.json decision: a judge-dependent result may only restore or narrow")

    def test_scope_claim_for_every_arm_must_match_the_recount(self):
        results = self.bundle["results"]
        results["secondary_risk"] = results["secondary_risk"].replace("fails in every arm", "passes in every arm")
        self.bundle["doc"] = re.sub(r"It trips\s+the scope guard in every arm\.", "It passes the scope guard.", self.bundle["doc"])
        self.assertRejected("results.json secondary_risk: 'fails in every arm' is False, recomputed True")
        self.assertRejected("doc: 'trips the scope guard in every arm' present False, recomputed True")

    def test_judge_record_bound_to_another_runs_output_is_rejected(self):
        data = self.bundle["addendum-runs"]
        a, b = _blind(data, "D-Abase-1"), _blind(data, "D-Abase-2")
        data["blind_map"][a], data["blind_map"][b] = "D-Abase-2", "D-Abase-1"
        self.assertRejected("judge D: judge prompt length does not fit the judged run output")

    def test_secondary_fidelity_numbers_must_match_raw_verdicts(self):
        records = [_record(self.bundle, "addendum-2-judgments", "secondary", f"X1-Abase-{rep}", "K-") for rep in range(1, 6)]
        passing = next(r for r in records if next(c for c in read_judgment(r["result"]) if c["id"] == "X5")["verdict"] == "pass")
        _set_verdict(passing, "X5", "fail")
        self.assertRejected("results.json secondary_risk X5 Abase 3/5, recomputed 2/5")
        self.assertRejected("doc secondary bullet X5 Abase 3/5, recomputed 2/5")

    def test_secondary_risk_must_name_exactly_the_tripped_fidelity_criteria(self):
        results = self.bundle["results"]
        results["secondary_risk"] = results["secondary_risk"].replace("; Y5 Amin 0/5, Amain 0/5, Abase 2/5", "")
        self.assertRejected("results.json secondary_risk names fidelity trips ['X5'], recomputed Amin ['X5', 'Y5']")

    def test_edited_stored_aggregates_are_reported(self):
        results = self.bundle["results"]
        results["comparisons_secondary"]["Amin vs Abase+F"] = [1, 0, "inconclusive"]
        results["judge_agreement_addendum2"]["agree"] = 400
        results["total_cost_usd"] = 40.0
        results["generated_frontmatter_yaml_invalid"]["by_arm"]["Amin"] = 0
        results["posthoc_scope"] = results["posthoc_scope"].replace("x5 = 20", "x5 = 25")
        del results["comparisons_primary"]["Amin vs Amain"]
        self.assertRejected("results.json comparisons_secondary Amin vs Abase+F: stored [1, 0, 'inconclusive'] recomputed [0, 0, 'inconclusive']")
        self.assertRejected("results.json judge_agreement_addendum2: stored")
        self.assertRejected("results.json total_cost_usd: stored 40.0 recomputed 46.57")
        self.assertRejected("results.json generated_frontmatter_yaml_invalid: stored")
        self.assertRejected("results.json posthoc_scope")
        self.assertRejected("pre-registered comparison 'Amin vs Amain' is missing")

    def test_changed_run_cost_breaks_the_total_and_the_cost_table(self):
        _run(self.bundle, "addendum-2-runs", "X2-Amin-1").update(total_cost_usd=1.5)
        self.assertRejected("results.json total_cost_usd: stored 46.57")
        self.assertRejected("doc cost table Amin")

    def test_spend_over_the_preregistered_cap_is_reported(self):
        _run(self.bundle, "addendum-2-runs", "X2-Amin-1").update(total_cost_usd=30.0)
        self.assertRejected("addendum-2: spent")

    def test_posthoc_pass_contradicts_all_fail(self):
        _set_verdict(self.bundle["posthoc-proposal-activation"]["judges"][0], "PX", "pass")
        self.assertRejected("results.json posthoc_scope")
        self.assertRejected("doc: posthoc claim")

    def test_posthoc_missing_judgment_shrinks_the_claimed_scope(self):
        self.bundle["posthoc-proposal-activation"]["judges"].pop()
        self.assertRejected("results.json posthoc_scope")
        self.assertRejected("doc: posthoc claim")

    def test_doc_paired_table_must_list_every_comparison(self):
        self.bundle["doc"] = re.sub(r"(?m)^\| Amin vs Amain \|.*\n", "", self.bundle["doc"])
        self.assertRejected("doc paired table rows")

    def test_doc_table_columns_must_not_be_reordered(self):
        self.bundle["doc"] = (self.bundle["doc"]
                              .replace("| Comparison | Primary judge | Secondary judge |", "| Comparison | Secondary judge | Primary judge |")
                              .replace("| Output tokens | Mean cost (USD) |", "| Mean cost (USD) | Output tokens |"))
        self.assertRejected("doc paired table columns")
        self.assertRejected("doc cost table columns")

    def test_doc_secondary_count_outside_the_claim_format_is_reported(self):
        self.bundle["doc"] = self.bundle["doc"].replace("N3: Amin 0/3, Abase 0/3.", "N3: Amin 0/3 and Abase 2/3.")
        self.assertRejected("doc secondary bullet has counts that are not '<arm> p/n' claims")

    def test_primary_judge_record_without_prompt_length_is_reported(self):
        _record(self.bundle, "addendum-2-judgments", "primary", "X1-Amin-1").pop("prompt_chars")
        self.assertRejected("(X1-Amin-1): prompt_chars missing")

    def test_doc_fidelity_bullet_must_name_every_tripped_criterion(self):
        self.bundle["doc"] = self.bundle["doc"].replace("X5: Amin 1/5, Amain 1/5, Abase 3/5.", "X5: Amin 1 of 5, Amain 4 of 5, Abase 3 of 5.")
        self.assertRejected("doc secondary fidelity bullet names ['Y5'], recomputed Amin ['X5', 'Y5']")

    def test_doc_not_worse_claim_must_hold(self):
        for rep in (1, 2):
            _set_verdict(_record(self.bundle, "addendum-2-judgments", "primary", f"D-Amin-{rep}"), "D5", "fail")
        self.assertRejected("not worse than Abase, but D5 is")

    def test_doc_numbers_must_match_the_recomputation(self):
        doc = self.bundle["doc"]
        self.bundle["doc"] = (doc.replace("| Amin | 936 | 3,814 | 0.223 |", "| Amin | 900 | 3,814 | 0.223 |")
                              .replace("| Amin vs Abase | 9 wins, 0 losses: value |", "| Amin vs Abase | 10 wins, 0 losses: value |")
                              .replace("343 of 435", "353 of 435")
                              .replace("Amin 2/15, Amain 5/15", "Amin 1/15, Amain 5/15"))
        self.assertRejected("doc cost table Amin")
        self.assertRejected("doc paired table Amin vs Abase primary")
        self.assertRejected("doc: agreement")
        self.assertRejected("doc secondary scope Amin 1/15")

    def test_doc_claim_that_cannot_be_found_is_reported(self):
        self.bundle["doc"] = self.bundle["doc"].replace("Author spend: $46.57", "Author spend was modest")
        self.assertRejected("doc: claim /Author spend")


if __name__ == "__main__":
    unittest.main()
