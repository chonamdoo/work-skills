# 2026-11-04 evaluation of the depth pass

**Decision: judge-dependent; ship the narrowed depth pass.** The pre-depth skill
failed two pre-registered criteria. On both, the narrowed version and the merged
depth pass won 9 of 9 discordant pairs under the primary judge and 7 of 7 under
the secondary judge, with no losses.

The guards split the judges:

- **Primary judge:** no guard failure for the narrowed version, so the
  pre-registered rule ships it.
- **Secondary judge:** it trips the pre-registered fidelity guard. The 5th
  criterion, labelling author additions, fails in 2 more runs than the pre-depth
  skill in X1 and in X2, for both the narrowed and the merged version. It also
  fails the scope guard in every arm, the pre-depth skill included, and the
  narrow-update guard (N3 0/3 for the narrowed version and the pre-depth skill).

Under `addendum-2.json`'s disagreement rule, a judge-dependent result allows no
body change beyond restoring the pre-depth body or narrowing the merged one.
**We narrow rather than restore.** Both judges agree on the depth gain. The
secondary judge's scope failures do not distinguish the two options, and the
narrowed body is 18% shorter than the merged one. The labelling risk stays open
(see Limits).

Supplying the article's four-question prompt beside the pre-depth skill gave
the same results on the screened criteria.

This is authoring (A) evidence from three synthetic source bundles, one author
model, and text-only runs. It does not establish B task behavior, host selection,
or held-out performance.

Evidence: [`tests/behavior/evidence/depth-2026-11-04/`](../tests/behavior/evidence/depth-2026-11-04/).

## Packages

