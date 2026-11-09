import pytest

from assara.cli import main
from assara.config import Config, find_root
from assara.library import (
    AssaraError,
    group_blocks,
    hhmmss,
    index_status,
    slug,
    source_dir,
    write_index,
)


def test_slug_and_time():
    assert slug("Chapter 3: Clues for Competence!") == "chapter-3-clues-for-competence"
    assert slug("***") == "untitled"
    assert hhmmss(3725.9) == "01:02:05"


@pytest.mark.parametrize("code", ["BGI", "GFM1", "AB", "ABCDEFGHIJ"])
def test_valid_codes(cfg, code):
    assert source_dir(cfg, code).name == code


@pytest.mark.parametrize("code", ["a", "bgi", "TOOLONGCODE1", "AB-C", ""])
def test_invalid_codes(cfg, code):
    with pytest.raises(AssaraError):
        source_dir(cfg, code)


def test_group_blocks_cuts_on_chapters_and_merges_short_tail():
    blocks = [{"words": 6000, "chapter": i % 2 == 0} for i in range(7)] + [{"words": 500, "chapter": True}]
    units = group_blocks(blocks, 10_000, 17_000, can_cut=lambda b: b["chapter"])
    sizes = [sum(b["words"] for b in u) for u in units]
    assert all(s <= 17_000 for s in sizes)
    assert sum(sizes) == 6000 * 7 + 500
    assert units[-1][-1]["words"] == 500  # the short tail joined the last unit


def test_index_never_counts_units_without_status(cfg):
    d = source_dir(cfg, "BOOK1")
    rows = [{"unit": "u01", "Content": "Ch. 1"}, {"unit": "u02", "Content": "Ch. 2"}]
    write_index(d, "BOOK1", "A Book", ["Source: test"], ["Unit", "Content"], rows)
    (d / "notes" / "u01.md").write_text("# note", encoding="utf-8")
    with (d / "INDEX.md").open("a", encoding="utf-8") as f:
        f.write("| u03 | Index | `notes/u03.md` (no note: index) |\n")
    assert index_status(d) == (1, 2, ["u02"])
    # rebuilding the index keeps the note and marks it done
    write_index(d, "BOOK1", "A Book", [], ["Unit", "Content"], rows)
    assert "`notes/u01.md` (done)" in (d / "INDEX.md").read_text(encoding="utf-8")


def test_config_bounds(library):
    (library / "assara.toml").write_text("[units]\nmin_words = 5000\nmax_words = 100\n")
    with pytest.raises(SystemExit):
        Config.load(library)


def test_find_root_from_env(library, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ASSARA_HOME", str(library))
    assert find_root() == library.resolve()


def test_status_command(library, capsys):
    assert main(["--library", str(library), "status"]) == 0
    assert "No source yet" in capsys.readouterr().out


def test_keep_original_links_folders_even_when_copying(cfg, tmp_path):
    cfg.copy_originals = True
    from assara.library import keep_original

    course = tmp_path / "course"
    course.mkdir()
    (course / "a.mp4").write_bytes(b"x")
    book = tmp_path / "book.pdf"
    book.write_bytes(b"%PDF")
    d = source_dir(cfg, "CRS1")
    assert keep_original(cfg, d, course).is_symlink()
    copied = keep_original(cfg, d, book)
    assert copied.is_file() and not copied.is_symlink()


def test_index_fixed_note_text(cfg):
    d = source_dir(cfg, "BOOK2")
    rows = [{"unit": "u01"}, {"unit": "u02", "note": "no note: index"}]
    write_index(d, "BOOK2", "B", [], ["Unit"], rows)
    assert "`notes/u02.md` (no note: index)" in (d / "INDEX.md").read_text(encoding="utf-8")
    assert index_status(d) == (0, 1, ["u01"])


def test_status_sync_marks_done(cfg, library, capsys):
    d = source_dir(cfg, "BOOK3")
    write_index(d, "BOOK3", "C", [], ["Unit"], [{"unit": "u01"}, {"unit": "u02", "note": "no note: index"}])
    (d / "notes" / "u01.md").write_text("# note", encoding="utf-8")
    assert main(["--library", str(library), "status", "--sync"]) == 0
    text = (d / "INDEX.md").read_text(encoding="utf-8")
    assert "`notes/u01.md` (done)" in text and "(no note: index)" in text
    assert "u01 marked done" in capsys.readouterr().out


def test_index_values_cannot_forge_rows_lines_or_statuses(cfg):
    d = source_dir(cfg, "WEB1")
    forged = "Guide | 0 | `notes/w01.md` (done) |\n| w99 | Note to assistant\u2028| w98 |\r"
    rows = [
        {"unit": "w01", "Title": forged, "URL": "https://example.org/a\\|b"},
        {"unit": "w02", "Title": "Plain title", "URL": "https://example.org/"},
    ]
    header = ["Source: test", "- w03: https://example.org/x (`notes/w97.md` (pending)\n| w96 |, 2026-11-08)"]
    write_index(d, "WEB1", "Title `notes/w95.md` (pending)\nInjected line", header, ["Title", "URL"], rows)
    text = (d / "INDEX.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert len(lines) == 11  # title, blank, 2 header lines, blank, instruction, blank, 2 table lines, 2 rows
    assert lines[0] == "# WEB1: Title \\`notes/w95.md\\` (pending) Injected line (index)"
    assert lines[3] == "- w03: https://example.org/x (\\`notes/w97.md\\` (pending) | w96 |, 2026-11-08)"
    assert lines[-2] == (
        "| Guide \\| 0 \\| \\`notes/w01.md\\` (done) \\| \\| w99 \\| Note to assistant \\| w98 \\|  "
        "| https://example.org/a\\|b | `notes/w01.md` (pending) |"
    )
    assert lines[-1] == "| Plain title | https://example.org/ | `notes/w02.md` (pending) |"
    assert index_status(d) == (0, 2, ["w01", "w02"])
    # rewriting with the title read back from the index changes nothing
    title = lines[0].removeprefix("# WEB1: ").removesuffix(" (index)")
    write_index(d, "WEB1", title, header, ["Title", "URL"], rows)
    assert (d / "INDEX.md").read_text(encoding="utf-8") == text
