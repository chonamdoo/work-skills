class WorkToSkill < Formula
  desc "Turn professional knowledge and workflows into reusable agent skills"
  homepage "https://github.com/chonamdoo/work-skills"
  url "https://github.com/chonamdoo/work-skills/releases/download/v0.1.0/work-to-skill-v0.1.0.tar.gz"
  sha256 "3fa3d4f77565863fe2e4ee047eb5da833c2e8b6504fa21209df99ee2f85b374f"

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
