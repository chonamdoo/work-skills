# Behavioral checks

These synthetic inputs are maintainer evaluation data, not installed skills.
Package tests validate structure, not model judgment.

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

CI runs the same check without network access. It catches missing, duplicate,
or failed runs and summaries that disagree with their verdicts. It does not
check whether a verdict is right.
