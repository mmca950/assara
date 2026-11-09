"""PDF extraction: pages with `[p.N]` markers, units cut on bookmarks, scanned PDF detection.

Page numbers are always the page numbers of the PDF file (1 = first page of the file), never the
numbers printed in the book. Citations: `CODE uNN [p.N]`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .library import AssaraError, clean_text, group_blocks, install_hint, thousands, words, write_index

PDF_COLUMNS = ["Unit", "Content", "PDF pages", "Words", "Text"]

# Under this many words per page on average, the PDF has no real text layer (scanned).
SCANNED_WORDS_PER_PAGE = 10
# A short line found on at least this share of pages is a watermark or a running header, not content.
REPEATED_LINE_SHARE = 0.6
REPEATED_LINE_MAX_WORDS = 12

# Bidirectional control characters that pdftotext leaves around Arabic or Hebrew text.
BIDI_CONTROLS = dict.fromkeys(map(ord, "‪‫‬‭‮‎‏⁦⁧⁨⁩"))

# Back-matter sections: a unit labelled with one of these usually gets no full note.
BACK_MATTER_RE = re.compile(
    r"\b(references?|bibliograph\w*|works cited|sources|index|endnotes|notes|r[ée]f[ée]rences|"
    r"bibliographie)\b",
    re.I,
)

# Tesseract language codes for ocrmypdf, from the two-letter `language` of the configuration.
OCR_LANGUAGES = {
    "en": "eng",
    "fr": "fra",
    "ar": "ara",
    "es": "spa",
    "de": "deu",
    "it": "ita",
    "pt": "por",
    "nl": "nld",
    "ru": "rus",
    "tr": "tur",
    "zh": "chi_sim",
    "ja": "jpn",
}


def _pymupdf():
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover
        raise AssaraError("Reading a PDF needs PyMuPDF: " + install_hint("pdf")) from exc
    return pymupdf


@dataclass
class Scan:
    """Result of the text layer check."""

    scanned: bool
    watermark: bool
    words: int
    pages: int
    repeated_lines: list[str] = field(default_factory=list)


@dataclass
class PdfResult:
    units: int
    words: int
    pages: int
    scan: Scan
    warnings: list[str]


def chapter_starts(toc: list[list]) -> tuple[set[int], dict[int, str]]:
    """Return (pages where a chapter starts, page -> bookmark titles) from a PyMuPDF outline.

    Chapters are the shallowest bookmark level that has at least two entries (a single level-1
    bookmark is often just the book title). Titles of that level and the next one label the units.
    """
    entries = [(int(lvl), clean_text(str(t)).strip(), int(p)) for lvl, t, p, *_ in toc if int(p) >= 1]
    if not entries:
        return set(), {}
    counts = Counter(lvl for lvl, _t, _p in entries)
    level = min((lvl for lvl, n in counts.items() if n >= 2), default=min(counts))
    starts = {p for lvl, _t, p in entries if lvl == level}
    titles: dict[int, str] = {}
    for lvl, t, p in entries:
        if level <= lvl <= level + 1 and t:
            titles[p] = f"{titles[p]} / {t}" if p in titles else t
    return starts, titles


def check_text_layer(texts: list[str]) -> Scan:
    """Detect a scanned PDF: little or no text, or only a repeated line (watermark) on each page."""
    n = len(texts)
    lines_per_page = [{ln.strip() for ln in t.splitlines() if ln.strip()} for t in texts]
    repeated: list[str] = []
    if n >= 3:
        counts = Counter(ln for lines in lines_per_page for ln in lines)
        repeated = [
            ln
            for ln, c in counts.items()
            if c >= REPEATED_LINE_SHARE * n and words(ln) <= REPEATED_LINE_MAX_WORDS
        ]
    total = sum(words(t) for t in texts)
    content = sum(words(ln) for lines in lines_per_page for ln in lines if ln not in repeated)
    scanned = n > 0 and content < SCANNED_WORDS_PER_PAGE * n
    watermark = scanned and bool(repeated) and total > content
    return Scan(scanned, watermark, total, n, repeated)


def ocr_command(file: Path, out: Path, language: str = "") -> str:
    """The ocrmypdf command to run on a scanned PDF (printed, never run by assara)."""
    lang = OCR_LANGUAGES.get(language.lower(), language) if language else "eng"
    return f"nice -n 19 ocrmypdf -l {lang} --jobs 2 --skip-text '{file}' '{out}'"


def ocr_advice(scan: Scan, file: Path, out: Path, language: str, code: str) -> str:
    cmd = ocr_command(file, out, language)
    if scan.watermark:
        cmd = cmd.replace("--skip-text", "--force-ocr")
        why = (
            f"the only text is a line repeated on most pages (watermark or stamp: "
            f"'{scan.repeated_lines[0][:60]}'), so --skip-text would skip every page"
        )
    else:
        why = f"{thousands(scan.words)} words for {scan.pages} pages"
    return (
        f"WARNING: this PDF looks scanned ({why}). Run OCR first (not run for you):\n"
        f"  {cmd}\n"
        f"then: assara add {code} '{out}'"
    )


def _label(group: list[dict], titles: dict[int, str], prev_title: str | None) -> str:
    chapters = [titles[b["page"]] for b in group if b["page"] in titles]
    first, last = group[0]["page"], group[-1]["page"]
    if not chapters:
        return f"pages {first} to {last}" + (f" (continues {prev_title})" if prev_title else "")
    label = "; ".join(chapters[:4]) + ("; ..." if len(chapters) > 4 else "")
    if group[0]["page"] not in titles and prev_title:
        label = f"end of {prev_title}; {label}"
    return label


def spill_warnings(code: str, groups: list[list[dict]], titles: dict[int, str]) -> list[str]:
    """Flag back-matter units (references, bibliography, index) that start with running text.

    A unit cannot exceed max_words, so the end of the last chapter can be pushed into the unit that
    holds the references, and the end of the references into the index unit.
    """
    out = []
    for n, group in enumerate(groups, start=1):
        pages = [b["page"] for b in group]
        own = [(p, titles[p]) for p in pages if p in titles]
        if not own or pages[0] in titles:
            continue
        first_page, first_title = own[0]
        if BACK_MATTER_RE.search(first_title):
            out.append(
                f"CHECK u{n:02d}: labelled '{first_title}' but pages {pages[0]} to {first_page - 1} come "
                f"before it (end of the previous section, cut by max_words). Read its first pages before "
                f"marking it 'no note', and give them to the note of u{n - 1:02d}."
            )
    return out


def extract_pdf(
    file: Path, d: Path, code: str, title: str, min_words: int, max_words: int, language: str = ""
) -> PdfResult:
    """Write raw/pages.md, units/uNN.md and INDEX.md for a PDF. Notes are never touched."""
    pymupdf = _pymupdf()
    try:
        doc = pymupdf.open(str(file))
    except Exception as exc:
        raise AssaraError(f"Cannot open {file} as a PDF: {exc}") from exc
    with doc:
        starts, titles = chapter_starts(doc.get_toc())
        texts = [clean_text(page.get_text()).strip() for page in doc]

    pages = [{"page": i, "text": t, "words": words(t)} for i, t in enumerate(texts, start=1)]
    (d / "raw" / "pages.md").write_text(
        f"# {code}: raw text (PyMuPDF)\n\n" + "".join(f"[p.{p['page']}]\n{p['text']}\n\n" for p in pages),
        encoding="utf-8",
    )
    scan = check_text_layer(texts)
    total = scan.words
    warnings = []
    if scan.scanned:
        warnings.append(ocr_advice(scan, file, d / "raw" / f"{code}-ocr.pdf", language, code))

    for old in (d / "units").glob("u[0-9]*.md"):
        old.unlink()
    groups = group_blocks(pages, min_words, max_words, can_cut=lambda b: b["page"] in starts) if pages else []
    rows = []
    prev_title: str | None = None
    for n, group in enumerate(groups, start=1):
        unit = f"u{n:02d}"
        first, last = group[0]["page"], group[-1]["page"]
        label = _label(group, titles, prev_title)
        count = sum(b["words"] for b in group)
        body = "\n\n".join(f"[p.{b['page']}]\n{b['text']}" for b in group)
        (d / "units" / f"{unit}.md").write_text(
            f"# {code} {unit}: {label}\n\nPages {first} to {last} of the PDF, {thousands(count)} words. "
            f"Cite `{code} {unit} [p.N]`.\n\n{body}\n",
            encoding="utf-8",
        )
        rows.append(
            {
                "unit": unit,
                "Unit": unit,
                "Content": label.replace("|", "/"),
                "PDF pages": f"{first}-{last}",
                "Words": thousands(count),
                "Text": f"`units/{unit}.md`",
            }
        )
        for b in group:
            if b["page"] in titles:
                prev_title = titles[b["page"]]
    warnings += spill_warnings(code, groups, titles)

    header = [
        f"Source: `original/{file.name}` ({len(pages)} pages, about {thousands(total)} words).",
        f"Citations: `{code} uNN [p.N]`, N = page number of the PDF file.",
    ]
    if scan.scanned:
        header.append("Text layer: little or none (scanned PDF). Run OCR, then extract again.")
    write_index(d, code, title, header, PDF_COLUMNS, rows)
    return PdfResult(len(groups), total, len(pages), scan, warnings)


# ---------- pdftotext rebuild (right-to-left scripts) ----------


def read_unit_ranges(index: Path) -> list[tuple[str, int, int]]:
    """Read (unit, first page, last page) from the 'PDF pages' column of an INDEX.md."""
    if not index.exists():
        raise AssaraError(f"No {index}: run `assara add CODE FILE` first, it sets the page ranges.")
    col = None
    ranges = []
    for line in index.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if col is None:
            if "PDF pages" in cells and "Unit" in cells:
                col, ucol = cells.index("PDF pages"), cells.index("Unit")
            continue
        if len(cells) <= col:
            continue
        m = re.fullmatch(r"(\d+)-(\d+)", cells[col])
        if m and re.fullmatch(r"u\d+", cells[ucol]):
            ranges.append((cells[ucol], int(m.group(1)), int(m.group(2))))
    if not ranges:
        raise AssaraError(f"{index} has no unit with a 'PDF pages' range (is it a PDF source?).")
    return ranges


def pdftotext_page(file: Path, page: int, layout: bool = False) -> str:
    """Text of one page with poppler's pdftotext (keeps the logical order of Arabic text)."""
    cmd = ["pdftotext", "-f", str(page), "-l", str(page)] + (["-layout"] if layout else []) + [str(file), "-"]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise AssaraError(f"pdftotext failed on page {page}: {res.stderr.strip()}")
    return res.stdout


