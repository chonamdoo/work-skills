class WorkToSkill < Formula
  desc "Turn professional knowledge and workflows into reusable agent skills"
  homepage "https://github.com/chonamdoo/work-skills"
  url "https://github.com/chonamdoo/work-skills/releases/download/v0.1.1/work-to-skill-v0.1.1.tar.gz"
  sha256 "6c70b0a029aea8bf324370e101b12a63930ca13651124582d06507ca71cae0c2"

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
