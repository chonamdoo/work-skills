# 2026-11-08 check of suspected evaluation gaps

**Decision: no change.** Four gaps suspected in `references/validation.md`, and a
fifth observed during the check, did not reproduce under the pre-registered rule.
`validation.md` and `SKILL.md` are unchanged.

This is A-side guidance evidence from text-only runs: an executor given the current
package was asked to write a verdict or B plan for a supplied record. It does not
test host selection or a generated skill's task behavior.

Evidence: [`tests/behavior/evidence/eval-gaps-2026-11-08/`](../tests/behavior/evidence/eval-gaps-2026-11-08/).

## Why these gaps were suspected

A check of a 2026-10-31 seminar on skill evaluation, and a 45-run A/B of the
seminar's `codebase-brain` skill on one TypeScript repository, suggested that the
guidance might let an evaluator:

| Gap | Suspected miss |
| --- | --- |
| G1 | treat equal accuracy at higher time, tokens, and cost as a tie |
| G2 | plan B without checking that the host selects the generated skill |
| G3 | attribute a version difference to the change without a same-version (A/A) noise estimate |
| G4 | read repeated runs as overall pass rate when every run must pass |

G1's case uses the raw A/B rows: equal recall and precision, about +9.5 s and
about 2.3× input tokens per run for the skill arm.

## Conditions

- **Executor and primary judge:** `claude-fable-5-1`, invocation as in
  `depth-2026-11-04/plan.json`.
- **Secondary judge:** `gpt-6.1-sol` through `codex exec`, same blind ids.
- **Arms:** `Abase` and `AbaseB`, both `main@59466c9`, run as separate batches (A/A).
- **Freezing:** `plan.json` and `addendum-e2c.json` were written and hashed before
  their runs. The addendum was written after the plan's results were seen.

## Results

Failures of each case's key criteria, Abase + AbaseB (6 runs). A gap reproduces at
≥ 4 of 6 under the primary judge.

| Gap | Case | Primary | Secondary | Verdict |
| --- | --- | --- | --- | --- |
| G1 efficiency | G1 | 0/6 | 0/6 | not reproduced |
| G2 B selection | G2 | 1/6 | 0/6 | not reproduced |
| G3 A/A noise | G3 | 0/6 | 0/6 | not reproduced |
| G4 every-run reading | G4 | 0/6 | 0/6 | not reproduced |
| E2c selection evidence | S1 | 2/6 | 2/6 | not reproduced |
| E2c selection evidence | S2 | 0/6 | 0/6 | not reproduced |

All six G1 runs reported the skill arm's higher time and tokens and called the
release claim unsupported. All G3 and G4 runs refused the improvement or
reliability claim and reported the per-case every-run result.

E2c was a non-key criterion in case G2: plans said to record which skill the host
selected without naming host events or logs as the evidence. It failed 5/6
(primary) and 6/6 (secondary). The addendum made it the key criterion on two new
cases. On S2, where the record held only the agents' own statements, every run
reported selection as unverified. The A/A difference was 0 on both key criteria.

Because neither phase reproduced a gap, the fix, held-out (`HS`), and regression
phases were not run.

## Limits

- Synthetic records and one executor model. Executors received the guidance as
  text; host discovery was not exercised.
- Three runs per arm per case. A rarer miss below the 4-of-6 threshold would not
  be detected; the E2c miss on S1 (2/6) is one such signal and stays open.
- Criteria wording and case choice are the evaluator's; G1–G4 were
  written after the seminar check, so they are development cases.
- Cost: USD 13.62 for executor runs and primary judging; secondary judging ran on
  a Codex subscription with no per-call cost record.
