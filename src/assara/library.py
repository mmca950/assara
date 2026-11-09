"""The on-disk library: sources, units, notes and the INDEX of each source.

Layout of a library (see docs/architecture.md):

    <library>/
      assara.toml
      sources/<CODE>/original/   link to (or copy of) the original file, never published
      sources/<CODE>/raw/        raw extraction (pages.md, .srt, .json)
      sources/<CODE>/units/      layer 1: text cut into units (u01.md, ch01-title.md)
      sources/<CODE>/notes/      layer 2: one note per unit, written by the distiller
      sources/<CODE>/INDEX.md    list of units, size and note status
      synthesis/<project>/       layer 3: cross-source sheets
"""

from __future__ import annotations

import contextlib
import re
import shutil
import sys
import unicodedata
from collections.abc import Callable, Iterable
from pathlib import Path

from .config import Config

CODE_RE = re.compile(r"[A-Z0-9]{2,10}")
NOTE_STATUS_RE = re.compile(r"`notes/([\w-]+)\.md` \((done|pending)\)")


class AssaraError(SystemExit):
    """User-facing error: printed without a traceback."""


# Where the package is installed from. Until the first PyPI release, extras come from GitHub.
PACKAGE_SPEC = "assara[{extra}] @ git+https://github.com/mmca950/assara"


def install_hint(extra: str) -> str:
    """How to add an optional extra, for both pip and `uv tool` installs (separate environments)."""
    spec = PACKAGE_SPEC.format(extra=extra)
    return (
        f"install the '{extra}' extra in the environment that runs assara: "
        f'with pip, `pip install "{spec}"`; with uv tool, `uv tool install --force "{spec}"` '
        f"(list every extra you use, e.g. [pdf,{extra}])"
    )


def slug(text: str, length: int = 50) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:length].strip("-") or "untitled"


def words(text: str) -> int:
    return len(text.split())


