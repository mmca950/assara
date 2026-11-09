"""`assara rebuild-pdftotext CODE FILE`: redo raw/pages.md and units/ with pdftotext.

Use it after `assara add` when PyMuPDF garbles a right-to-left script such as Arabic (letters of
each line reversed, presentation forms, words glued together). The unit page ranges of INDEX.md are
kept; text is normalised to Unicode NFKC and bidirectional control characters are removed.
Notes are never touched.
"""

from __future__ import annotations

from pathlib import Path

from ..library import AssaraError, source_dir, thousands


def configure(sub) -> None:
    p = sub.add_parser(
        "rebuild-pdftotext",
        help="rebuild a PDF source's text with pdftotext (Arabic and other right-to-left scripts)",
        description=__doc__,
    )
    p.add_argument("code", help="code of a source already extracted with `assara add`")
    p.add_argument("file", type=Path, help="the same .pdf file")
    p.add_argument(
        "--layout",
        action="store_true",
        help="call pdftotext with -layout (keeps columns; plain reading order is usually better for Arabic)",
    )
    p.set_defaults(func=run)


def run(args, cfg) -> int:
    from ..pdf import rebuild_pdftotext

    d = source_dir(cfg, args.code, create=False)
    file: Path = args.file.expanduser()
    if not file.is_file():
        raise AssaraError(f"File not found: {file}")
    units = rebuild_pdftotext(file, d, args.code, cfg.max_words, layout=args.layout)
    for unit, a, b, count in units:
        flag = "  (over max_words: consider cutting again)" if count > cfg.max_words else ""
        print(f"{args.code} {unit}: pages {a}-{b}, {thousands(count)} words{flag}")
    print(f"Rewritten: raw/pages.md and {len(units)} unit(s). Notes untouched; INDEX.md word counts updated.")
    return 0
