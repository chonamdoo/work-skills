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

### Install with npx (recommended)

Requires Node.js, npm (which provides `npx`), and Git. The
[skills CLI](https://github.com/vercel-labs/skills) installs directly from this
repository; `work-skills` does not need a separate npm package or Homebrew.

Choose **one** installation scope:

**Project** — run from the project root to make the skill available in that project:

```sh
npx skills@latest add chonamdoo/work-skills --skill work-to-skill
```

**Global** — make the skill available across your projects:

```sh
npx skills@latest add chonamdoo/work-skills --skill work-to-skill -g
```

Select the agents you use, such as Codex and Claude Code, and choose **Symlink**
when prompted. The installer keeps a shared copy and connects supported agents
to it. Agent-specific discovery paths are handled by the installer; not every
agent reads `.agents/skills` directly. Homebrew's manual linking step below is
not part of the npx installation.

Before confirming, inspect existing project, global, and plugin installations,
including any legacy `~/.codex/skills` copy or Homebrew links. Keep one installation
route and scope for this skill per project/agent; do not layer npx over a Homebrew
installation or install the same skill both globally and in a project. Review
any overwrite prompt instead of replacing a customized skill automatically.

These commands fetch the repository's default branch, not a pinned release.
For npx-managed installations, use `npx skills@latest update work-to-skill` and
select the intended scope when prompted. Restart the agent if needed, check its
skill list, and try an explicit `work-to-skill` request. Installation does not
verify automatic selection or task correctness in every host.

### Alternative: Homebrew

This repository also serves as a Homebrew tap. Use its explicit URL because its
name is `work-skills`, not `homebrew-work-skills`:

```sh
brew tap chonamdoo/work-skills https://github.com/chonamdoo/work-skills.git
brew install chonamdoo/work-skills/work-to-skill
```

If Homebrew requests trust, review `Formula/work-to-skill.rb` and trust only this
formula with `brew trust --formula chonamdoo/work-skills/work-to-skill` on versions
that support that command, then retry installation.

Homebrew verifies the pinned release checksum and installs the skill files under
`$(brew --prefix chonamdoo/work-skills/work-to-skill)/share/work-to-skill`.
It does not install an AI CLI, register a skill, or overwrite existing skills.

### Connect to Codex and Claude Code

This manual connection step is only for the Homebrew alternative above.

The documented personal skill directories differ:
[Codex](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)
uses `~/.agents/skills`, while
[Claude Code](https://code.claude.com/docs/en/skills#choose-where-skills-load)
uses `~/.claude/skills`. Both support symlinked skill folders.

First check for an existing `work-to-skill` in your personal, project, and plugin
skill locations, including a legacy `~/.codex/skills` installation. Keep one
installation route per host; this example does not scan or remove those copies.
After Homebrew installation, run this to register the skill for both local hosts.
The shared entry is `~/.agents/skills/work-to-skill`; Claude Code links to that
entry. The actual files remain managed by Homebrew.

```sh
(
  skill_prefix="$(brew --prefix chonamdoo/work-skills/work-to-skill)" || exit 1
  skill_source="$skill_prefix/share/work-to-skill"
  skill_shared="$HOME/.agents/skills/work-to-skill"
  skill_claude="$HOME/.claude/skills/work-to-skill"
  if [ ! -f "$skill_source/SKILL.md" ]; then
    printf 'Skill files not found; finish Homebrew installation first.\n'
    exit 1
  fi
  for skill_target in "$skill_shared" "$skill_claude"; do
    if [ -e "$skill_target" ] || [ -L "$skill_target" ]; then
      if [ ! "$skill_target" -ef "$skill_source" ]; then
        printf 'Stopped; inspect existing skill: %s\n' "$skill_target"
        exit 1
      fi
    fi
  done
  mkdir -p "$(dirname "$skill_shared")" "$(dirname "$skill_claude")" || exit 1
  if [ ! -e "$skill_shared" ]; then
    ln -s "$skill_source" "$skill_shared" || exit 1
  fi
  if [ ! -e "$skill_claude" ]; then
    ln -s "$skill_shared" "$skill_claude" || exit 1
  fi
)
```

This creates links to one package, not two maintained copies. Rerunning it keeps
links that already resolve to the package, including the previous direct
Homebrew links. Any conflicting file, directory, or broken link stops registration
before either skill entry is created; existing entries are left untouched.
Restart the host if the skill does not appear;
check its skill list and try an explicit `work-to-skill` request. Automatic
selection and task correctness still need checking in your actual environment.
These are local-host instructions, not cloud/Cowork installation instructions.
For another local agent, check its documented discovery path. If it reads
`~/.agents/skills`, the shared entry is enough. Otherwise, link only its supported
skill path to that entry after checking for existing installations; there is no
universal discovery path for every agent.

To update the Homebrew package, run `brew update` and
`brew upgrade chonamdoo/work-skills/work-to-skill`. Links use Homebrew's stable
package path, so they follow an upgrade. Do not edit the Homebrew-managed files;
keep custom skill drafts in your own workspace. Uninstalling the formula leaves
any personal links you created in place; inspect and remove only those links
separately if you no longer want them.

### Manual installation

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
See [current validation evidence](docs/validation-v0.1.1.md) and the
[initial validation record](docs/validation-v0.1.0.md) for tested scope and limitations.
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

After a new release is published, update the URL and SHA-256 in
`Formula/work-to-skill.rb` through a reviewed PR. The formula intentionally tracks
an already published asset; tagging alone does not update Homebrew users.
Homebrew CI installs that asset and runs the formula's package test in a disposable
runner. These checks do not certify AI-host discovery or model behavior.

Updating work-to-skill does not rewrite previously generated skills.
Recheck affected outputs separately when a consequential creator defect is fixed.

## Sources

The design draws on [OpenAI's skill guidance](https://learn.chatgpt.com/docs/build-skills),
[Anthropic's skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator),
and [Matt Pocock's writing-for-agents](https://github.com/mattpocock/skills/tree/main/skills/productivity/writing-for-agents).
These are background sources, not runtime dependencies or bundled copies.