def hhmmss(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def thousands(n: int) -> str:
    return f"{n:,}"


def check_code(code: str) -> str:
    if not CODE_RE.fullmatch(code):
        raise AssaraError(f"Invalid code '{code}': use 2 to 10 uppercase letters or digits (e.g. BGI, GFM1).")
    return code


def source_dir(cfg: Config, code: str, create: bool = True) -> Path:
    """Return sources/<CODE>/, creating its sub-folders when asked."""
    d = cfg.sources_dir / check_code(code)
    if create:
        for sub in ("original", "raw", "units", "notes"):
            (d / sub).mkdir(parents=True, exist_ok=True)
    elif not d.is_dir():
        raise AssaraError(f"Unknown source '{code}' (no folder {d}).")
    return d


def keep_original(cfg: Config, d: Path, file: Path) -> Path:
    """Keep a reference to the original in original/: a symlink by default, a copy if configured.

    Copying keeps the library readable when the original lives on a removable or network drive.
    A folder (a course, a set of videos) is always linked, never copied: it can weigh gigabytes.
    """
    target = d / "original" / file.name
    if target.exists() or target.is_symlink():
        return target
    if cfg.copy_originals and file.is_file():
        shutil.copy2(file, target)
    else:
        target.symlink_to(file.resolve())
    return target


def note_status(d: Path, unit: str) -> str:
    return "done" if (d / "notes" / f"{unit}.md").exists() else "pending"


UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")


# Control characters (Unicode category Cc) other than LF and tab, and lone surrogates (category Cs).
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def clean_text(text: str) -> str:
    """Text from outside (a web page, a video, a post) made safe to store, show and print.

    CR LF becomes LF. Every other control character except LF and tab becomes a space, so words never
    run together and terminal sequences (ESC, BEL, the C1 range) are broken. A lone surrogate, left by
    a broken decoding, becomes U+FFFD: written under a C locale it would come out as a raw C1 byte.
    """
    text = CONTROL_RE.sub(" ", text.replace("\r\n", "\n"))
    return SURROGATE_RE.sub("\ufffd", text)


def terminal_safe(text: str) -> str:
    """`text` with every control character but LF and tab, and every lone surrogate, shown as '?'."""
    return SURROGATE_RE.sub("?", CONTROL_RE.sub("?", text))


class SafeStream:
    """A text stream that shows control characters as '?' (see `terminal_safe`).

    Titles, captions, page text and tool error messages can come from a remote page. Printed as they
    are, an ESC or BEL in them would let the page drive the terminal (window title, clipboard, cursor).
    `assara` wraps stdout and stderr in it for the whole command (see `cli.main`).
    """

    def __init__(self, stream):
        self.raw_stream = stream

    def write(self, text: str) -> int:
        self.raw_stream.write(terminal_safe(text))
        return len(text)

    def __getattr__(self, name):
        return getattr(self.raw_stream, name)


def unwrap(stream):
    """The stream under every `SafeStream` layer of `stream`."""
    while isinstance(stream, SafeStream):
        stream = stream.raw_stream
    return stream


@contextlib.contextmanager
def raw_output():
    """Unwrap stdout and stderr while a trusted library draws on them (a download progress bar).

    The bar redraws itself with CR and ESC sequences, which `SafeStream` would print as '?'.
    """
    saved = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = (unwrap(s) for s in saved)
    try:
        yield
    finally:
        sys.stdout, sys.stderr = saved


def index_line(text: str) -> str:
    """`text` made safe for one line of INDEX.md (title, header line or table cell).

    Titles, URLs and error texts can come from a remote page or video. Control characters and line
    breaks (including the Unicode line and paragraph separators) become spaces, so the text cannot add
    lines; a note-status marker inside it gets its backticks escaped, so `status` never counts it.
    """
    flat = "".join(" " if unicodedata.category(ch) in ("Cc", "Zl", "Zp") else ch for ch in text)
    return NOTE_STATUS_RE.sub(lambda m: f"\\`notes/{m.group(1)}.md\\` ({m.group(2)})", flat)


def index_cell(text: str) -> str:
    """`text` made safe for a cell of the INDEX table: one line, and every unescaped `|` escaped."""
    return UNESCAPED_PIPE_RE.sub(r"\\|", index_line(text))


def write_index(
    d: Path,
    code: str,
    title: str,
    header: Iterable[str],
    columns: list[str],
    rows: list[dict],
) -> Path:
    """Write sources/<CODE>/INDEX.md. Each row needs a 'unit' key; the Note column is computed.

    A row may carry a 'note' key to replace the computed status with a fixed text, for a unit that
    gets no note (e.g. "no note: index", "no note: no speech"); `status` does not count those rows.
    Rebuilding an index never touches existing notes: their status is read from notes/.
    The title, the header lines and the cells go through index_line and index_cell: they cannot add
    lines or rows, nor a status that `status` would count.
    """
    out = [
        f"# {code}: {index_line(title)} (index)",
        "",
        *(index_line(line) for line in header),
        "",
        "Read ONLY the unit you need. Notes (`notes/`) come before the raw text.",
        "",
        "| " + " | ".join(columns + ["Note"]) + " |",
        "|" + "---|" * (len(columns) + 1),
    ]
    for row in rows:
        cells = [index_cell(str(row.get(c, ""))) for c in columns]
        status = row.get("note") or note_status(d, row["unit"])
        cells.append(f"`notes/{row['unit']}.md` ({status})")
        out.append("| " + " | ".join(cells) + " |")
    path = d / "INDEX.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


def group_blocks(
    blocks: list[dict],
    min_words: int,
    max_words: int,
    key: str = "words",
    can_cut: Callable[[dict], bool] = lambda b: True,
) -> list[list[dict]]:
    """Group consecutive blocks into units of min_words to max_words words.

    A cut is preferred in front of a block where can_cut(block) is true (start of a chapter).
    A short tail (under a third of min_words) is merged into the previous unit.
    """
    units: list[list[dict]] = []
    current: list[dict] = []
    total = 0
    for b in blocks:
        if current and ((total >= min_words and can_cut(b)) or total + b[key] > max_words):
            units.append(current)
            current, total = [], 0
        current.append(b)
        total += b[key]
    if current:
        if units and total < min_words / 3:
            units[-1].extend(current)
        else:
            units.append(current)
    return units


def list_sources(cfg: Config) -> list[Path]:
    if not cfg.sources_dir.is_dir():
        return []
    return sorted(p for p in cfg.sources_dir.iterdir() if p.is_dir() and CODE_RE.fullmatch(p.name))


def sync_index(d: Path) -> list[str]:
    """Mark as (done) every unit of INDEX.md whose note now exists; return the units changed.

    Only the "(pending)" status is touched; fixed texts such as "(no note: index)" are left alone.
    """
    index = d / "INDEX.md"
    if not index.exists():
        return []
    changed: list[str] = []

    def repl(m: re.Match) -> str:
        unit, status = m.group(1), m.group(2)
        if status == "pending" and (d / "notes" / f"{unit}.md").exists():
            changed.append(unit)
            return f"`notes/{unit}.md` (done)"
        return m.group(0)

    text = index.read_text(encoding="utf-8")
    new = NOTE_STATUS_RE.sub(repl, text)
    if changed:
        index.write_text(new, encoding="utf-8")
    return changed


def index_status(d: Path) -> tuple[int, int, list[str]]:
    """Return (done, total, pending units) from a source's INDEX.md.

    Units marked with any other wording (e.g. "no note: index") are not counted.
    """
    index = d / "INDEX.md"
    if not index.exists():
        return 0, 0, []
    found = NOTE_STATUS_RE.findall(index.read_text(encoding="utf-8"))
    pending = [unit for unit, _ in found if not (d / "notes" / f"{unit}.md").exists()]
    return len(found) - len(pending), len(found), pending


def unit_body(text: str) -> str:
    """The text of a unit without its header (title and citation lines), for comparisons.

    The body starts at the first marker line: `[p.N]`, `[§N]`, `[HH:MM:SS]` or a `## ` heading.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("[") or line.startswith("## "):
            return "\n".join(lines[i:]).strip()
    return text.strip()


class NotedUnitsGuard:
    """Protect the citations of existing notes while units are rebuilt.

    Notes cite `CODE uNN [p.N]` or `CODE uNN §N`: if a rebuild cuts the text differently (other
    min_words or max_words, a new media in a folder), those citations would silently point to another
    passage. On entry, the guard saves units/, INDEX.md and raw/*.md; on exit it compares the body of
    every unit that has a note. If one changed or disappeared, it restores the saved files and refuses,
    unless force is true (then it only warns). Units without a note may change freely.
    """

    def __init__(self, d: Path, force: bool = False):
        self.d = d
        self.force = force
        self.backup = d / ".rebuild-backup"
        self.before: dict[str, str] = {}
        self.changed: list[str] = []

    def __enter__(self) -> NotedUnitsGuard:
        units = self.d / "units"
        for note in sorted((self.d / "notes").glob("*.md")):
            unit_file = units / note.name
            if unit_file.exists():
                self.before[note.stem] = unit_body(unit_file.read_text(encoding="utf-8"))
        if self.before:
            if self.backup.exists():
                shutil.rmtree(self.backup)
            (self.backup / "raw").mkdir(parents=True)
            shutil.copytree(units, self.backup / "units")
            if (self.d / "INDEX.md").exists():
                shutil.copy2(self.d / "INDEX.md", self.backup / "INDEX.md")
            for f in (self.d / "raw").glob("*.md"):
                shutil.copy2(f, self.backup / "raw" / f.name)
        return self

    def _restore(self) -> None:
        shutil.rmtree(self.d / "units")
        shutil.copytree(self.backup / "units", self.d / "units")
        if (self.backup / "INDEX.md").exists():
            shutil.copy2(self.backup / "INDEX.md", self.d / "INDEX.md")
        for f in (self.backup / "raw").glob("*.md"):
            shutil.copy2(f, self.d / "raw" / f.name)

    def __exit__(self, exc_type, exc, tb) -> bool:
        if not self.before:
            return False
        try:
            if exc_type is not None:
                self._restore()
                return False
            for unit, body in self.before.items():
                f = self.d / "units" / f"{unit}.md"
                if not f.exists() or unit_body(f.read_text(encoding="utf-8")) != body:
                    self.changed.append(unit)
            if self.changed and not self.force:
                self._restore()
                raise AssaraError(
                    f"{self.d.name}: this rebuild would change the text of units that already have a "
                    f"note ({', '.join(self.changed)}), so their citations would point to other "
                    "passages. Nothing was changed. Keep the previous min_words and max_words (or the "
                    "same media list), or run again with --force and then review those notes."
                )
            if self.changed:
                print(
                    f"WARNING: the text of {', '.join(self.changed)} changed; their notes are kept but "
                    "their citations must be checked."
                )
        finally:
            shutil.rmtree(self.backup, ignore_errors=True)
        return False
