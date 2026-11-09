from pathlib import Path

import pytest

from assara.cli import main
from assara.commands import regroup as rg
from assara.config import Config
from assara.library import AssaraError, index_status
from assara.srt import Cue, write_srt


def make_source(tmp_path: Path, lesson_words: list[int], min_words: int = 100, max_words: int = 200):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "assara.toml").write_text(
        f"[units]\nmin_words = {min_words}\nmax_words = {max_words}\n", encoding="utf-8"
    )
    cfg = Config.load(root)
    course = tmp_path / "course"
    course.mkdir()
    for i, n in enumerate(lesson_words, start=1):
        (course / f"{i:02d} Lesson {i}.mp4").write_bytes(b"x")
        write_srt([Cue(0, 5, "word " * n)], course / f"{i:02d} Lesson {i}.srt")
    assert main(["--library", str(root), "transcribe", "CRS1", str(course), "--index-only"]) == 0
    return cfg, course, cfg.sources_dir / "CRS1"


def test_parse_range():
    assert rg.parse_range("ch01-ch03, ch07") == {1, 2, 3, 7}
    with pytest.raises(ValueError):
        rg.parse_range("ch05-ch02")
    with pytest.raises(ValueError):
        rg.parse_range("lesson1")


def test_parse_modules():
    mods, skipped = rg.parse_modules("# comment\n\nm01 | Basics | ch01-ch02\nskip | ch03 | duplicate\n")
    assert [(m.name, m.title, m.numbers) for m in mods] == [("m01", "Basics", [1, 2])]
    assert skipped == {3: "duplicate"}
    with pytest.raises(AssaraError):
        rg.parse_modules("m01 | only two fields")
    with pytest.raises(AssaraError):
        rg.parse_modules("m01 | A | ch01\nm01 | B | ch02\n")


def test_parse_lessons_with_parts_and_pipes():
    text = (
        "| ch01 | Intro \\| part | 00:01:00 | 1,234 | `units/ch01-intro.md` | `notes/ch01.md` (pending) |\n"
        "| ch02a | Long (part 1/2) | 00:00:00 to 00:30:00 | 900 | `units/ch02a-long.md` | x |\n"
    )
    lessons = rg.parse_lessons(text)
    assert [(les.unit, les.number, les.words) for les in lessons] == [("ch01", 1, 1234), ("ch02a", 2, 900)]
    assert lessons[0].title == "Intro \\| part"


def test_auto_modules():
    lessons = [rg.Lesson(f"ch{i:02d}", i, f"L{i}", "", 60, "") for i in range(1, 8)]
    mods = rg.auto_modules(lessons, 100, 200)
    assert sum((m.numbers for m in mods), []) == list(range(1, 8))
    assert all(m.name.startswith("m") for m in mods)


def test_regroup_with_modules_file_and_rerun_after_transcribe(tmp_path):
    cfg, course, d = make_source(tmp_path, [50, 60, 70, 80])
    (d / "raw" / "modules.txt").write_text(
        "m01 | First steps | ch01-ch02\nm02 | Practice | ch03\nskip | ch04 | duplicate\n", encoding="utf-8"
    )
    (d / "notes" / "m01.md").write_text("note", encoding="utf-8")
    assert main(["--library", str(cfg.root), "regroup", "CRS1"]) == 0
    index = (d / "INDEX.md").read_text(encoding="utf-8")
    assert "| Module | Title | Lessons | Words | Note |" in index
    assert "| m01 | First steps | ch01, ch02 | 112 | `notes/m01.md` (done) |" in index
    assert "left out (duplicate)" in index
    assert (d / "raw" / rg.BY_LESSON).exists()
    assert index_status(d) == (1, 2, ["m02"])

    # running regroup twice keeps the per-lesson copy intact
    assert main(["--library", str(cfg.root), "regroup", "CRS1"]) == 0
    assert "| ch01 |" in (d / "raw" / rg.BY_LESSON).read_text(encoding="utf-8")

    # a new lesson arrives, transcribe rewrites the per-lesson index, regroup picks it up
    (course / "05 Lesson 5.mp4").write_bytes(b"x")
    write_srt([Cue(0, 5, "word " * 40)], course / "05 Lesson 5.srt")
    assert main(["--library", str(cfg.root), "transcribe", "CRS1", str(course), "--index-only"]) == 0
    with (d / "raw" / "modules.txt").open("a", encoding="utf-8") as f:
        f.write("m03 | New | ch05\n")
    assert main(["--library", str(cfg.root), "regroup", "CRS1"]) == 0
    index = (d / "INDEX.md").read_text(encoding="utf-8")
    assert "| m03 | New | ch05 | 41 |" in index
    assert (d / "notes" / "m01.md").read_text(encoding="utf-8") == "note"


def test_regroup_without_modules_file_writes_one(tmp_path):
    cfg, course, d = make_source(tmp_path, [60] * 6)
    modules, skipped, generated = rg.regroup(d, "CRS1", cfg.min_words, cfg.max_words)
    assert generated and not skipped
    text = (d / "raw" / "modules.txt").read_text(encoding="utf-8")
    assert "m01 |" in text
    again, _ = rg.parse_modules(text)
    assert [m.numbers for m in again] == [m.numbers for m in modules]


def test_overlapping_modules_rejected(tmp_path):
    cfg, course, d = make_source(tmp_path, [50, 50])
    (d / "raw" / "modules.txt").write_text("m01 | A | ch01-ch02\nm02 | B | ch02\n", encoding="utf-8")
    with pytest.raises(AssaraError):
        rg.regroup(d, "CRS1", cfg.min_words, cfg.max_words)
