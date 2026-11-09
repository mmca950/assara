"""`assara regroup CODE`: group the short lessons of a course into modules, one note per module.

A course of many short lessons (500 to 2,000 words each) is distilled by module rather than by lesson.
The text and the citations stay per lesson (`CODE chNN [HH:MM:SS]`, timestamps of each lesson); only the
notes are per module (`notes/mNN.md`).

Modules are read from sources/CODE/raw/modules.txt, one line per module (blank lines and # ignored):

    m01 | Title of the module | ch01-ch10
    m02 | Another module | ch11,ch12,ch15-ch18
    skip | ch13,ch14 | reason (duplicate, out of scope...)

Without modules.txt, consecutive lessons are grouped into modules of min_words to max_words words, and
the result is written to modules.txt so it can be edited and the command run again.

The per-lesson INDEX.md is kept in raw/INDEX-by-lesson.md, then INDEX.md is rewritten by module. Run this
command again after `assara transcribe`, which rewrites the per-lesson index.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from ..library import AssaraError, group_blocks, source_dir, thousands, write_index

LESSON_RE = re.compile(r"^\| (ch(\d+)[a-z]?) \| (.*) \| (.*?) \| ([\d,]+) \| `(units/[^`]+)` \|")
CH_RE = re.compile(r"ch(\d+)")
MODULE_RE = re.compile(r"[A-Za-z][\w-]*")
BY_LESSON = "INDEX-by-lesson.md"
MODULE_HEADER = "| Module |"


@dataclass
class Lesson:
    unit: str  # ch01, or ch02a for a part of a long lesson
    number: int
    title: str
    duration: str
    words: int
    text: str


@dataclass
class Module:
    name: str
    title: str
    numbers: list[int]


def configure(sub) -> None:
    p = sub.add_parser(
        "regroup",
        help="group short lessons into modules (one note per module, citations per lesson)",
        description=__doc__.split("\n\n", 1)[1] if __doc__ else None,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("code", help="source code")
    p.set_defaults(func=run)


def parse_range(text: str) -> set[int]:
    """`ch01-ch03,ch07` -> {1, 2, 3, 7}."""
    numbers: set[int] = set()
    for piece in text.split(","):
        piece = piece.strip()
        if not piece:
            continue
        a, _, b = piece.partition("-")
        ma, mb = CH_RE.fullmatch(a.strip()), CH_RE.fullmatch(b.strip()) if b else None
        if not ma or (b and not mb):
            raise ValueError(f"bad lesson range '{piece}' (expected chNN or chNN-chMM)")
        start = int(ma.group(1))
        end = int(mb.group(1)) if mb else start
        if end < start:
            raise ValueError(f"bad lesson range '{piece}' (end before start)")
        numbers.update(range(start, end + 1))
    return numbers


def parse_lessons(index_text: str) -> list[Lesson]:
    lessons = []
    for line in index_text.splitlines():
        m = LESSON_RE.match(line)
        if m:
            unit, num, title, duration, count, text = m.groups()
            lessons.append(Lesson(unit, int(num), title, duration, int(count.replace(",", "")), text))
    return lessons


def parse_modules(text: str) -> tuple[list[Module], dict[int, str]]:
    """Parse modules.txt: (modules, {lesson number: reason} for skipped lessons)."""
    modules: list[Module] = []
    skipped: dict[int, str] = {}
    seen: set[str] = set()
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [x.strip() for x in line.split("|", 2)]
        if len(parts) != 3:
            raise AssaraError(f"modules.txt line {n}: expected 3 fields separated by '|'.")
        a, b, c = parts
        try:
            if a.lower() == "skip":
                for num in parse_range(b):
                    skipped[num] = c or "no reason given"
                continue
            if not MODULE_RE.fullmatch(a) or a.lower().startswith("ch"):
                raise ValueError(f"bad module name '{a}' (e.g. m01)")
            if a in seen:
                raise ValueError(f"module '{a}' defined twice")
            seen.add(a)
            modules.append(Module(a, b, sorted(parse_range(c))))
        except ValueError as e:
            raise AssaraError(f"modules.txt line {n}: {e}.") from e
    return modules, skipped


def auto_modules(lessons: list[Lesson], min_words: int, max_words: int) -> list[Module]:
    """Group consecutive lessons into modules of min_words to max_words words."""
    by_number: dict[int, dict] = {}
    for les in lessons:
        b = by_number.setdefault(les.number, {"number": les.number, "words": 0, "title": les.title})
        b["words"] += les.words
    groups = group_blocks([by_number[k] for k in sorted(by_number)], min_words, max_words)
    modules = []
    for i, g in enumerate(groups, start=1):
        first, last = g[0], g[-1]
        title = first["title"] if len(g) == 1 else f"{first['title']} to {last['title']}"
        modules.append(
            Module(f"m{i:02d}", re.sub(r" \(part \d+/\d+.*\)$", "", title), [b["number"] for b in g])
        )
    return modules


def format_modules(modules: list[Module]) -> str:
    out = [
        "# One line per module: name | title | lessons (chNN-chMM, chNN,chMM). Lessons to leave out:",
        "# skip | ch13,ch14 | reason. Edit, then run `assara regroup CODE` again.",
    ]
    for mod in modules:
        nums = mod.numbers
        contiguous = nums == list(range(nums[0], nums[-1] + 1))
        lessons = f"ch{nums[0]:02d}-ch{nums[-1]:02d}" if contiguous else ",".join(f"ch{n:02d}" for n in nums)
        out.append(f"{mod.name} | {mod.title.replace('|', '/')} | {lessons}")
    return "\n".join(out) + "\n"


def regroup(d: Path, code: str, min_words: int, max_words: int) -> tuple[list[Module], dict[int, str], bool]:
    """Rewrite INDEX.md by module. Returns (modules, skipped lessons, modules.txt was generated)."""
    index = d / "INDEX.md"
    copy = d / "raw" / BY_LESSON
    if not index.exists() and not copy.exists():
        raise AssaraError(f"{code}: no INDEX.md. Run `assara transcribe` first.")
    if index.exists() and MODULE_HEADER not in index.read_text(encoding="utf-8"):
        # first run, or transcribe rewrote the per-lesson index: keep the fresh one
        copy.write_text(index.read_text(encoding="utf-8"), encoding="utf-8")
    elif not copy.exists():
        raise AssaraError(
            f"{code}: INDEX.md is by module but raw/{BY_LESSON} is missing; "
            "run `assara transcribe --index-only` first."
        )
    source = copy.read_text(encoding="utf-8")
    lessons = parse_lessons(source)
    if not lessons:
        raise AssaraError(f"{code}: no lesson found in {copy}.")

    modules_file = d / "raw" / "modules.txt"
    generated = not modules_file.exists()
    if generated:
        modules_file.write_text(format_modules(auto_modules(lessons, min_words, max_words)), encoding="utf-8")
    modules, skipped = parse_modules(modules_file.read_text(encoding="utf-8"))
    if not modules:
        raise AssaraError(f"{modules_file}: no module defined.")

    known = {les.number for les in lessons}
    module_of: dict[int, str] = {}
    rows = []
    for mod in modules:
        unknown = [n for n in mod.numbers if n not in known]
        if unknown:
            print(
                f"Warning: module {mod.name} lists lessons not in the index: "
                + ", ".join(f"ch{n:02d}" for n in unknown)
            )
        for n in mod.numbers:
            if n in module_of:
                raise AssaraError(f"modules.txt: ch{n:02d} is in both {module_of[n]} and {mod.name}.")
            module_of[n] = mod.name
        units = [les.unit for les in lessons if les.number in mod.numbers]
        count = sum(les.words for les in lessons if les.number in mod.numbers)
        rows.append(
            {
                "unit": mod.name,
                "Module": mod.name,
                "Title": mod.title.replace("|", "\\|"),
                "Lessons": ", ".join(units),
                "Words": thousands(count),
            }
        )

    first = source.splitlines()[0] if source else f"# {code}: {code} (index)"
    title = re.sub(r"^# [^:]+: ", "", first)
    title = re.sub(r" \(index.*$", "", title)
    header = [
        line
        for line in source.splitlines()[1:]
        if line.startswith(("Source:", "No speech", "Not transcribed"))
    ]
    header += [
        f"One note per module (`notes/mNN.md`); the text and the citations stay per lesson: `{code} chNN "
        "[HH:MM:SS]` (timestamps of each lesson). Modules are defined in `raw/modules.txt`; the "
        f"per-lesson index is kept in `raw/{BY_LESSON}`.",
    ]
    write_index(d, code, f"{title} (by module)", header, ["Module", "Title", "Lessons", "Words"], rows)

    out = [
        "",
        "## Lessons",
        "",
        "| Unit | Content | Duration | Words | Text | Module |",
        "|---|---|---|---|---|---|",
    ]
    for les in lessons:
        where = module_of.get(les.number) or f"left out ({skipped.get(les.number, 'not assigned')})"
        out.append(
            f"| {les.unit} | {les.title} | {les.duration} | {thousands(les.words)} | `{les.text}` | {where} |"
        )
    with index.open("a", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    return modules, skipped, generated


def run(args, cfg) -> int:
    d = source_dir(cfg, args.code, create=False)
    modules, skipped, generated = regroup(d, args.code, cfg.min_words, cfg.max_words)
    if generated:
        print(
            f"No raw/modules.txt: modules made from word counts and written to {d / 'raw' / 'modules.txt'} "
            "(edit it and run again to change them)."
        )
    print(
        f"{args.code}: {len(modules)} module(s), {len(skipped)} lesson(s) left out. Index: {d / 'INDEX.md'}"
    )
    return 0
