# Behavioral checks

These synthetic inputs are maintainer evaluation data, not installed skills.
Package tests validate structure, not model judgment.

Check generated packages with `skills/work-to-skill/scripts/check_skill.py`, once
per intended host. Common Agent Skills format errors fail on every host; Anthropic
reserved names and XML tags fail only with `--host anthropic`; length and nesting
are warnings. Optional fields such as `metadata` pass. `tests/test_package.py`
also requires this repository's exact `name`/`description` field set, which is
not a rule for generated skills.

Combined case JSON containing a request and acceptance criteria is evaluator-only.
Supply just the request and the complete work-to-skill package to a fresh model
context. Keep acceptance criteria with the evaluator, not the author. Record
model, host, skill digest, allowed tools, input, output, and verdict. For text-only
runs, collect file contents and state that installation/tool execution did not occur.

Evaluate authoring (A), then run generated skills (B) on new inputs in fresh contexts.
B gets only its generated skill and task inputs, without work-to-skill, authoring
history, or answer hints. Evaluators may use an answer key; executors may not.
When portability is in scope, cross-execute relevant examples between the hosts
named for that claim in the validation record.

Test native discovery with other creators present before claiming automatic
invocation compatibility. Prompt-level selection is not native discovery evidence.
Keep private inputs out of the repository. Record failures and corrections.
Reused cases are regression checks, not fresh held-out tests.

## Comparative evaluations

Use a comparative evaluation to test whether a skill adds value. Each
`evidence/eval-*` directory is one source bundle. Its `contract.json` is written
and its digest recorded before any run, and it fixes:

- the source material and requests;
- the evaluator-only criteria;
- the arms;
- the decision rules;
- the cost caps.

The same yardstick applies to generated skills and to work-to-skill:

| Role | Generated skill (task) | work-to-skill (authoring) |
| --- | --- | --- |
| empty | task input only | authoring request with the notes (A0) |
| source | task input + the same notes | A0 + a skill-writing guide (A-guide) |
| skill | task input + generated skill | A0 + work-to-skill (A1) |

1. Screen every case with the empty and source arms. Keep only cases the empty
   arm fails, and leave answer hints out of task requests.
2. Gate authored packages on fidelity to the notes before running them.
3. Count discordant pairs against the source arm on discriminating cases:
   - value: wins ≥ 5 and losses = 0;
   - no value: at least 10 discriminating cases and net ≤ 0;
   - otherwise: inconclusive.

   Do not add cases after seeing results.
4. Judge blind, with arm labels hidden and order shuffled. The executor never sees
   the criteria.

Model runs use the host CLI recorded in the contract. `evaluate.py` recomputes
each `summary.json` from the recorded runs and verdicts, and pools pairs across
directories:

```
python tests/behavior/evaluate.py tests/behavior/evidence/eval-2026-11-01-*
```

CI runs the same check without network access. It rejects a bundle when:

- a run the contract calls for is missing, or a run it does not call for is
  present (screen runs for every case; three authoring arms × two runs; task
  runs only on discriminating cases, and base arms only when run 1's fidelity
  verdict differs from A1 run 1's);
- a text run failed, stopped for any reason other than `end_turn`, or lacks a
  cost or usage field. Usage and cost are non-negative numbers. A usage field
  the provider does not report is recorded as `null` with a reason under
  `unavailable`; a missing field, or a reason for a field that has a value, is
  an error. Cost is always required;
- a verdict is anything other than `pass`/`fail`, scores a criterion set that
  differs from the contract, or is not a verbatim transcription of the judge's
  recorded output through the blind map. Fidelity criteria match by full text
  or by id (`F1`); rubric criteria by full text only. Task verdicts score the
  case rubric plus one common criterion, which must equal `b_common` after its
  `every case: ` prefix with any parenthesised examples removed, optionally
  prefixed `common: ` (the three 2026-11-01 bundles word the examples
  differently);
- any JSON file, or a judge's recorded output, repeats a key or a judgment id;
- a generated skill does not name the run-1 authoring run of its arm or is not
  quoted from that run's output;
- a recorded prompt digest differs from the prompt rebuilt from the contract.
  Screen, task, and A0 prompts are always rebuilt; A1 prompts only while the
  checkout's `work-to-skill` files match the contract's package digests;
  A-guide prompts (guide kept as a digest) and judge prompts are not rebuilt,
  and the CLI lists them;
- the contract has an `e5` section but `e5.json` is absent, the recorded
  requests differ from the contract's set or wording, or a request lacks its
  completion status, model, cost, or the list of invoked skills. A request that
  stopped before completing is listed under `incomplete`; its recorded skill
  selection still counts;
- two pooled bundles have the same contract content (canonical JSON digest,
  `contract_sha256`) or the same set of run outputs (`runs_sha256`). A bundle
  that shares only some runs with another is not detected.

Authoring runs carry the request's `case` label, which the validator does not
check; the A0 and A1 prompt digests tie those runs to their bundle, and the
A-guide runs are tied only by their listed `rep` and arm. The 2026-11-01
planning and tax bundles carry a copied `payments-review` label on their
authoring runs. Expected arms and repetitions are the 2026-11-01 design
(`AUTHOR_ARMS`, `AUTHOR_REPS` in `evaluate.py`); a bundle with a different
design needs those constants changed. The check does not establish whether a
verdict is right.
