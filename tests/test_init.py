from assara.cli import main


def test_init_creates_a_complete_library(tmp_path, capsys):
    root = tmp_path / "lib"
    assert main(["init", str(root)]) == 0
    for rel in (
        "assara.toml",
        "CLAUDE.md",
        "catalog.md",
        "queue.md",
        "journal.md",
        "lessons.md",
        ".gitignore",
        "templates/note.md",
        "templates/synthesis.md",
        "templates/project-readme.md",
        "templates/short-note.md",
        "templates/index.md",
        ".claude/skills/distill/SKILL.md",
        ".claude/skills/synthesize/SKILL.md",
        ".claude/skills/add-source/SKILL.md",
        ".claude/skills/tutor/SKILL.md",
    ):
        assert (root / rel).is_file(), rel
    assert main(["--library", str(root), "status"]) == 0


def test_init_never_overwrites_user_files(tmp_path):
    root = tmp_path / "lib"
    main(["init", str(root)])
    (root / "CLAUDE.md").write_text("mine", encoding="utf-8")
    (root / ".claude/skills/distill/SKILL.md").write_text("edited", encoding="utf-8")
    main(["init", str(root)])
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == "mine"
    assert (root / ".claude/skills/distill/SKILL.md").read_text(encoding="utf-8") == "edited"
    main(["init", str(root), "--force-skills"])
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == "mine"
    assert (root / ".claude/skills/distill/SKILL.md").read_text(encoding="utf-8") != "edited"
