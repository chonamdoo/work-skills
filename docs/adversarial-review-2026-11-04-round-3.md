# 2026-11-04 third-round adversarial review

Read-only adversarial reviewers checked `main` at `25571f3` (#16), then the fix
for this round. Each reviewer ran in a fresh context without the others' output.

| Reviewer | Agent | Scope |
| --- | --- | --- |
| C1 | Claude Code CLI, `claude -p --model opus`, instructions focus | `SKILL.md`, `validation.md`, cases, docs |
| C2 | Claude Code CLI, `claude -p --model opus`, script focus | `scripts/check_skill.py` and its tests |
| S | omp `adversarial-sol61` subagent (GPT-6.1-sol) | whole package and evidence |

All three returned NOT MERGEABLE on `25571f3`, and all three returned NOT
MERGEABLE on the first fix. The first fix edited `SKILL.md` and
`references/validation.md`. C1 and C2 both found that this broke the
pre-registered `judge_disagreement` rule in `addendum-2.json` ("do not ship a
body change beyond the restore/narrow default") and ledger entry
`I9-reproduced-failure`. Those edits were reverted. The shipped files again
match the evaluated Amin digests, and
`RecordedDepthEvaluationTests.test_shipped_instructions_are_the_evaluated_candidate`
now enforces this.

## Fixed

| Finding | Change |
| --- | --- |
| C2, S: fallback rejected valid frontmatter (flow mappings, comment-first or column-0-comment mappings, quoted keys, unindented sequences, keys containing `:`) | Block mappings, quoted keys, and unindented sequences are parsed. Flow collections report "frontmatter not checked" (exit 3). |
| C2, S: `\|+` length off by one; a less-indented comment inside a block scalar failed | Header lines are split without a trailing empty line. Block indentation is detected as PyYAML detects it, and a less-indented comment ends the scalar. |
| C2: plain scalars typed differently from PyYAML (`08`, `1e3`, `on`, `0x1f`) | PyYAML's YAML 1.1 implicit resolvers are used. |
| C2, S: PyYAML path accepted duplicate keys; the duplicate-key loader then rejected `<<` merges | The loader rejects keys repeated in one mapping and leaves merge keys to SafeLoader. |
| C2: unreadable `.md` files, `x.md` directories, and broken symlinks crashed the checker | Each case is reported; a symlink to a directory is skipped. |
| C2: unsupported frontmatter skipped link and placeholder checks | The body is checked regardless; exit 3 is kept separate from usage errors (exit 2). |
| C2, S: link destinations with parentheses, `<...>`, or escapes were truncated; links split across lines were missed; reference-style links were ignored | Inline links are parsed through the closing `)`, with one line break allowed, and reference definitions are recognised. |
| C2: reference definitions matched `[Field]: text` and lines inside a paragraph | A definition needs a destination with only an optional title after it, and must not interrupt a paragraph. |
| C2: `compatibility` over 500 characters passed | Fails. |
| C2: a UTF-8 byte-order mark failed with a misleading message | The message names the mark. |
| S: depth evidence had no integrity check | `tests/test_depth_evidence.py` recomputes every stored aggregate and the documented numbers from the raw runs and verdicts. |
| S: README overstated the depth result | The README states 9–0 and 7–0 on 2 screened criteria, that gaps and proposals count, and that the result is judge-dependent. |
| Evidence test: the secondary narrow-update guard trip was not stated | Stated in the evaluation decision. |
| C1 N4: superseded sentence in the 2026-11-04 review | Annotated. |

A generated parity test now compares the fallback with PyYAML on 400 generated
frontmatters. A throwaway run over 50 seeds (20,000 frontmatters) found no
mismatch.

## Declined, with reasons

| Finding | Reason |
| --- | --- |
| S B1: non-string `metadata` values and list-form `allowed-tools` should fail | The reference validator `skills-ref` converts metadata values with `str()` and does not check the type of `allowed-tools`. Both stay warnings. |
| S S1: bind verdicts to outputs by prompt digest | The judge prompt template was not archived, and rebuilding it from the recorded fields did not reproduce `prompt_sha256`. The limit is recorded in the evaluation's Limits section. |

## Deferred: body changes that need a reproduced failure and a rerun

C1 and C2 found these conflicts in the evaluated text. Under
`I9-reproduced-failure`, each needs a reproduced failure and a same-condition
candidate rerun before it can ship.

- `SKILL.md` still says both "label them in the generated file" for derived
  interpretations and "leave unconfirmed proposals out of the generated skill".
  This is the open labelling risk in the evaluation. A smoke run on this round's
  reverted edit put an unlabelled test method inside the skill (A9, 1 of 1 run).
  That is a candidate reproduction, not a pre-registered one.
- The script instruction says to run it "from this skill's folder" with a
  `<skill-dir>` argument. It does not say what to report when the draft exists
  only in the response.
- "Narrow update" has no definition. The assess-mode depth rule ("advisory")
  and the Depth branch in `validation.md` can be read as being in conflict.
- The hand-off report list omits the outcome note required in "Establish the
  assignment".

## Evaluator criteria revised after outputs were seen

These revisions are in `tests/behavior/cases.json`. Earlier scores were not
rescored.

- A9 criterion 1, before: "Records what the review is for as supplied or as a
  labeled author inference, in the report or the skill, or leaves it open …".
  The skill says to state the outcome in the skill only when it is supplied or
  confirmed, so the criterion now requires that.
- A9 criterion 3, before: "No persona or tone instruction; …". Nothing in the
  skill supports failing a persona instruction by itself. The criterion now
  says only that a persona or tone instruction does not count as a method.

## Checks

The suite ran locally, with and without PyYAML, together with Git's whitespace
check over the committed tree. GitHub Actions was paused for this change.
Smoke runs on the reverted instruction edit are development observations and
are not evidence for the shipped text.
