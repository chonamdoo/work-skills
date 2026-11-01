# 2026-11-01 comparative evaluation (epic #9 pilot)

This pilot implements [epic #9](https://github.com/chonamdoo/work-skills/issues/9)
after its 2026-11-01 revision. It tests two separate claims with the same yardstick:

- Do generated skills do the work better than the same expert notes supplied
  directly?
- Does `work-to-skill` author better skills than a plain request, or than a request
  that includes a skill-writing guide?

A separate check observes whether a real host selects `work-to-skill`.

Raw records are under [tests/behavior/evidence](../tests/behavior/evidence) in the
three `eval-2026-11-01-*` directories. The procedure is in
[tests/behavior/README.md](../tests/behavior/README.md#comparative-evaluations).
`python tests/behavior/evaluate.py tests/behavior/evidence/eval-2026-11-01-*`
recomputes every count below.

## Conditions

- **Model:** `claude-fable-5-1` for every run. This is the served model reported
  in each response.
- **Text runs:** `claude -p --bare --tools ""` from `/tmp` with a fixed system
  prompt.
- **Host check:** Claude Code 2.1.316, run from an isolated configuration
  directory.
- **Package:** `work-to-skill` at `main` after PR #10 (`SKILL.md` `8e3555e1…`).
- **Source bundles:** three synthetic bundles of five cases each.
  - Payments code review: rules with path carve-outs, a superseded exemption, a
    declined proposal, and an embedded instruction to auto-approve.
  - Feature-proposal readiness: knowledge only.
  - Expense-document gaps: thresholds come from the engagement letter, plus a
    prepaid exception.
- **Freezing:** each contract was written and hashed before its runs.
  - The planning and tax contracts were frozen after the payments results had been
    seen.
  - All three are development bundles, not held-out evidence.
- **Cost:** provider-reported USD 15.73 for 84 calls, against a pre-set cap of
  USD 40 and 80 calls per bundle.

## Results

### Host selection (E5)

Claude Code loaded 72 skills: the maintainer's installed set, the candidate
`work-to-skill`, and Anthropic's `skill-creator`. Built-in skills were also
present. Selection was read from `Skill` tool events in the stream, not from the
model's own statements.

| Requests | Selected `work-to-skill` | Pre-set rule |
| --- | --- | --- |
| Positive (create ×2 incl. Korean, knowledge capture, narrow update, evaluate) | 4/5 | ≥ 4/5 |
| Negative (ordinary work incl. Korean, a deliverable from expert notes) | 0/5 | 0/5 |
| Adjacent (AGENTS.md, system prompt, CLAUDE.md) | 0/3 (`writing-for-agents` ×2, none ×1) | reported |

The miss was the narrow update. The request supplied an existing skill inline,
and the model edited it directly without loading any skill. The evaluation-only
request loaded `work-to-skill` and then read `references/validation.md`, as the
skill's link directs. Epic hypothesis H1, that ordinary work requests might
falsely trigger the skill, is closed: no false selection occurred.

Selection and completion are separate observations. `P1`, `P2`, `P5`, and `J3`
stopped at the evaluation's `--max-turns 3` limit (`error_max_turns`; Write,
Edit, and Bash were also disallowed) after their skill selection, if any, had
been observed; the other nine completed. The selection counts above stand,
because a `Skill` event precedes any later stop; whether those four requests
would have produced a deliverable was not observed. For `J3`, which loaded
`writing-for-agents`, "no false selection" covers the three turns that ran, not
a completed request.

### Case screening

| Bundle | Cases the empty arm failed |
| --- | --- |
| Payments | 4/5 |
| Planning | 4/5 |
| Tax | 2/5 |

Ten of the 15 cases discriminate. The source arm passed all of them.

### Authoring fidelity (work-to-skill)

Two authoring runs were made per arm per bundle. Each package was judged blind
against the bundle's fidelity gate.

| Arm | Failed packages | Failures |
| --- | --- | --- |
| A0 (request + notes) | 2/6 | unlabelled author additions (payments); description without a "when to use" condition (tax) |
| A-guide (+ Anthropic best-practices page) | 1/6 | unlabelled example rulings that contradict the notes (planning) |
| A1 (+ work-to-skill) | 0/6 | — |

Discordant pairs for A1:

| Comparison | Wins | Losses | Ties | Decision |
| --- | --- | --- | --- | --- |
| A1 vs A0 | 2 | 0 | 4 | inconclusive |
| A1 vs A-guide | 1 | 0 | 5 | inconclusive |

No arm promoted the auto-approve instruction, lost a carve-out, or produced a
reserved name.

### Task behaviour (generated skills)

| Comparison on discriminating cases | Wins | Losses | Ties | Decision |
| --- | --- | --- | --- | --- |
| Generated skill (A1) vs the same notes supplied directly, pooled | 0 | 0 | 10 | **no value** |
| Generated skill (A0, payments only) vs notes | 0 | 0 | 4 | inconclusive |

Each bundle's B-A1 runs used that bundle's A1 run 1, as pre-registered. The 10
pairs therefore test three generated packages, one per bundle, not ten
independent authoring results.

The payments A0 skill failed the fidelity gate but passed every task case. Its
unlabelled additions did not change any outcome measured here.

## Decisions

- **Generated skill vs notes supplied directly:**
  - This is a "no value" result under the pre-registered rule. With short, clean
    notes, a generated skill did not make the work more correct than pasting the
    notes.
  - It is not a finding of equivalence.
  - It is not evidence about long or scattered sources, tool-using procedures,
    or other models.
  - Any benefit of packaging lies in reuse, discovery, and not having to supply
    the notes each time. None of those was measured, so no break-even count is
    computed.
- **`work-to-skill` vs plain authoring:**
  - The result is inconclusive, so the current version is kept.
  - The only measured difference is fewer labelling and description defects in
    generated packages (0/6 vs 2/6 and 1/6). Of the three failed packages, only
    the payments A0 run 1 was run on tasks, and its defects did not change any
    task result there. The planning A-guide and tax A0 failures were never run on
    tasks, so their downstream effect is unobserved.
- **Changes from this evaluation (E4):** none.
  - No creator failure was reproduced.
  - The single host-selection miss is below the reproduction threshold (2/5).
  - `validation.md` already carries the same-knowledge baseline and the screening
    rule from PR #10, so it needs no further edit.
- **Option for users:** for a one-off task, or a short rule set you will apply
  rarely, give the notes to the agent directly. Create a skill when reuse or
  automatic selection matters to you.

## Limits

- The bundles are synthetic, development-only, and three in number. Expert
  correctness was not assessed.
- All runs used one model. The host check covered one host, and only selection
  and reference reading. No generated skill was installed and executed with
  tools.
- The judges are the same model family as the executors. Arm labels were hidden.
  The parent read the outputs and overrode no verdict.
- The payments judge received two clarifications after the parent had read the
  screening outputs: hedged wording does not count as a judgment, and listing an
  allowed item among violations fails its criterion. The payments discriminating
  set depends only on the second. The later bundles' judges used both from the
  start.
- Human preparation and review time were not measured.
- The planning and tax authoring runs carry `case: "payments-review"`, copied from
  the payments bundle. The label is wrong; the A0 and A1 prompt digests of those
  runs match their own bundles' authoring requests (the A-guide prompts are not
  rebuilt), and the records are left as captured.
- The planning contract's `value_rules.authoring` says "fidelity gate F1-F7",
  copied from payments; its `fidelity_gate` lists F1-F5, and the judge scored
  those five.
- The judges scored the common "no external action" criterion under the
  contract's clause with differently worded examples in each bundle; the
  validator matches the clause, not the examples.
- `tests/behavior/evaluate.py` checks the records' structure and transcription,
  not the judgments. The A-guide prompts (guide held as a digest) and the judge
  prompts cannot be rebuilt from the bundles. The `contract_sha256` and
  `runs_sha256` in each `summary.json` were computed afterwards for duplicate
  detection when pooling; they are not pre-registration records.
