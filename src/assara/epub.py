"""EPUB extraction: one block per spine chapter, grouped into units of min_words to max_words words.

An EPUB has no reliable page numbers. Paragraphs are numbered `[§N]` across each unit, so a passage is
cited `CODE uNN §N`, N being the `[§N]` marker numbered through the unit (the `## chNN: title`
headings only help to find a passage).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

from .library import AssaraError, clean_text, group_blocks, install_hint, thousands, words, write_index

EPUB_COLUMNS = ["Unit", "Content", "Chapters", "Words", "Text"]
PARAGRAPH_TAGS = ["p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre"]


@dataclass
class EpubResult:
    units: int
    words: int
    chapters: int


def _libs():
    try:
        import ebooklib
        from bs4 import BeautifulSoup
        from ebooklib import epub
    except ImportError as exc:  # pragma: no cover
        raise AssaraError(
            "Reading an EPUB needs ebooklib and BeautifulSoup: " + install_hint("epub")
        ) from exc
    return ebooklib, epub, BeautifulSoup


def _parser() -> str:
    try:
        import lxml  # noqa: F401
    except ImportError:
        return "html.parser"
    return "lxml"


def html_paragraphs(html: bytes | str, fallback_title: str) -> tuple[str, list[str]]:
    """Return (title, paragraphs) of one XHTML chapter. Nested tags are not counted twice."""
    _ebooklib, _epub, BeautifulSoup = _libs()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # XMLParsedAsHTMLWarning when lxml is not installed
        soup = BeautifulSoup(html, _parser())
    head = soup.find(["h1", "h2", "h3"]) or soup.find("title")
    title = clean_text(head.get_text(" ", strip=True)).strip() if head else ""
    paras = []
    for tag in soup.find_all(PARAGRAPH_TAGS):
        if tag.find_parent(PARAGRAPH_TAGS):
            continue  # a <p> inside a <li> or <blockquote> is already in its parent
        text = " ".join(clean_text(tag.get_text(" ", strip=True)).split())
        if text:
            paras.append(text)
    return (title or fallback_title), paras


def read_chapters(file: Path) -> list[dict]:
    """Chapters in reading (spine) order, without the generated navigation document."""
    ebooklib, epub, _bs = _libs()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            book = epub.read_epub(str(file), options={"ignore_ncx": True})
        except Exception as exc:
            raise AssaraError(f"Cannot open {file} as an EPUB: {exc}") from exc
    items = []
    seen = set()
    for idref, *_ in book.spine:
        item = book.get_item_with_id(idref)
        if item is not None:
            items.append(item)
            seen.add(item.get_id())
    # Documents missing from the spine are kept at the end, as the old readers did.
    items += [i for i in book.get_items_of_type(ebooklib.ITEM_DOCUMENT) if i.get_id() not in seen]
    chapters = []
    for item in items:
        if item.get_type() != ebooklib.ITEM_DOCUMENT or isinstance(item, epub.EpubNav):
            continue
        title, paras = html_paragraphs(item.get_content(), Path(item.get_name()).stem)
        if paras:
            chapters.append({"title": title, "paras": paras, "words": sum(words(p) for p in paras)})
    for n, c in enumerate(chapters, start=1):
        c["ch"] = f"ch{n:02d}"
    return chapters


def extract_epub(file: Path, d: Path, code: str, title: str, min_words: int, max_words: int) -> EpubResult:
    """Write raw/chapters.md, units/uNN.md and INDEX.md for an EPUB. Notes are never touched."""
    chapters = read_chapters(file)
    if not chapters:
        raise AssaraError(f"{file}: no text found in the EPUB (DRM-protected or images only?).")
    (d / "raw" / "chapters.md").write_text(
        f"# {code}: raw text by chapter (EPUB spine order)\n\n"
        + "".join(f"## {c['ch']}: {c['title']}\n\n" + "\n\n".join(c["paras"]) + "\n\n" for c in chapters),
        encoding="utf-8",
    )
    total = sum(c["words"] for c in chapters)

    for old in (d / "units").glob("u[0-9]*.md"):
        old.unlink()
    rows = []
    groups = group_blocks(chapters, min_words, max_words)
    for n, group in enumerate(groups, start=1):
        unit = f"u{n:02d}"
        names = [c["title"] for c in group]
        label = "; ".join(names[:4]) + ("; ..." if len(names) > 4 else "")
        parts, para = [], 0
        for c in group:
            lines = []
            for p in c["paras"]:
                para += 1
                lines.append(f"[§{para}] {p}")
            parts.append(f"## {c['ch']}: {c['title']}\n\n" + "\n\n".join(lines))
        count = sum(c["words"] for c in group)
        (d / "units" / f"{unit}.md").write_text(
            f"# {code} {unit}: {label}\n\n{thousands(count)} words. Cite `{code} {unit} §N` "
            f"(N = the `[§N]` marker, numbered through the unit).\n\n" + "\n\n".join(parts) + "\n",
            encoding="utf-8",
        )
        chs = group[0]["ch"] if len(group) == 1 else f"{group[0]['ch']}-{group[-1]['ch']}"
        rows.append(
            {
                "unit": unit,
                "Unit": unit,
                "Content": label.replace("|", "/"),
                "Chapters": chs,
                "Words": thousands(count),
                "Text": f"`units/{unit}.md`",
            }
        )
    write_index(
        d,
        code,
        title,
        [
            f"Source: `original/{file.name}` ({len(chapters)} chapters, about {thousands(total)} words).",
            f"Citations: `{code} uNN §N` (unit and `[§N]` marker, numbered through the unit). "
            "No page numbers.",
        ],
        EPUB_COLUMNS,
        rows,
    )
    return EpubResult(len(groups), total, len(chapters))
