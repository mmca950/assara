"""Rebuilding units must not silently move the passages that existing notes cite."""

from __future__ import annotations

import pytest

pytest.importorskip("ebooklib.epub")
pytest.importorskip("bs4")

from assara.cli import main  # noqa: E402
from assara.library import AssaraError, NotedUnitsGuard, unit_body  # noqa: E402

from .test_epub import make_epub, make_library, para  # noqa: E402

CHAPTERS = [(f"Chapter {i}", [para(30), para(30)]) for i in range(1, 7)]


def _set_sizes(lib, lo, hi):
    (lib / "assara.toml").write_text(f"[units]\nmin_words = {lo}\nmax_words = {hi}\n", encoding="utf-8")


def test_epub_citation_lines(tmp_path):
    lib = make_library(tmp_path / "lib")
    book = make_epub(tmp_path / "b.epub", CHAPTERS)
    main(["--library", str(lib), "add", "EBK1", str(book)])
    d = lib / "sources" / "EBK1"
    index = (d / "INDEX.md").read_text(encoding="utf-8")
    unit = (d / "units" / "u01.md").read_text(encoding="utf-8")
    assert "`EBK1 uNN §N` (unit and `[§N]` marker, numbered through the unit)" in index
    assert "Cite `EBK1 u01 §N` (N = the `[§N]` marker, numbered through the unit)." in unit
    assert "section title" not in index + unit


def test_rebuild_refused_when_noted_unit_changes(tmp_path):
    lib = make_library(tmp_path / "lib")
    book = make_epub(tmp_path / "b.epub", CHAPTERS)
    main(["--library", str(lib), "add", "EBK1", str(book)])
    d = lib / "sources" / "EBK1"
    (d / "notes" / "u02.md").write_text("# note citing EBK1 u02 §3", encoding="utf-8")
    before = (d / "units" / "u02.md").read_text(encoding="utf-8")
    index_before = (d / "INDEX.md").read_text(encoding="utf-8")

    _set_sizes(lib, 150, 300)  # other unit sizes: u02 would cover other chapters
    with pytest.raises(AssaraError, match="u02"):
        main(["--library", str(lib), "add", "EBK1", str(book)])
    assert (d / "units" / "u02.md").read_text(encoding="utf-8") == before
    assert (d / "INDEX.md").read_text(encoding="utf-8") == index_before
    assert not (d / ".rebuild-backup").exists()

    assert main(["--library", str(lib), "add", "EBK1", str(book), "--force"]) == 0
    assert (d / "units" / "u02.md").read_text(encoding="utf-8") != before
    assert (d / "notes" / "u02.md").exists()


def test_same_rebuild_is_allowed(tmp_path):
    lib = make_library(tmp_path / "lib")
    book = make_epub(tmp_path / "b.epub", CHAPTERS)
    main(["--library", str(lib), "add", "EBK1", str(book)])
    d = lib / "sources" / "EBK1"
    (d / "notes" / "u01.md").write_text("# note", encoding="utf-8")
    assert main(["--library", str(lib), "add", "EBK1", str(book), "--title", "New title"]) == 0


def test_guard_restores_on_error(tmp_path):
    d = tmp_path / "SRC1"
    for sub in ("units", "notes", "raw"):
        (d / sub).mkdir(parents=True)
    (d / "units" / "u01.md").write_text("# h\n\n[p.1]\ntext", encoding="utf-8")
    (d / "notes" / "u01.md").write_text("# note", encoding="utf-8")
    with pytest.raises(RuntimeError):
        with NotedUnitsGuard(d):
            (d / "units" / "u01.md").unlink()
            raise RuntimeError("extraction failed")
    assert (d / "units" / "u01.md").exists()


def test_unit_body_ignores_header():
    a = "# X u01: old label\n\n10 words. Cite `X u01 §N`.\n\n## ch01: One\n\n[§1] text"
    b = "# X u01: new label\n\n10 words. Cite `X u01 §N` (new wording).\n\n## ch01: One\n\n[§1] text"
    assert unit_body(a) == unit_body(b)
