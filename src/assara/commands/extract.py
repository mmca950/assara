"""`assara add CODE FILE`: extract a PDF or an EPUB into raw/, units/ and INDEX.md.

Re-running regenerates raw/, units/ and INDEX.md; existing notes are never touched, and the rebuild is
refused if it would change the text of a unit that already has a note (see --force).
Audio and video: `assara transcribe`.
"""

from __future__ import annotations

from pathlib import Path

from ..library import AssaraError, NotedUnitsGuard, check_code, keep_original, source_dir, thousands


def configure(sub) -> None:
    p = sub.add_parser(
        "add",
        aliases=["extract"],
        help="extract a PDF or EPUB into units of raw text and an INDEX",
        description=__doc__,
    )
    p.add_argument("code", help="short uppercase code of the source (e.g. BOOK1)")
    p.add_argument("file", type=Path, help="the .pdf or .epub file")
    p.add_argument("--title", help='"Title, author, year" (default: the file name)')
    p.add_argument(
        "--force",
        action="store_true",
        help="rebuild even if the text of units that already have a note changes (then check their notes)",
    )
    p.set_defaults(func=run)


def run(args, cfg) -> int:
    code = check_code(args.code)
    file: Path = args.file.expanduser()
    if not file.is_file():
        raise AssaraError(f"File not found: {file}")
    ext = file.suffix.lower()
    if ext not in (".pdf", ".epub"):
        raise AssaraError(f"Type {ext or '(none)'} is not handled here. Audio or video: assara transcribe.")
    d = source_dir(cfg, code)
    keep_original(cfg, d, file)
    title = args.title or file.stem
    with NotedUnitsGuard(d, force=args.force):
        if ext == ".pdf":
            from ..pdf import extract_pdf

            res = extract_pdf(file, d, code, title, cfg.min_words, cfg.max_words, cfg.language)
            summary = f"{code}: {res.units} unit(s), {res.pages} pages, about {thousands(res.words)} words."
            warnings = res.warnings
        else:
            from ..epub import extract_epub

            res = extract_epub(file, d, code, title, cfg.min_words, cfg.max_words)
            summary = (
                f"{code}: {res.units} unit(s), {res.chapters} chapters, about {thousands(res.words)} words."
            )
            warnings = []
    print(summary)
    for w in warnings:
        print(w)
    print(f"Index: {d / 'INDEX.md'}")
    print("Next: add the source to catalog.md, then distill unit by unit.")
    return 0
