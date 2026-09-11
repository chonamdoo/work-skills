# v0.1.1 rubric validation

This release strengthens the existing A/B evaluation reference for work-to-skill
and its generated skills. It adds task-grounded criterion records, justified
requiredness, valid uncertainty versus avoidance, four distinct result states,
and evidence-bounded verification claims. It does not add a runtime framework,
mandatory model/case counts, or evaluator answer keys to generated skills.

## Exact scope

SKILL.md is unchanged from v0.1.0:
`7a4361fb753f3951b76886bbe839840b9c933ce66f6688833d6de8cf943548bf`.

The initial enhanced reference had SHA-256
`8e6aeb63a45e9435a18df7cce87385811ce67150569175221edec355ffd450a2`.
After a reporting failure was observed, one evidence-granularity sentence was
added. The final reference SHA-256 is
`3d9538774bc7a30d872c57457655fd1ffcf20f2271792653250dd83b7276eb38`.

The guidance remains profession-neutral. This change was exercised on synthetic
planning/reference authoring, generated meeting-note interpretation, and studio
visibility evaluation. These checks are not evidence of professional correctness
in every occupation. The broader historical cases remain documented separately
in [v0.1.0 validation](validation-v0.1.0.md); that entire suite was not rerun.

## Criteria before grading

[Raw requests](../tests/behavior/rubric-inputs.json) and
[evaluator-only expectations](../tests/behavior/rubric-expectations.json) are
separate. Executors received only their request and relevant skill package.

The first criteria version was fixed before task dispatch. Independent review
requested explicit source locators, conditions, required reasons, team-only scope
and East's unresolved classification. Those clarifications formed v2 after
dispatch but before any executor output was inspected or graded. Both versions
and every captured result are preserved in the
[evaluation record](../tests/behavior/evidence/v0.1.1/rubric.json).
All results were graded consistently against v2. This is development/regression
evidence, not a held-out performance or no-skill improvement claim.

## Observed results

| Check | Astra | Fable | Evidence scope |
| --- | --- | --- | --- |
| A: create decision-state and a separate rubric | pass | pass | Team definitions, exceptions, unknown authority, standalone package and unrun checks preserved. |
| R: evaluate illustrative studio responses, initial | pass | fail | Fable claimed folder-name agreement from supplied contents alone; R4 failed. |
| B: use the other model's generated skill | pass | pass | Delta confirmed, Echo exploring, Foxtrot authority unresolved on new notes. |
| R: regression with final evidence clarification | pass | pass | Both distinguish supplied text from unverified filesystem, B and discovery properties. |

There were eight task executions. R's four illustrative response pairs are not
four real B executions. They test whether the evaluator rejects an unjustified
table requirement, unjustified avoidance, unsupported classification and fake
expert certification while accepting supported work and appropriate uncertainty.
Because R includes candidate responses, it is not a blind rubric-construction
exercise. It also cannot prove the supplied studio skill caused those responses.

The original Fable R4 failure remains in the record. The correction and its
regression passing do not establish a zero failure rate. A and B used the initial
enhancement; final R reruns test the later, narrow evidence clarification.

## Review and verification

Independent GPT-6 Astra and Claude Fable 5.1 reviewed the changes. Fixture issues
were corrected, and both approved the final evidence clarification. One Fable
review response merely announced future inspection; it was not counted as an
approval and was retried. Review summaries and Fable results are in the record.

Four package tests, the installed Codex skill validator, and local whitespace
checks passed. These structural checks do not substitute for behavioral results.
CI and the release pipeline check the committed candidate and package assets.

No independent executor or business tools existed *inside* the authoring and
rubric-evaluation tasks. Their unverified reports are therefore correct. The
host controller separately ran the B tasks in new contexts, with only the
generated task skill and new task facts. It did not forward the creator, rubric,
authoring reports, prior results, or evaluator expectations to those B executors.

## Limits

Astra used fresh Codex app subagents with inherited host system/developer
instructions. No additional creator instruction files were reported loaded.
Fable used fresh Claude Code CLI processes with tools and slash commands disabled;
recorded model usage confirms claude-fable-5-1, with auxiliary Haiku usage.
All inputs were explicitly supplied, so this is not automatic discovery evidence.

All result judgments are source-grounded model comparisons with synthetic,
user-defined criteria. They are not qualified human assessments. Labels such as
mechanical or manual inside a response do not establish that a program or human
checker ran. No customer data, submissions, messages, deployments, or other
business actions were part of these cases.

Native discovery, other models/hosts, real tool-using procedures, professional
certification, baseline improvement, statistical reliability and cost savings
remain unverified. Updating this creator does not rewrite previously generated
or installed skills.
