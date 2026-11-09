"""PDF extraction, scanned PDF detection and the pdftotext rebuild, on tiny PDFs built in the test."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

pymupdf = pytest.importorskip("pymupdf")

from assara import cli  # noqa: E402
from assara import pdf as pdfmod  # noqa: E402


@pytest.fixture(autouse=True)
def only_existing_commands(monkeypatch):
    """Other command modules may not be written yet: load only those that exist."""
    present = tuple(
        n for n in cli.COMMAND_MODULES if importlib.util.find_spec(f"assara.commands.{n}") is not None
    )
    monkeypatch.setattr(cli, "COMMAND_MODULES", present)


def make_library(root: Path, min_words: int = 100, max_words: int = 300) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "assara.toml").write_text(
        f"[units]\nmin_words = {min_words}\nmax_words = {max_words}\n", encoding="utf-8"
    )
    (root / "sources").mkdir(exist_ok=True)
    return root


def make_pdf(path: Path, pages: list[str], toc: list[list] | None = None) -> Path:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(40, 40, 560, 800), text, fontsize=7)
    if toc:
        doc.set_toc(toc)
    doc.save(str(path))
    doc.close()
    return path


def prose(n: int, word: str = "lorem") -> str:
    return " ".join(f"{word}{i % 7}" for i in range(n))


def pages_of(count: int, n_words: int, word: str = "lorem") -> list[str]:
    """Distinct pages (identical pages would look like a repeated watermark)."""
    return [f"{prose(n_words - 1, word)} page{i}" for i in range(count)]


def test_chapter_starts_picks_shallowest_level_with_two_entries():
    toc = [[1, "Book", 1], [2, "One", 1], [2, "Two", 3], [3, "Detail", 4], [2, "Three", 5]]
    starts, titles = pdfmod.chapter_starts(toc)
    assert starts == {1, 3, 5}
    assert titles[3] == "Two" and titles[4] == "Detail"


def test_check_text_layer():
    assert not pdfmod.check_text_layer([prose(200)] * 4).scanned
    empty = pdfmod.check_text_layer(["", "", ""])
    assert empty.scanned and not empty.watermark
    marked = pdfmod.check_text_layer(["Downloaded from example.org"] * 5)
    assert marked.scanned and marked.watermark
    # A running header on every page of a real book is not a watermark.
    book = pdfmod.check_text_layer([f"My Book\n{prose(150)}"] * 5)
    assert not book.scanned


def test_add_pdf_with_bookmarks(tmp_path, capsys):
    lib = make_library(tmp_path / "lib")
    pages = pages_of(6, 80) + pages_of(2, 80, "ref")
    toc = [[1, "Chapter 1", 1], [1, "Chapter 2", 4], [1, "References", 7]]
    pdf = make_pdf(tmp_path / "book.pdf", pages, toc)
    assert cli.main(["--library", str(lib), "add", "BOOK1", str(pdf), "--title", "Book, Author, 2020"]) == 0
    d = lib / "sources" / "BOOK1"
    raw = (d / "raw" / "pages.md").read_text()
    assert "[p.1]" in raw and "[p.8]" in raw
    assert (d / "original" / "book.pdf").exists()
    units = sorted(p.name for p in (d / "units").iterdir())
    assert units == ["u01.md", "u02.md", "u03.md"]
    u2 = (d / "units" / "u02.md").read_text()
    assert u2.startswith("# BOOK1 u02: Chapter 2") and "[p.4]" in u2 and "Cite `BOOK1 u02 [p.N]`" in u2
    index = (d / "INDEX.md").read_text()
    assert "| Unit | Content | PDF pages | Words | Text | Note |" in index
    assert "| u01 | Chapter 1 | 1-3 |" in index
    assert "(pending)" in index
    out = capsys.readouterr().out
    assert "3 unit(s)" in out and "WARNING" not in out and "CHECK" not in out


def test_rerun_keeps_notes(tmp_path):
    lib = make_library(tmp_path / "lib")
    pdf = make_pdf(tmp_path / "book.pdf", pages_of(6, 80), [[1, "A", 1], [1, "B", 4]])
    cli.main(["--library", str(lib), "add", "BOOK1", str(pdf)])
    note = lib / "sources" / "BOOK1" / "notes" / "u01.md"
    note.write_text("my note")
    cli.main(["--library", str(lib), "extract", "BOOK1", str(pdf)])
    assert note.read_text() == "my note"
    assert "`notes/u01.md` (done)" in (lib / "sources" / "BOOK1" / "INDEX.md").read_text()


def test_references_spill_is_reported(tmp_path, capsys):
    lib = make_library(tmp_path / "lib", min_words=100, max_words=250)
    # Chapter 2 runs 5 pages of 80 words: max_words pushes its end into the References unit.
    pages = pages_of(7, 80) + [prose(30, "ref")]
    toc = [[1, "Chapter 1", 1], [1, "Chapter 2", 3], [1, "References", 8]]
    pdf = make_pdf(tmp_path / "book.pdf", pages, toc)
    cli.main(["--library", str(lib), "add", "BOOK1", str(pdf)])
    out = capsys.readouterr().out
    assert "CHECK u03: labelled 'References'" in out
    index = (lib / "sources" / "BOOK1" / "INDEX.md").read_text()
    assert "end of Chapter 2; References" in index


@pytest.mark.parametrize("watermark,flag", [(False, "--skip-text"), (True, "--force-ocr")])
def test_scanned_pdf_prints_ocr_command(tmp_path, capsys, watermark, flag):
    lib = make_library(tmp_path / "lib")
    text = "Scanned by Example Library" if watermark else ""
    pdf = make_pdf(tmp_path / "scan.pdf", [text] * 4)
    cli.main(["--library", str(lib), "add", "SCAN", str(pdf)])
    out = capsys.readouterr().out
    assert "looks scanned" in out and "ocrmypdf" in out and flag in out
    assert "SCAN-ocr.pdf" in out
    assert not (lib / "sources" / "SCAN" / "raw" / "SCAN-ocr.pdf").exists()  # never run for us


def test_unsupported_type(tmp_path):
    lib = make_library(tmp_path / "lib")
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(SystemExit):
        cli.main(["--library", str(lib), "add", "TXT1", str(f)])


def test_clean_rtl_normalises_presentation_forms():
    # U+FEDF U+FED0 U+FEB0: Arabic presentation forms, plus a right-to-left mark and a form feed.
    assert pdfmod.clean_rtl("‏ﻟﻐﺰ\f  ") == "لغز"


def test_read_unit_ranges(tmp_path):
    index = tmp_path / "INDEX.md"
    index.write_text(
        "# X\n\n| Unit | Content | PDF pages | Words | Text | Note |\n|---|---|---|---|---|---|\n"
        "| u01 | A | 1-3 | 10 | t | n |\n| u02 | B | 4-9 | 10 | t | n |\n"
    )
    assert pdfmod.read_unit_ranges(index) == [("u01", 1, 3), ("u02", 4, 9)]


def test_rebuild_pdftotext_keeps_ranges_and_notes(tmp_path, capsys, monkeypatch):
    lib = make_library(tmp_path / "lib")
    pdf = make_pdf(tmp_path / "book.pdf", pages_of(6, 80), [[1, "A", 1], [1, "B", 4]])
    cli.main(["--library", str(lib), "add", "AR1", str(pdf)])
    d = lib / "sources" / "AR1"
    (d / "notes" / "u01.md").write_text("keep me")
    if not shutil.which("pdftotext"):
        monkeypatch.setattr(pdfmod.shutil, "which", lambda _n: "/usr/bin/pdftotext")
    monkeypatch.setattr(pdfmod, "pdftotext_page", lambda f, p, layout=True: f"‏word{p} ﻟﻐﺰ\f")
    assert cli.main(["--library", str(lib), "rebuild-pdftotext", "AR1", str(pdf)]) == 0
    u2 = (d / "units" / "u02.md").read_text()
    assert u2.startswith("# AR1 u02: pages 4 to 6") and "[p.4]\nword4 لغز" in u2
    assert "‏" not in (d / "raw" / "pages.md").read_text()
    assert (d / "notes" / "u01.md").read_text() == "keep me"
    index = (d / "INDEX.md").read_text()
    assert "| u02 | B | 4-6 | 6 |" in index
    assert "pages 4-6, 6 words" in capsys.readouterr().out


@pytest.mark.skipif(not shutil.which("pdftotext"), reason="poppler pdftotext not installed")
def test_rebuild_with_real_pdftotext(tmp_path):
    lib = make_library(tmp_path / "lib")
    pdf = make_pdf(tmp_path / "book.pdf", pages_of(3, 80))
    cli.main(["--library", str(lib), "add", "PT1", str(pdf)])
    cli.main(["--library", str(lib), "rebuild-pdftotext", "PT1", str(pdf)])
    assert "lorem0" in (lib / "sources" / "PT1" / "units" / "u01.md").read_text()


def test_control_characters_are_cleaned_from_pdf_text():
    starts, titles = pdfmod.chapter_starts([[1, "One\x1b]0;x\x07", 1], [1, "Two", 3]])
    assert titles[1] == "One ]0;x"
    assert pdfmod.clean_rtl("alpha\x1b[2Jbeta\x0cgamma") == "alpha [2Jbetagamma"
