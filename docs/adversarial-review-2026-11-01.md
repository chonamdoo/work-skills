# 2026-11-01 adversarial review (Fable) and follow-up probes

Claude Fable reviewed `work-to-skill` and
[epic #9](https://github.com/chonamdoo/work-skills/issues/9) against Anthropic's
[skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices).
It used the same yardstick as the
[2026-09-25 review](adversarial-review-2026-09-25.md): every proposal had to compare
its impact scope, benefits, and drawbacks with leaving the text unchanged, and zero
findings was an acceptable result. The parent session then ran the cheap,
pre-registered probes the review called for. Raw outputs are under
[tests/behavior/evidence/adversarial-review-2026-11-01](../tests/behavior/evidence/adversarial-review-2026-11-01).

| | Review | Probes |
| --- | --- | --- |
| Invocation | `claude -p --model fable --tools ""` | `claude -p --bare --model fable --tools "" --system-prompt <fixed>` from `/tmp` |
| Served model (response `modelUsage`) | `claude-fable-5-1` | `claude-fable-5-1` for all 23 runs and the judge |
| Provider-reported cost | USD 2.29 | USD 4.32 |

`--bare` with an explicit system prompt kept CLAUDE.md files, hooks, and installed
skills out of the probe context. The 49-input-token smoke call confirmed that
nothing else was injected. The review prompt embeds the Anthropic page verbatim,
so only its header and section digests are archived.

## Review result

The review made three findings about the skill text.

1. The naming rule (`SKILL.md:36`) does not mention host frontmatter limits.
   Anthropic's skill documentation disallows `claude` and `anthropic` in names.
   The finding was typed as a contract conflict, but the parent did not adopt it
   from text alone: the limit is host-specific, and it had not been observed in
   any generated skill. The review's proposed five-run probe was run instead
   (below).
2. The probe's A1 skill states authoring facts in its own body, for example "no
   runtime dependency on an authoring skill". This was an untested hypothesis
   from one artifact and was not acted on.
3. "No-skill baseline" (`validation.md:60`) does not say whether the baseline gets
   the same source knowledge. This was an untested hypothesis. It was acted on
   only together with the evaluation yardstick below, because the creator should
   not teach users a weaker baseline than the one this repository uses.

The review judged the other differences from the best practices to be deliberate
and justified: the 500-line guidance, third-person descriptions, gerund names,
the Haiku/Sonnet/Opus matrix, and the minimum of three evaluations. Whether
evaluation should come before authoring was left open. The page's claim that
no skill-writing skill is needed is a question about whether `work-to-skill`
is worth having, and only comparative evaluation can answer it.

The epic critique changed epic #9 as follows.

- The -2 pp non-inferiority rule cannot fire at feasible sample sizes. It was
  replaced with exact discordant-pair counts. The review proposed a 3:0 threshold,
  which the parent rejected (one-sided sign test p = 0.125) in favour of 5:0
  (p = 0.031).
- The no-knowledge arm became mandatory, because it screens out cases that cannot
  separate the arms.
- Real-host checks moved earlier.
- H3 was dropped. `SKILL.md:14` already asks about the destination only when
  neither the request nor the environment establishes it.
- The lifetime cost formula was split so that the sunk authoring cost of the
  current version does not count against keeping it.

## Probes

Rubrics and decision rules were frozen before each batch. The frozen files'
digests are recorded in `experiments.inputs.json`.

| Probe | Question | Result | Decision |
| --- | --- | --- | --- |
| O: original epic case × empty/source/A0/A1 | Does the case separate the arms? | 4/4 arms pass, including empty | The case has a ceiling effect. Its request contained the answer hints. |
| R: hint-free replacement × empty/source | Same, without hints | 2/2 pass. Skill arms were not run, per the screening rule | Also a ceiling. These synthetic rules match the model's priors. |
| H2: evaluate a supplied generated skill with the package, ×5 | Does `validation.md` section A make evaluators demand a creator re-authoring run? | 0/5 | H2 closed, no change |
| RW: Claude-API review rules with the current package, ×5 | Does the creator emit reserved names? | 5/5 `claude-api-call-review` | Threshold (≥2/5) met, so a candidate was written |
| RW2: same request with the candidate package, ×5 | Does the candidate fix it? | 0/5 (`model-api-call-review` ×4, `messages-api-call-review` ×1) | Adopted |
| REG: the epic's authoring request with the candidate package, ×2 | Is a user-specified name preserved? | 2/2 `incident-update-review` | No regression on naming |

O and R were also scored by a blinded Fable judge, with arm labels hidden and the
order shuffled. Its verdicts matched the parent's reading. These observations
were not scored because no frozen criterion covered them:

- R-empty invented a telemetry fact ("holding at 0.8%").
- All five H2 evaluators noted that the A1 artifact does not label its derived
  guidance as author inference.

Both are inputs for the next frozen rubric. They are not retroactive failures.

## Changes

- `SKILL.md:36`: respect the documented frontmatter limits of the hosts where the
  skill may be used, with Anthropic's reserved words as the example. This is
  supported by RW and RW2, and REG found no naming regression.
- `validation.md:60`: compare against a baseline given the same source knowledge
  without the skill, or against the previous version. A case that a baseline
  without that knowledge already passes cannot show improvement. Probes O and R
  are direct instances of this.

## Limits

- Text-only runs on one model and host. Nothing here observes automatic discovery,
  tool use, or installation.
- The RW probes used one request, so they show that the candidate removed a
  reproducible failure, not a rate across requests.
- O and R found no case that discriminates between the arms. No claim about the
  value of `work-to-skill` or of the generated skills follows.
- Model judgments are not expert certification.
