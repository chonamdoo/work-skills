# 2026-11-04 adversarial review of main (`25571f3`)

Two read-only adversarial reviewers checked `work-to-skill` on main after #16,
with the prior reviews' dispositions as context. Each proposal had to compare
its impact with leaving the text unchanged; zero findings was acceptable.

| Reviewer | Agent | Findings | Verdict |
| --- | --- | --- | --- |
| R1 | omp `adversarial-opus55` subagent (Claude Opus 5.5) | 5 (F1–F5) | change recommended (F1, with a same-condition rerun) |
| R2 | omp `adversarial-sol61` subagent (GPT-6.1-sol) | 1 | change recommended (checker only); body unchanged |

**Result: the `SKILL.md` body is unchanged.** Neither candidate body edit met the
`I9-reproduced-failure` rule when rerun under the same conditions. The checker,
one evaluation criterion, and the README changed.

## Disposition

| Finding | Type | Status |
| --- | --- | --- |
| R2-1: without PyYAML, `check_skill.py` treated any value starting with `[` or `{` as a valid empty collection, so `metadata: {` passed with exit 0 | factual, reproduced | Fixed. Flow collections are reported as unchecked (exit 2) without PyYAML. This also stops a valid `{owner: team}` from failing on the `: ` rule. The guard is `test_unreadable_yaml_is_unchecked_not_invalid`. |
| R1-F1: answer-only authoring returns frontmatter with an unquoted `: ` (invalid YAML) | measured, pre-existing | Not changed. The candidate sentence did not reduce the failure (below). The checker still catches it wherever it runs. |
| R1-F2: `SKILL.md:14` asks for the outcome in the report, but the report list at `:74` omits it | text gap | Not changed. Rerun result was inconclusive (below). |
| R1-F3: A9 criterion 1 accepted an inferred outcome in the skill, which `SKILL.md:14` disallows | eval-data contradiction | Fixed. The inference is accepted only in the report. |
| R1-F4: the `:28` "inference" label lets unconfirmed depth answers into the skill | behavioral hypothesis | Flagged only. This is already an open risk in `evaluation-2026-11-04-depth.md` Limits. The reviewer recommends a pre-registered rejudging of archived Amin outputs. |
| R1-F5: README says the checker uses only the standard library | factual | Fixed. It uses PyYAML when installed. |

## Same-condition rerun

These runs were recorded after they finished and were not pre-registered.

- **Author:** `claude -p --model fable` (served `claude-fable-5-1`), no tools,
  with the `plan.json` author system and composition.
  - The X1 prompt rebuilt from main reproduces the recorded Amin
    `prompt_sha256` (`affcddab5cdc…`).
- **Judge:** the `plan.json` judge (fable) with blind ids. It judged the new runs
  and rejudged Amin's archived X1/X2 outputs with the same prompt.
  - An added criterion O checks that the outcome is stated, labeled, and kept out
    of the skill when it is inferred.
- **Frontmatter check:** PyYAML `safe_load` on the returned `SKILL.md` frontmatter.

Evidence is in
[`tests/behavior/evidence/review-2026-11-04b/`](../tests/behavior/evidence/review-2026-11-04b/).
Provider-reported cost was USD 10.51.

| Package | Invalid YAML frontmatter (X1 + X2) | O passes | X1–X8, Y1–Y8 |
| --- | --- | --- | --- |
| Amin (main) | 1 of 10 | 7 of 10 | all 5/5 |
| F1 + F2 | 1 of 10 | not judged | not judged |
| F2 only | 2 of 10 | 9 of 10 | all 5/5 |

- **F1:** no reduction in invalid frontmatter, so the sentence was withdrawn.
- **F2:** 3 wins and 1 loss on O. That is inconclusive under the #9 pair rule
  (wins ≥ 5, losses = 0). The loss was a run that labeled its inferred outcome in
  the report but stated the rollout decision unlabeled in the skill. F2 was
  withdrawn.
- One judge and one author model; this is A evidence on development bundles.