def clean_rtl(text: str) -> str:
    """NFKC normalisation (Arabic presentation forms to letters), no bidi controls, no form feeds or other
    control characters (see `library.clean_text`)."""
    text = clean_text(unicodedata.normalize("NFKC", text.translate(BIDI_CONTROLS)).replace("\f", ""))
    return "\n".join(ln.rstrip() for ln in text.strip().splitlines())


def rebuild_pdftotext(
    file: Path, d: Path, code: str, max_words: int, layout: bool = False
) -> list[tuple[str, int, int, int]]:
    """Rewrite raw/pages.md and units/uNN.md with pdftotext, keeping the page ranges of INDEX.md.

    Returns (unit, first, last, words). Notes are never touched; in INDEX.md only the Words cells change.
    """
    if not shutil.which("pdftotext"):
        raise AssaraError("pdftotext not found: install poppler (e.g. apt install poppler-utils).")
    ranges = read_unit_ranges(d / "INDEX.md")
    last_page = max(b for _u, _a, b in ranges)
    pages = {p: clean_rtl(pdftotext_page(file, p, layout)) for p in range(1, last_page + 1)}
    (d / "raw" / "pages.md").write_text(
        f"# {code}: raw text (pdftotext, NFKC)\n\n" + "".join(f"[p.{p}]\n{pages[p]}\n\n" for p in pages),
        encoding="utf-8",
    )
    out = []
    for unit, a, b in ranges:
        body = "\n\n".join(f"[p.{p}]\n{pages[p]}" for p in range(a, b + 1))
        count = words(body) - (b - a + 1)  # do not count the [p.N] markers
        (d / "units" / f"{unit}.md").write_text(
            f"# {code} {unit}: pages {a} to {b}\n\nPages {a} to {b} of the PDF, {thousands(count)} words "
            f"(text extracted with pdftotext to keep the reading order of right-to-left scripts). "
            f"Cite `{code} {unit} [p.N]`.\n\n{body}\n",
            encoding="utf-8",
        )
        out.append((unit, a, b, count))
    update_index_words(d / "INDEX.md", {u: c for u, _a, _b, c in out})
    return out


def update_index_words(index: Path, counts: dict[str, int]) -> None:
    """Replace the Words cell of the given units in INDEX.md; every other cell is kept as is."""
    lines = index.read_text(encoding="utf-8").splitlines()
    wcol = ucol = None
    for i, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        cells = line.strip().strip("|").split("|")
        names = [c.strip() for c in cells]
        if wcol is None:
            if "Words" in names and "Unit" in names:
                wcol, ucol = names.index("Words"), names.index("Unit")
            continue
        if len(cells) > wcol and names[ucol] in counts:
            cells[wcol] = f" {thousands(counts[names[ucol]])} "
            lines[i] = "|" + "|".join(cells) + "|"
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")
