# 2026-11-04 third-round adversarial review

Read-only adversarial reviewers checked `main` at `25571f3` (#16), then the fix
for this round. Each reviewer ran in a fresh context without the others' output.

| Reviewer | Agent | Scope |
| --- | --- | --- |
| C1 | Claude Code CLI, `claude -p --model opus`, instructions focus | `SKILL.md`, `validation.md`, cases, docs |
| C2 | Claude Code CLI, `claude -p --model opus`, script focus | `scripts/check_skill.py` and its tests |
| S | omp `adversarial-sol61` subagent (GPT-6.1-sol) | whole package and evidence |

All three returned NOT MERGEABLE on `25571f3` and again on the first fix. That
fix edited `SKILL.md` and `references/validation.md`. C1 and C2 both found that
this broke the pre-registered `judge_disagreement` rule in `addendum-2.json`
("do not ship a body change beyond the restore/narrow default") and ledger
entry `I9-reproduced-failure`. Those edits were reverted. The shipped files again
match the evaluated Amin digests, and
`RecordedDepthEvaluationTests.test_shipped_instructions_are_the_evaluated_candidate`
now enforces this. On the second fix, C1 returned MERGEABLE. C2 and S returned
NOT MERGEABLE on parser and link findings. On the third fix, C1 again returned
MERGEABLE, while C2 and S found regressions from that fix: tabs inside nested
quoted or block values were rejected, a link inside link text made the outer
text count as a link, and time zones were dropped from timestamps. The fourth
fix addressed those. On it, C2 and S found more edge inputs (tabs in other
positions, quoted values continued at column 0, column-0 comments in block
values, empty and image link destinations, and a crash on malformed URLs).

The fifth fix changes approach for the fallback YAML parser. Matching every
PyYAML edge case had kept producing new wrong verdicts. The fallback now judges
only input it fully reads. For anything else it reports "frontmatter not checked"
(exit 3), which is neither a pass nor a failure. On the fifth fix, C2 found
inputs the fallback still judged without fully reading them: control and
separator characters, a plain `=`, list item contents, comments inside nested
values, and inline-level link text (code spans of several backticks, escaped
`[`, entities). The sixth fix closes those. All findings below are addressed or
declined.

## Fixed

| Finding | Change |
| --- | --- |
| C2, S: fallback rejected valid frontmatter (flow mappings, comment-first or column-0-comment mappings, quoted keys, unindented sequences, keys containing `:`) | Block mappings, quoted keys, and unindented sequences are parsed. Flow collections report "frontmatter not checked" (exit 3). |
| C2, S: `\|+` length off by one; a less-indented comment inside a block scalar failed | Header lines are split without a trailing empty line. Block indentation is detected as PyYAML detects it, and a less-indented comment ends the scalar. |
| C2: plain scalars typed differently from PyYAML (`08`, `1e3`, `on`, `0x1f`) | PyYAML's YAML 1.1 implicit resolvers are used. |
| C2, S: PyYAML path accepted duplicate keys; the duplicate-key loader then rejected `<<` merges | The loader rejects keys repeated in one mapping and leaves merge keys to SafeLoader. |
| C2: unreadable `.md` files, `x.md` directories, and broken symlinks crashed the checker | Each case is reported; a symlink to a directory is skipped. |
| C2: unsupported frontmatter skipped link and placeholder checks | The body is checked regardless; exit 3 is kept separate from usage errors (exit 2). |
| C2, S: link destinations with parentheses, `<...>`, or escapes were truncated; links split across lines were missed | Inline links are parsed through the closing `)`. One line break is allowed in link text and around the destination, and one level of nested brackets is allowed in link text, so linked images are covered. |
| C2: links inside HTML comments were checked | HTML comments are skipped. |
| S: a comment before a value was read as ending the value | Only a comment after the value has started ends it. |
| S: plain and quoted keys such as `42` and `"42"` were merged into one duplicate key | Plain keys are typed as PyYAML types them. |
| C2: dates were typed as strings; a `...` document end failed; a `<<` block key produced a false metadata warning | Timestamps resolve to dates and datetimes, and their time zone is kept. `...` ends the document. Merge keys report "frontmatter not checked". |
| C2, S: tabs were accepted where PyYAML rejects them, and rejected inside valid quoted and block values | Without PyYAML, frontmatter containing a tab reports "frontmatter not checked". |
| C2, S: a quoted value continued at column 0, a column-0 comment inside a block value, and a block indicator on the line after the key were misjudged | Each reports "frontmatter not checked". |
| C2: control characters, NEL, and line or paragraph separators passed; a plain `=` or `<<` passed; plain values starting with `,`, `]`, or `}` passed | Unusual characters and `=`/`<<` report "frontmatter not checked". Plain values starting with `,`, `]`, or `}` fail, as in PyYAML. |
| C2: list items were not read, so an unterminated quote or an alias in a list passed | Each single-line list item is read. Items that span lines, nest, or hold complex keys report "frontmatter not checked". |
| C2: comments inside nested values were dropped, so they did not end a plain value | Comments keep their place in nested mappings. |
| C2: code spans of two or more backticks, code spans across a line break, escaped `[`, and entities in destinations produced false link failures | Code spans follow CommonMark backtick matching, escaped `[` opens no link, and `&amp;`-style entities in destinations are decoded. |
| C2: an unclosed `(` repeated through a file made link checking quadratic | Parenthesis nesting in a destination is capped at 32, which CommonMark permits. A 200,000-character case runs in under a second. |
| S: the outer text of `[outer [inner](a.md)](b.md)` was checked as a link, including around empty destinations and after an escaped `!` | Link text that holds a complete non-image link, including one with an empty destination, makes the outer text plain, as CommonMark specifies. An escaped `!` does not open an image. |
| S: a link inside an image description voided the image | Images may describe links; the image destination is checked. |
| S: a malformed URL such as `<//[>` or a NUL escape crashed the checker | Reported as "not a valid local path"; checking continues. |
| C2: `compatibility` over 500 characters passed | Fails. |
| C2: a UTF-8 byte-order mark failed with a misleading message | The message names the mark. |
| S: depth evidence had no integrity check | `tests/test_depth_evidence.py` recomputes every stored aggregate and the documented numbers from the raw runs and verdicts. |
| S: README overstated the depth result | The README states 9–0 and 7–0 on 2 screened criteria, that gaps and proposals count, and that the result is judge-dependent. |
| Evidence test: the secondary narrow-update guard trip was not stated | Stated in the evaluation decision. |
| C1 N4: superseded sentence in the 2026-11-04 review | Annotated. |

A generated parity test compares the fallback with PyYAML on 400 generated
frontmatters, covering dates, time zones, tabs, typed keys, comments, document
ends, indicator characters, control characters, list items, and nested comments.
It compares nested values with their types, and it accepts "frontmatter not
checked" as an outcome. The generator puts one space after each `:`, so other
separators are covered only by the fixed cases. Throwaway runs found no value
mismatch over 60 seeds (24,000 frontmatters) and no verdict mismatch over 200
seeds (80,000 frontmatters).

## Declined, with reasons

| Finding | Reason |
| --- | --- |
| S B1: non-string `metadata` values and list-form `allowed-tools` should fail | The reference validator `skills-ref` converts metadata values with `str()` and does not check the type of `allowed-tools`. Both stay warnings. |
| S S1: bind verdicts to outputs by prompt digest | The judge prompt template was not archived, and rebuilding it from the recorded fields did not reproduce `prompt_sha256`. The evaluation's Limits section states what the remaining binding covers: length for primary records, the blind map alone for secondary records. |
| C2, S: reference-style definitions (`[r]: path`) produced false failures on template lines such as `[Severity]: high`, unterminated titles, and `#hashtag` paragraphs, and were missed inside lists and block quotes | Reference-definition checking, added earlier in this round, was removed. Telling definitions apart from template lines needs a full CommonMark block parser. Reference-style links stay unchecked, as they were on `main`, and the documentation says so. |
| C2: links in indented code blocks are checked | Indented code cannot be told apart from indented list content without a block parser. Unchanged from `main`. |

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

The full suite ran locally with PyYAML installed. The checker tests also ran
without PyYAML; `tests/test_package.py` imports PyYAML and does not run without
it. Git's whitespace check ran over the committed tree. GitHub Actions was paused
for this change.
Smoke runs on the reverted instruction edit are development observations and
are not evidence for the shipped text.
