# 2026-11-04 adversarial review of the depth pass (#14)

Two read-only adversarial reviewers checked
[#14](https://github.com/chonamdoo/work-skills/pull/14) at `3c6f940` against
[Felix Rieseberg's "How to be more ambitious"](https://felixrieseberg.com/how-to-be-more-ambitious-a-tutorial-for-humans-with-models/)
and this skill's existing provenance, authorization, and scope rules. Each
proposal had to compare its impact with leaving the text unchanged. #14 merged
at `8385f9b` with commit `1e10637`, which already addressed several findings;
this record covers what remained on main.

| Reviewer | Agent | Findings |
| --- | --- | --- |
| R1 | omp `adversarial-opus55` subagent (Claude Opus 5.5) | 11 |
| R2 | omp `adversarial-sol61` subagent (GPT-6.1-sol) | 1 |

## Disposition

| Finding | Text conflict | Status |
| --- | --- | --- |
| R2-1, R1-7: `validation.md` labeled every borrowed method a proposal, including methods the source itself requires | `SKILL.md` "Treat a sourced answer according to its authority" | Fixed: only author-proposed methods are labeled proposals. |
| R1-1, R1-3: belief testing had no actor and demoted any source-stated fact | `SKILL.md` "Keep creation separate from … real business execution"; sourced answers keep their authority | Authoring-time testing fixed in `1e10637`. Fixed here: only empirical claims given without evidence become judgments; definitions, criteria, and requirements keep their status. |
| R1-2: another model's review could count as the outside check | `SKILL.md` "another model's approval cannot substitute for B"; article: "Do *not* ask the model to judge itself" | Fixed in the outside-check question and the gap rule. |
| R1-4: inferred outcome used as a source | Author inferences must stay visibly distinct | Fixed in `1e10637`. |
| R1-5: a substantial update deepened unrelated parts | "change only the requested behavior" | Fixed: the pass covers the changed behavior; unchanged parts only on request. |
| R1-6: no rule for an outside check unavailable at run time | Missing tools are not evidence that an action ran | Fixed: state its access condition; report the result as unverified. |
| R1-7: A9 criteria contradicted the skill | `validation.md` allows unresolved outcomes | Fixed in `1e10637`. |
| R1-8: README evaluation results not tied to a package version | — | Fixed: README states the results predate #14. |
| R1-9: pending proposals not reported | — | Fixed in `1e10637`. |
| R1-10: A8 first criterion passed on current practice | — | Fixed: requires evidence less digested than the copied top-three reasons. |
| R1-11: Kelley and Littman uncredited | Provenance rules | Fixed in README sources. |

## Behavior smoke

Text-only runs: the package was supplied as the system prompt of a fresh omp
`completion(model="slow")` call, and a second call of the same role judged the
output against the evaluator-only criteria in `tests/behavior/cases.json`. The
served model id was not recorded. Outputs were not archived. These are
development checks on reused cases, not a comparative evaluation.

| Case | main `8385f9b` | This change |
| --- | --- | --- |
| A4-reference | — | 3/3 criteria |
| A6-update | — | 2/2 criteria |
| A8-depth, criterion 3 (proposals inactive) | 0 of 1 run (`3c6f940`: 0 of 1) | 0 of 1 before the build-step sentence, 2 of 3 after |
| A9-outcome-range | 4/4 criteria | 4/4 criteria |

A8 criterion 3 failed on main and on `3c6f940` (one run each): labeled proposals
were placed inside procedure steps and so ran unconfirmed. The build and review
steps now state that a proposal label inside a step still makes it active. One
of three runs still put an author-added stopping rule inside the procedure.

A8 criterion 1 was revised after observing outputs. Once proposals stayed
inactive, a run that offered full exit notes only as an inactive option failed
it, although the skill requires exactly that when the user cannot confirm. The
criterion now accepts either sourced practice or an inactive labeled proposal.
The three A8 runs after the build-step sentence and the main run were rescored
with the revised criterion; all four pass criterion 1.
