# work-skills

Reusable professional skills, independent of agent-flow.

개발자·기획자·세무사 등 전문가의 지식과 일하는 방식을 재사용 가능한 스킬로 정리합니다.
첫 번째 스킬은 **work-to-skill**입니다.

## Available skill

| Skill | Use |
| --- | --- |
| [work-to-skill](skills/work-to-skill/SKILL.md) | Create, evaluate, or narrowly improve skills from professional knowledge, judgment, procedures, examples, and feedback. |

Reference-only knowledge is welcome. Repeated execution history is not required.
Ordinary document or code requests stay ordinary tasks.
Generated skills belong in the user's chosen project or private workspace;
this repository does not automatically collect user outputs.

## Use

Download the skill archive from [Releases](https://github.com/chonamdoo/work-skills/releases),
check its checksum against SHA256SUMS, and extract it.
The archive contains a work-to-skill directory with instructions and references.

Install that directory using your AI host's documented skill mechanism, or
explicitly give the complete package to an agent that can read its files.
Choose one installation route per host. Check existing copies before installing;
do not assume every host discovers the same shared directory.

Example request:

> Use work-to-skill to turn our review guidelines and examples into a reusable
> skill. Preserve exceptions and uncertain claims. Save the draft in the project
> location I specify; do not install or publish it.

Files use the [Agent Skills format](https://agentskills.io/specification).
Shared instructions do not guarantee identical outputs, automatic discovery,
tools, or approval behavior across hosts.
See [validation evidence](docs/validation-v0.1.0.md) for tested scope and limitations.
There is no mandatory creator, agent-flow, CLI, or model dependency at runtime.

## Maintain and release

Install development dependencies with `python -m pip install -r requirements-dev.txt`.
Run `python -m unittest discover -s tests -v` and `git diff --check`.
CI additionally checks committed whitespace against Git's empty tree, so a
clean checkout does not skip that check.
These are package checks, not professional-accuracy certification.
[Behavioral inputs](tests/behavior) are separate from installed skills.

Use a topic branch and reviewed PR. After checks and behavioral review, merge it,
then push a version tag such as `v0.1.0` at the reviewed main commit.
The Release workflow checks the tagged code and publishes a skill-only archive
and SHA256SUMS to GitHub Releases. It does not publish to npm.
Do not move existing release tags.

Updating work-to-skill does not rewrite previously generated skills.
Recheck affected outputs separately when a consequential creator defect is fixed.

## Sources

The design draws on [OpenAI's skill guidance](https://learn.chatgpt.com/docs/build-skills),
[Anthropic's skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator),
and [Matt Pocock's writing-for-agents](https://github.com/mattpocock/skills/tree/main/skills/productivity/writing-for-agents).
These are background sources, not runtime dependencies or bundled copies.
