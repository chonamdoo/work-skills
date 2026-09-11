# v0.1.0 validation

This is a reviewed initial release, not certification of professional accuracy or
universal AI compatibility. Checks were performed on 2026-09-11.

## What was evaluated

- Author: GPT-6 Astra in a Codex app subagent.
- Independent reviewers: another GPT-6 Astra subagent and Claude Fable 5.1 in
  Claude Code CLI. Both approved the corrected implementation.
- Behavioral executors: fresh Codex app Astra subagents and fresh Fable CLI
  processes. Inputs were explicitly supplied; these were text-only tasks.
  No skill was globally installed and no business action was executed.
- Fable responses record `claude-fable-5-1` in model usage. The CLI also recorded
  auxiliary Haiku usage; Haiku was not substituted for the requested reviewer.
- The local Codex CLI rejected Astra because it required a newer CLI. We did not
  upgrade it or switch models; Astra execution used the app's subagent capability.

## Package versions

| Phase | SKILL.md SHA-256 | Purpose |
| --- | --- | --- |
| r1 | d4b0f52c13a5d9538c17160969fc5968d05757e158b3f7ce26eed76f4a2f9676 | Initial implementation |
| r2 | 16042d74e8f246423bd7fb472fa7df0861f4650600a60fb9133bd48d5dc22493 | Source facts and author inference separated |
| r3 / release | 7a4361fb753f3951b76886bbe839840b9c933ce66f6688833d6de8cf943548bf | Source-artifact fallback and metadata preservation clarified |

`references/validation.md` remained unchanged:
`faa5999767fd997f1598fce4cf545d27f8770813b93c2d0d2b7c3ac5f2b4918c`.

## A: authoring behavior

[Inputs and evaluator criteria](../tests/behavior/cases.json) were prepared before
the corresponding execution. Executors received requests and the skill package,
not acceptance answers. [Full captured outputs](../tests/behavior/evidence/v0.1.0/authoring.json)
include failures, phase identifiers, and evaluator notes.

| Cases | Observation |
| --- | --- |
| A1 development, A4 reference, A6 narrow update | Both models met the checked criteria in r3 regression runs. Exceptions survived; source affiliation was no longer invented; existing metadata survived the update. |
| A2 planning, A3 synthetic intake, A5 ordinary request | Both models met the checked criteria in r1. These cases were not re-authored after the narrow provenance/metadata changes. |
| A7 new provenance case | Both models preserved missing identity/date and excluded the synthetic private marker. This is limited evidence: Fable retained the source contradiction but favored definitions for new decisions. Conflict-resolution behavior was not validated. |

There were 24 authoring executions across the three phases, not 24 independent
proofs of quality. The same regression cases were deliberately reused.

### Failures and corrections

1. Fable r1 A1 attributed author-derived alternatives to team acceptance.
2. Fable r1 A4 invented how the explanation was received and conflated the
   authoring date with when the definitions took effect.
3. Fable r2 A4 corrected the date but still inferred the original expert's
   affiliation from the requester's team context.

After independent review, the creator was corrected to distinguish source facts
from derived guidance, distinguish date types, and identify the supplied artifact
when the original speaker is unknown. The final A1/A4 regression outputs passed
these checks on both models. This does not establish a zero failure rate.

## B: generated-task behavior

[New task inputs](../tests/behavior/tasks.json) were provided in fresh contexts
with only the generated task skill, its own resources, and the task inputs.
Executors did not receive work-to-skill, authoring history, reviewer findings,
or reference answers.

All four tasks were cross-executed: Astra used Fable-generated skills and Fable
used Astra-generated skills. [Captured outcomes](../tests/behavior/evidence/v0.1.0/execution.json)
link each run to the exact authoring output.

- B1: identified the unsafe late-response overwrite and the permitted fully
  disabled-editing exception. Fable also asked to inspect the implementation of
  the editing lock; it did not require revision checking in an already safe case.
- B2: separated internal observations from assumptions and did not invent
  customer demand, measurements, or a launch commitment.
- B3: identified the period mismatch and unresolved checklist authority and did
  not call the synthetic intake complete.
- B4: classified the private preview as queued, the unowned proposal as planned,
  and the public recorded URL as shipped.

Eight initial B executions met these bounded task criteria. Four additional
executions rechecked B1/B4 using r3-generated skills. B2/B3 used r1-generated
skills. These were text/code-inspection tasks, not runtime UI tests, filing tests,
or validation of real tax advice.

## Static and distribution checks

- Four Python package tests passed: metadata/body, local reference containment,
  release/runtime separation, and authoring case identifiers.
- Codex's installed quick validator accepted work-to-skill.
- Whitespace checks passed locally; CI checks committed content against the
  empty tree rather than comparing a clean checkout with itself.
- Candidate archive inspection showed only the work-to-skill directory,
  SKILL.md, and references/validation.md. Evaluation records are outside that tree.
- There is no application build or configured static type checker. Archive
  construction and package checks are the relevant build checks for this release.

[Review records](../tests/behavior/evidence/v0.1.0/reviews.json) include the Fable
findings and final approval, and summaries of Astra's independent review cycle.
Review-driven fixes also preserve existing metadata during updates and make the
CI whitespace check inspect committed content.

## Limits

Native installation, automatic discovery with other creators present, global
deduplication, other hosts/models, and tool-enabled execution were not tested.
File readability and explicitly supplied instructions are not proof of automatic
skill selection. No gain over a no-skill baseline, cost saving, statistical
reliability, complete conflict resolution, or professional certification is claimed.
All inputs are synthetic; no customer documents or live confidential data were used.
The final provenance-focused cases are regressions, not a new held-out benchmark.
