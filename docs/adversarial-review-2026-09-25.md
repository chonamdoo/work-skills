# 2026-09-25 adversarial review

Two independent reviewers, Codex Astra and Claude Fable, ran in parallel on
identical prompts. Fable ran with tools disabled; Codex ran in a read-only
sandbox and its event stream recorded no tool calls (the stream itself is not
archived, only the final message). Each review asked for zero findings when
nothing is justified and required, for every finding, a quoted line, an
evidence type, and a direct comparison of impact scope, benefits, and drawbacks
against leaving the text unchanged. The same yardstick was applied to both
rounds. Raw outputs are under
[tests/behavior/evidence/adversarial-review-2026-09-25](../tests/behavior/evidence/adversarial-review-2026-09-25).
The round 1 prompt is archived in full (trailing whitespace on its blank
numbered lines was stripped for the repository whitespace check). The round 2
prompt embeds five third-party files verbatim and is not archived; its header,
section order, per-section origins, and SHA-256 digests are in
`work-to-skill.prompt-manifest.md`, so identical input to both reviewers is
verifiable by digest but the prompt is not reproducible from this repository
alone.

| | Codex Astra | Claude Fable |
| --- | --- | --- |
| Invocation | `codex exec -m gpt-6-astra --ephemeral -s read-only` | `claude -p --model fable --tools ""` |
| Model evidence | CLI flag only; the Codex event stream does not echo the served model | Response metadata `canonicalModel: claude-fable-5-1` |

## Round 1: anthropics/skills `claude-api/shared/prompt-audit.md`

Target: the upstream file at `main` on 2026-09-25 (223 lines), reviewed as
data, not executed. Findings are tracked in
[issue #7](https://github.com/chonamdoo/work-skills/issues/7); this file
records only the outcome.

- Three conflicts were reported by both reviewers with overlapping line
  citations (parentheses give the primary conflicting pair; full line sets
  are in the JSON): pattern match promoted to medium confidence (L206 versus L12,
  L201; Fable also L39, L102, L204); Step 6 "stop there" placed before Step 7
  verification and pre-deletion checks (L215 versus L219; Fable also L222);
  numeric ceilings removed even with a stated reason (L125 versus keep-list
  L177; Fable also L83).
- Astra alone reported user-named scope versus "every code path" removal
  (L20 versus L213-214).
- Fable alone reported three more: the 1e prohibition test versus 1c and
  keep-list 5 (L121 versus L95, L181); "before reading any file" versus a
  target-model resolution that requires reading files (L18 versus L21); and
  ambiguous apply-consent examples (L10 versus L215).
- Evidence type for all seven is text contradiction within the document. No
  behavioral experiment was run; none of the findings claims one.
- Not filed: two earlier candidates from a non-model-pinned review (mandatory
  tool-call guarantee under `tool_choice: auto`; "exactly one model call") were
  not reported by either pinned reviewer and are excluded from the issue.

## Comparison with other guidance

- OpenAI `openai/skills` `skills/.system/openai-docs/references/`
  (`49f948f`, 2026-06-23): `prompting-guide.md` shares the direction of
  prompt-audit 1a and 1c (avoid carrying over legacy over-specification;
  reserve `ALWAYS`/`NEVER`/`must` for true invariants). `upgrade-guide.md`
  takes the opposite posture on scope: "narrowest safe change set", leave
  pinned or fallback model sites unchanged and report them as
  confirmation-needed, "avoid broad prompt cleanup unrelated to the upgrade",
  and mark API-surface, tool, or structured-output changes as blocked. That
  posture matches issue #7 findings 3 and 4.
- Matt Pocock `writing-for-agents` (`mattpocock/skills` `c55ee46`): the local
  copy is byte-identical to upstream (`diff -ru` exit 0); last change to the
  skill was 2026-08-19. No update to apply.

## Round 2: `work-to-skill` against the collected sources

Target: `skills/work-to-skill/SKILL.md`
(`7a4361fb753f3951b76886bbe839840b9c933ce66f6688833d6de8cf943548bf`) and
`references/validation.md`
(`3d9538774bc7a30d872c57457655fd1ffcf20f2271792653250dd83b7276eb38`), both
unchanged since v0.1.1. Sources supplied: prompt-audit.md, the two OpenAI
references, writing-for-agents `SKILL.md` and `SKILL-MECHANICS.md`, and
anthropics `skill-creator/SKILL.md`. The round 1 issue text was supplied with
an instruction not to repeat it.

Result: no change.

- Astra: zero findings, `no_change_recommended: true`.
- Fable: `no_change_recommended: false`, one finding at confidence 0.4, typed
  as an untested behavioral hypothesis: validation.md section A opens with an
  unconditional imperative (line 27) and the text does not settle whether an
  independent fresh-context authoring rerun is required for every generated
  skill or only when the authoring process itself is being assessed. It is
  recorded here and not filed. The discriminator is evidence type, not the
  confidence number: every round 1 finding is a text contradiction, while an
  untested behavioral hypothesis is a flag, not an edit.
- Both reviewers judged the target already aligned on the prompt-audit
  anti-patterns they were asked to check: no pressure language, no step
  choreography for judgment work, no prohibition runs, evaluator vocabulary
  confined to the evaluation the reader builds, trigger text separated from
  behavioral text, and the narrowest-safe-change-set posture of the OpenAI
  upgrade guide. Fable alone also recorded the absence of numeric caps;
  Astra alone matched the target's report-what-was-not-run rule
  (validation.md line 64) to the OpenAI prompting guide.

## Limits

Text review only. Neither round observed a host selecting or executing the
skill, so nothing here is evidence of discovery, task behavior, or
professional correctness. The Codex model identity rests on the request flag.
