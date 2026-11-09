"""SubRip (.srt) subtitles: read, write, clean, and turn into timestamped paragraphs and units.

A transcript unit is a list of paragraphs, each starting with one `[HH:MM:SS]` timestamp, so a note can
cite `CODE chNN [HH:MM:SS]`. Timestamps always stay those of the media file, even when a long media is
cut into several parts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .library import clean_text as clean_controls
from .library import hhmmss, words

TIME_RE = re.compile(r"(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})\s*-->\s*(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})")
TAG_RE = re.compile(r"<[^>]+>|\{\\[^}]*\}")


@dataclass
class Cue:
    """One subtitle cue (or one Whisper segment): start and end in seconds, and its text."""

    start: float
    end: float
    text: str


def _seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def clean_text(text: str) -> str:
    """Remove formatting tags (<i>, <font>, {\\an8}) and control characters, and collapse white space."""
    return " ".join(TAG_RE.sub("", clean_controls(text)).split())


def parse_srt(text: str) -> list[Cue]:
    """Parse SRT text. Cue numbers are optional; empty cues and malformed blocks are skipped."""
    cues = []
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        for k, line in enumerate(lines):
            m = TIME_RE.search(line)
            if m:
                g = m.groups()
                body = clean_text(" ".join(x.strip() for x in lines[k + 1 :] if x.strip()))
                if body:
                    cues.append(Cue(_seconds(*g[:4]), _seconds(*g[4:]), body))
                break
    return cues


def read_srt(path: Path) -> list[Cue]:
    return parse_srt(path.read_text(encoding="utf-8", errors="replace"))


def looks_like_srt(path: Path) -> bool:
    """True if the start of the file contains a cue timing line (for subtitles without extension)."""
    try:
        head = path.read_bytes()[:400].decode("utf-8", errors="replace")
    except OSError:
        return False
    return bool(TIME_RE.search(head))


def timestamp(seconds: float) -> str:
    """SRT timestamp: HH:MM:SS,mmm."""
    ms = max(0, int(round(seconds * 1000)))
    return f"{ms // 3_600_000:02d}:{ms % 3_600_000 // 60_000:02d}:{ms % 60_000 // 1000:02d},{ms % 1000:03d}"


def format_srt(cues: Iterable[Cue]) -> str:
    blocks = [
        f"{i}\n{timestamp(c.start)} --> {timestamp(c.end)}\n{c.text.strip()}\n"
        for i, c in enumerate(cues, start=1)
    ]
    return "\n".join(blocks)


def write_srt(cues: Iterable[Cue], path: Path) -> Path:
    """Write an SRT file atomically (through a .part file), so an interrupted pass leaves no half file.

    An empty cue list writes an empty file: it records a media without speech, never re-transcribed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(format_srt(cues), encoding="utf-8")
    tmp.replace(path)
    return path


def dedupe_rolling(cues: list[Cue]) -> list[Cue]:
    """Remove the repetitions of automatic subtitles, where each cue repeats the end of the previous one.

    A cue identical to the previous one is dropped; a cue that starts with the previous text keeps only
    the new words.
    """
    out: list[Cue] = []
    prev = ""
    for c in cues:
        text = c.text
        if prev and text == prev:
            continue
        if prev and text.startswith(prev + " "):
            text = text[len(prev) + 1 :]
        prev = c.text
        if text.strip():
            out.append(Cue(c.start, c.end, text.strip()))
    return out


def paragraphs(cues: Iterable[Cue], seconds: float = 60, max_words: int = 150) -> list[tuple[float, str]]:
    """Group cues into paragraphs of about `seconds` seconds or `max_words` words: (start, text)."""
    paras: list[tuple[float, str]] = []
    start: float | None = None
    current: list[str] = []
    count = 0
    for c in cues:
        if current and start is not None and (c.start - start >= seconds or count >= max_words):
            paras.append((start, " ".join(current)))
            start, current, count = None, [], 0
        if start is None:
            start = c.start
        current.append(c.text)
        count += words(c.text)
    if current and start is not None:
        paras.append((start, " ".join(current)))
    return paras


def stamped(paras: Iterable[tuple[float, str]]) -> list[str]:
    """Format paragraphs as `[HH:MM:SS] text`."""
    return [f"[{hhmmss(t)}] {text}" for t, text in paras]


def split_parts(paras: list[str], max_words: int, target_words: int) -> list[list[str]]:
    """Cut a long transcript into parts of about target_words words, between two paragraphs.

    A transcript of at most max_words words stays whole.
    """
    total = sum(words(p) for p in paras)
    if total <= max_words or target_words <= 0:
        return [paras]
    n = -(-total // target_words)
    goal = total / n
    parts: list[list[str]] = []
    current: list[str] = []
    count = 0
    for p in paras:
        if current and count >= goal and len(parts) < n - 1:
            parts.append(current)
            current, count = [], 0
        current.append(p)
        count += words(p)
    parts.append(current)
    return parts