| Arm | `SKILL.md` | Words |
| --- | --- | ---: |
| Abase | `baa679f`, before #14 | 1,259 |
| Amain | `3135f5b`, #14 and #15 as merged | 2,159 |
| Amin | `3135f5b`, narrowed per the reviews below (shipped in #16; digests pinned by `tests/test_depth_evidence.py`) | 1,765 |
| Abase+F | Abase, plus the article's four-question prompt in the request | 1,259 |
| A0 | No authoring skill | — |

`plan.json` also has runs of `8385f9b` (A1) and `3c6f940` (A2). A mislabel is
corrected in `addendum-baseline.json`.

## Method

- **Author:** `claude -p --model fable`, served as `claude-fable-5-1`, with no
  tools and the 2026-11-01 author system prompt.
- **Deviation from 2026-11-01:** `--bare` now returns "Not logged in", so runs use
  `--setting-sources ''` instead. Claude Code still attaches an account-context
  reminder.
- **Bundles:**
  - D: churn review, development only, in the article's own domain.
  - X1: Android release crash triage, hint-free.
  - X2: payroll variance memo, hint-free.
  - Each bundle starts from a digested input, uses self-review as its check, and
    states an unevidenced cause as fact.
- **Guard bundles:** payments fidelity F1–F7 from 2026-11-01, narrow update N,
  and reserved name R.
- **Pre-registration:** criteria, arms, and decision rules were written and their
  digests recorded before each batch of runs (`plan.json`,
  `addendum-baseline.json`, `addendum-2.json`).
- **Judging:** one output per judge call, blind ids.
  - Primary judge: `claude-fable-5-1`.
  - Secondary judge, outside the model family: `gpt-6.1-sol` via `codex exec`.
- **Screening:** a criterion counts only where Abase failed it in at least 2 of 5
  runs.
- **Decision:** #9's discordant-pair rule.

## Results

Depth criteria, passes out of 5, primary judge:

| Criterion | A0 | Abase | Abase+F | Amain | Amin |
| --- | ---: | ---: | ---: | ---: | ---: |
| D1 account-level input (churn) | 0 | **1** | 5 | 5 | 5 |
| D2 method | 5 | 5 | 5 | 5 | 5 |
| D3 outside check | 5 | 5 | 5 | 5 | 5 |
| X1 crash-level input (crash triage) | — | 5 | 5 | 5 | 5 |
| X2 method | — | 5 | 5 | 5 | 5 |
| X3 outside check | — | 4 | 5 | 5 | 5 |
| Y1 transaction-level input (payroll) | — | 4 | 5 | 5 | 5 |
| Y2 method | — | 5 | 5 | 5 | 5 |
| Y3 outside check other than proofreading | — | **0** | 5 | 5 | 5 |

Screened in: D1 and Y3. Paired comparisons:

| Comparison | Primary judge | Secondary judge |
| --- | --- | --- |
| Amin vs Abase | 9 wins, 0 losses: value | 7–0: value |
| Amain vs Abase | 9–0: value | 7–0: value |
| Abase+F vs Abase | 9–0: value | 7–0: value |
| Amin vs Abase+F | 0–0: inconclusive | 0–0: inconclusive |
| Amin vs Amain | 0–0: inconclusive | 0–0: inconclusive |

**Guards:**

- Primary judge: Amin passed the scope criterion (D6, X6, Y6) in 15/15 runs,
  F1–F7 in 3/3, N1–N3 in 3/3, and the reserved-name check in 5/5. Its 4th, 5th,
  and 7th criteria were not worse than Abase.
- Secondary judge:
  - X5: Amin 1/5, Amain 1/5, Abase 3/5. Y5: Amin 0/5, Amain 0/5, Abase 2/5.
    That trips the fidelity guard for both depth variants.
  - Scope criterion (D6, X6, Y6): Amin 2/15, Amain 5/15, Abase 0/15. It trips
    the scope guard in every arm.
  - N3: Amin 0/3, Abase 0/3. The judge counted the hand-off notes after the
    edited file as added content.

**Cost and size, cases D, X1, and X2 (medians, 15 runs per arm):**

| Arm | Generated `SKILL.md` words | Output tokens | Mean cost (USD) |
| --- | ---: | ---: | ---: |
| Abase | 985 | 3,679 | 0.218 |
| Abase+F | 1,045 | 5,402 | 0.308 |
| Amain | 1,267 | 4,697 | 0.280 |
| Amin | 936 | 3,814 | 0.223 |

## Limits and open risks

- **Labelling of author additions is judge-dependent.** The secondary judge fails
  it more often for both depth variants than for the pre-depth skill (above).
  The two judges agree on 343 of 435 addendum-2 verdicts (79%).
- **Strict reading: author-derived steps.** An exploratory criterion written
  after the outputs were seen (`posthoc-proposal-activation.json`) failed all
  20 runs it judged. Those were case D only, 5 runs each of A1, A2, Abase, and
  Amain. Amin, Abase+F, X1, and X2 were not judged under it. It fails any
  author-derived step, stopping condition, or required input in an active
  procedure, which conflicts with the skill's own call for proportionate
  stopping conditions. It is recorded as a question to resolve, not as evidence
  for or against the narrowed version.
- **Generated frontmatter.** 8 of the 115 generated skills had an unquoted
  `description` containing `: `, which strict YAML rejects. 2 of these came from
  Amin, 4 from Abase+F, 1 from Abase, and 1 from Amain. The judges did not
  check this. `scripts/check_skill.py` reports all 8.
- **Discrimination rests on 2 criteria in 2 bundles.** D2–D4 and most X/Y
  criteria were already passed without the depth pass.
- **No B runs.** The plan conditioned B on a D-only result; the narrowed
  candidate changed where unconfirmed proposals go (the report, not the skill).
  Downstream task effect is unverified.
- **Judge-to-output binding is partial.** Primary judge records store the
  digest and length of their prompt; secondary records store the digest only.
  The prompt template was not archived, so `tests/test_depth_evidence.py` checks
  that each primary record's prompt length fits its mapped run output, and binds
  secondary records only through the blind map. The verdict text itself is not
  bound to its record, so moving verdicts between repeated runs of the same case
  and arm, or an equal-length edit to an output, is not detected.
- **Author spend: $46.57** for Claude runs and primary judging. Secondary judging
  ran on a Codex subscription and has no per-call cost record.
