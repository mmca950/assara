"""EPUB extraction on a tiny EPUB built in the test."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

epub = pytest.importorskip("ebooklib.epub")
pytest.importorskip("bs4")

from assara import cli  # noqa: E402
from assara.epub import html_paragraphs  # noqa: E402


@pytest.fixture(autouse=True)
def only_existing_commands(monkeypatch):
    present = tuple(
        n for n in cli.COMMAND_MODULES if importlib.util.find_spec(f"assara.commands.{n}") is not None
    )
    monkeypatch.setattr(cli, "COMMAND_MODULES", present)


def make_library(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "assara.toml").write_text("[units]\nmin_words = 50\nmax_words = 120\n", encoding="utf-8")
    (root / "sources").mkdir()
    return root


def para(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


def make_epub(path: Path, chapters: list[tuple[str, list[str]]]) -> Path:
    book = epub.EpubBook()
    book.set_identifier("test-book")
    book.set_title("Test Book")
    book.set_language("en")
    items = []
    # Written in reverse so that file order differs from spine order.
    for n, (title, paras) in reversed(list(enumerate(chapters, start=1))):
        c = epub.EpubHtml(title=title, file_name=f"c{n}.xhtml", lang="en")
        c.content = f"<h1>{title}</h1>" + "".join(f"<p>{p}</p>" for p in paras)
        book.add_item(c)
        items.insert(0, c)
    book.toc = items
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]
    epub.write_epub(str(path), book)
    return path


def test_html_paragraphs_does_not_double_nested():
    title, paras = html_paragraphs("<html><body><h2>T</h2><li><p>a b</p></li><p>c</p></body></html>", "x")
    assert title == "T"
    assert paras == ["T", "a b", "c"]


def test_add_epub(tmp_path, capsys):
    lib = make_library(tmp_path / "lib")
    chapters = [
        ("Intro", [para(20)]),
        ("One", [para(30), para(30)]),
        ("Two", [para(40)]),
        ("Three", [para(60)]),
    ]
    f = make_epub(tmp_path / "book.epub", chapters)
    assert cli.main(["--library", str(lib), "add", "EBK1", str(f), "--title", "Test Book, A. Author"]) == 0
    d = lib / "sources" / "EBK1"
    raw = (d / "raw" / "chapters.md").read_text()
    assert raw.index("ch01: Intro") < raw.index("ch02: One") < raw.index("ch04: Three")
    units = sorted(p.name for p in (d / "units").iterdir())
    assert len(units) >= 2
    u1 = (d / "units" / "u01.md").read_text()
    assert "## ch01: Intro" in u1 and "[§1] Intro" in u1 and "Cite `EBK1 u01 §N`" in u1
    index = (d / "INDEX.md").read_text()
    assert "| Unit | Content | Chapters | Words | Text | Note |" in index
    assert (d / "original" / "book.epub").exists()
    assert "chapters" in capsys.readouterr().out


def test_html_paragraphs_drops_control_characters():
    title, paras = html_paragraphs("<h1>Ti\x1btle</h1><p>alpha\x07beta</p>", "fallback")
    assert title == "Ti tle"
    assert paras == ["Ti tle", "alpha beta"]
