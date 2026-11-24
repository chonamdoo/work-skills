# 2026-11-24 NVIDIA SkillEvaluator Audit & `check_skill.py` Improvements

**Scope**: Static, keyless (`--no-llm`, zero paid LLM calls) audit of `skills/work-to-skill` using [`NVIDIA/SkillEvaluator`](https://github.com/NVIDIA/SkillEvaluator) `v1.2.0` (`harness-check` + `tier1 --no-llm`), deterministic improvements to `skills/work-to-skill/scripts/check_skill.py`, and an `I9`-compliant proposal for a future user-authorized candidate rerun on `SKILL.md` and `references/validation.md`.

**Regression Ledger Compliance**: `skills/work-to-skill/SKILL.md` and `skills/work-to-skill/references/validation.md` are **unchanged** in this change set so `I9-reproduced-failure` (`tests/test_depth_evidence.py::test_shipped_instructions_are_the_evaluated_candidate` SHA-256 pins) and `tests/test_package.py` remain strictly intact without unapproved LLM runs.

## 1. Before / After `NVIDIA/SkillEvaluator` (`v1.2.0`) Results

| Check | Baseline (`main`) | After (`check_skill.py` updates) | Notes |
| --- | --- | --- | --- |
| `skillevaluator harness-check skills/work-to-skill` | **6/6 load** (`0 not_loaded`, `0 degraded`, 4 INFO notes) | **6/6 load** (`0 not_loaded`, `0 degraded`, 4 INFO notes) | Claude Code, Codex, Copilot CLI, Hermes, OpenClaw, OpenCode all load |
| `skillevaluator tier1 skills/work-to-skill --no-llm` | **10/11 PASS, 1 FAIL** (`Code Risk Analysis`: Bandit `B506:yaml_load` error; SkillSpector `AST10` medium advisory) | **11/11 PASS, 0 FAIL** (`Code Risk Analysis` PASS, `PII Scan` PASS, `Unicode` PASS, `Security` 2 advisories) | Replaced `yaml.load(header, Loader=yaml_loader())` with `SafeLoader` AST duplicate-key check + `yaml.safe_load(header)` |
| Tier 1 Quality Score | `80.2/100` (Grade B) | `80.2/100` (Grade B) | Unchanged because `SKILL.md` is SHA-pinned under `I9-reproduced-failure` |
| `python3 skills/work-to-skill/scripts/check_skill.py skills/work-to-skill` (`generic` & `anthropic`) | `ok` (exit `0`, 0 warnings) | `ok` (exit `0`, 0 warnings) | Preserves all exit codes (`0`/`1`/`2`/`3`) |
| `pytest -q` (`tests/`) | `100 passed, 665 subtests passed` | `106 passed, 670 subtests passed` | Zero regressions on `regression_ledger.json` |

### Baseline Findings Analyzed

1. **Blocking failure fixed (`Code Risk Analysis`: Bandit `B506` + SkillSpector `AST10`)**: `check_skill.py:443` called `yaml.load(header, Loader=yaml_loader())` with a dynamically constructed `SafeLoader` subclass. Both Bandit and SkillSpector flagged dynamic `yaml.load(...)` as unsafe deserialization. Walking `yaml.SafeLoader(header).get_single_node()` with `check_unique_yaml_nodes(...)` before calling `yaml.safe_load(header)` keeps strict duplicate-key rejection (including nested mappings and YAML merge-key handling) while eliminating every `yaml.load(...)` call.
2. **Non-blocking `SKILL.md` advisories deferred under `I9-reproduced-failure`**:
   - `SCHEMA-LOW` / `HM-DESC-60`: `work-to-skill`'s `"Use when ..."` trigger appears at characters `111–119`, beyond Hermes's ~60-char skill-list preview.
   - `SCHEMA-LOW` / `QUALITY-MEDIUM`: `metadata.author` and `metadata.tags` are absent because `tests/test_package.py:25` currently enforces `set(metadata) == {"name", "description"}`.
   - `QUALITY-LOW` / `SCHEMA-MEDIUM`: Heading/template nudges (`## Instructions`, `## Examples`, `## Limitations`, `## Troubleshooting`, `run_script` table) are static documentation heuristics; `work-to-skill` intentionally avoids forced outlines (`WFW2-no-forced-counts`).

## 2. Deterministic Improvements Added to `scripts/check_skill.py`

Comparing `NVIDIA/SkillEvaluator` (`docs/harness-check.mdx`, `docs/tier1-reference.mdx`, `src/skillevaluator/config/unicode_smuggle_patterns.yaml`, `src/skillevaluator/config/pii_patterns.yaml`) against `scripts/check_skill.py` identified four deterministic static-check gaps that fit directly into the standalone validator without adding dependencies or changing existing exit codes (`0` = valid / advisory warnings only, `1` = format error, `2` = CLI usage error, `3` = unchecked YAML in stdlib fallback):

1. **Safe YAML duplicate-key parsing (`B506`/`AST10` fix)**: Replaced `yaml.load(header, Loader=yaml_loader())` in `parse_fields` with `check_unique_yaml_nodes` over `yaml.SafeLoader(header).get_single_node()` followed by `yaml.safe_load(header)`.
2. **Multi-harness loader compatibility warnings (`check_harness_portability` & `check_fields`)**:
   - Tab characters in YAML frontmatter even when PyYAML is installed (dropped by Codex, Copilot CLI, OpenClaw).
   - Non-string top-level frontmatter keys (e.g., unquoted `true:` / `123:`).
   - Symlinked `SKILL.md` (skipped by Codex, Hermes, OpenClaw) and nested `SKILL.md` manifests inside subdirectories.
   - Description UTF-16 code-unit length `> 1024` (rejected by Copilot CLI).
   - Delivery / context-budget size warnings (`> 15,000` chars for OpenClaw, `> 32,768` bytes per-skill budget, `> 51,200` bytes OpenCode truncation) — strictly advisory per `I9-no-line-failure`.
   - Host-specific placeholder tokens (`$ARGUMENTS`, `${CLAUDE_SKILL_DIR}`) delivered literally by non-Claude harnesses.
   - Non-skill / host-ignored frontmatter fields (`alwaysApply`, `globs`, `disable-model-invocation`).
3. **Unicode smuggling & Trojan Source warnings (`check_unicode_smuggling`)**:
   - Scans readable UTF-8 skill files for Unicode Tag characters (`U+E0000–U+E007F`), bidirectional overrides/isolates (`CVE-2021-42574`: `U+061C`, `U+200E–U+200F`, `U+202A–U+202E`, `U+2066–U+2069`), zero-width characters (`U+034F`, `U+180E`, `U+200B–U+200D`, `U+2060`, non-leading `U+FEFF`), and invisible format/math operators (`U+2061–U+2064`, `U+206A–U+206F`).
4. **Static secret & PII warnings (`check_secrets_and_pii`)**:
   - Scans readable UTF-8 skill files for PEM private keys, AWS Access Key IDs (`AKIA`/`ASIA`), GitHub tokens (`ghp_`/`ghs_`), Slack/Discord webhooks, database credential URLs, JWTs, hardcoded secret assignments, personal macOS/Windows home paths, US SSN patterns, and non-placeholder email addresses, while exempting standard RFC 2606 / synthetic placeholders.

## 3. Proposed `I9`-Compliant Candidate Follow-Up for `SKILL.md` & `references/validation.md`

The following prose-level gaps remain open for a future pre-registered, user-authorized A/B candidate rerun (required by `I9-reproduced-failure` before modifying `SKILL.md` or `references/validation.md`):

1. **Close open `E2c` host-selection evidence gap (`docs/evaluation-2026-11-08-gaps.md`)**:
   - In `references/validation.md` ("A — Can the author produce the right skill?" & "Compare, repair, and report"), explicitly require observed host discovery/activation artifacts (e.g., host event logs, tool-call transcripts showing `Skill` invocation or `SKILL.md` read events) as selection evidence, and state that an agent's self-report alone leaves automatic selection `unverified`.
   - In `SKILL.md` ("Build the smallest useful package"), note placing the primary `"Use when ..."` trigger early in `description` for harnesses with short skill-list previews (e.g., ~60-char previews) and avoiding host-only placeholders (`$ARGUMENTS`, `${CLAUDE_SKILL_DIR}`) in portable skills.
2. **Integrate Tier-2 intra-skill redundancy & inter-skill catalog overlap (`docs/tier2-deduplication.mdx`)**:
   - In `SKILL.md` ("Establish the assignment" / "Build the smallest useful package") and `references/validation.md`, add an authoring/review check for (a) intra-skill duplicated instructions inflating context budget and (b) inter-skill description/scope overlap against sibling skills installed in the same catalog (which share a finite host skill-list budget and compete for routing).
3. **Separate Tier-3 deterministic trajectory checks from LLM-judge scores (`docs/metrics-reference.mdx`)**:
   - In `references/validation.md` ("Define observable acceptance" & "Compare, repair, and report"), distinguish deterministic trajectory checks (security/command safety, observed skill activation/order/script execution, routing & tool efficiency, token/cost telemetry) from stochastic LLM-judge criteria (output accuracy, goal achievement, judged workflow steps), and note small-sample / dataset-sufficiency limits (e.g., single-attempt or `< 10`-case runs are smoke tests rather than statistically sufficient improvement claims, and token/cost overhead must be reported alongside pass rates).
