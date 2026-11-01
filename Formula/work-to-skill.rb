class WorkToSkill < Formula
  desc "Turn professional knowledge and workflows into reusable agent skills"
  homepage "https://github.com/chonamdoo/work-skills"
  url "https://github.com/chonamdoo/work-skills/releases/download/v0.1.2/work-to-skill-v0.1.2.tar.gz"
  sha256 "f0d20c88b117abb03018a1dc99f824c446de96aa05c31c1046a8ddc6e16fb249"

  def install
    pkgshare.install "SKILL.md", "references"
  end

  def caveats
    <<~EOS
      Skill files are installed at:
        #{opt_pkgshare}

      Homebrew does not register the skill with an AI host or change existing skills.
      Follow the README's optional Codex and Claude Code linking instructions:
        https://github.com/chonamdoo/work-skills#connect-to-codex-and-claude-code
    EOS
  end

  test do
    assert_path_exists pkgshare/"SKILL.md"
    assert_path_exists pkgshare/"references/validation.md"
    assert_match "name: work-to-skill\n", (pkgshare/"SKILL.md").read
    assert_match "(references/validation.md)", (pkgshare/"SKILL.md").read
  end
end
