"""`assara transcribe CODE PATH`: audio or video (one file or a folder) into layer 1 units.

- An existing .srt next to a media (provided subtitles, also `.SRT` or a subtitle file without extension)
  is reused as is: no Whisper.
- Otherwise faster-whisper writes the .srt into sources/CODE/raw/, never next to the original (the
  original folder may be read-only or on someone else's disk).
- Resumable: a media that already has its .srt is skipped. Ctrl+C, then run again, resumes at the first
  media without a .srt. An error skips the media and lists it; three errors in a row with no success
  stop the pass (the environment is likely broken).
- A media with no speech (0 segments) gets an empty .srt: it is recorded in the INDEX and never
  re-transcribed (Whisper would invent text).
- At the end: units/chNN-<slug>.md (paragraphs, one [HH:MM:SS] each) and INDEX.md. NN is the rank of the
  media in the sorted list, so it stays stable when the pass is partial. A media longer than max_words is
  cut into parts chNNa, chNNb... Existing notes are never touched.
"""

from __future__ import annotations

import argparse
import hashlib
import shlex
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..library import (
    AssaraError,
    NotedUnitsGuard,
    hhmmss,
    keep_original,
    slug,
    source_dir,
    thousands,
    words,
    write_index,
)
from ..srt import Cue, looks_like_srt, paragraphs, read_srt, split_parts, stamped, write_srt

MEDIA_SUFFIXES = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus",
    ".aac", ".ts", ".flv", ".mpg", ".mpeg", ".wma", ".wmv",
}  # fmt: skip
SRT_NAME_MAX = 120
MAX_FAILURES_IN_A_ROW = 3
LONG_PASS = 3  # media to transcribe from which the nohup / tmux hint is printed


def configure(sub) -> None:
    p = sub.add_parser(
        "transcribe",
        help="transcribe audio or video (file or folder) into timestamped units",
        description=__doc__.split("\n\n", 1)[1] if __doc__ else None,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("code", help="source code, e.g. TALK1")
    p.add_argument("path", type=Path, help="one media file, or a folder (recursive, sorted by path)")
    p.add_argument("--title", help="title of the source (default: file or folder name)")
    p.add_argument("--language", help="audio language (en, fr, ar...); default: config, else automatic")
    p.add_argument("--model", help="faster-whisper model (small, medium, large-v3); default: config")
    p.add_argument("--device", choices=["cpu", "cuda"], help="default: config")
    p.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="TEXT",
        help="skip media whose path contains TEXT (case-insensitive, repeatable)",
    )
    p.add_argument(
        "--index-only", action="store_true", help="transcribe nothing, rebuild units/ and INDEX.md"
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="rebuild units even if the text of units that already have a note changes",
    )
    p.set_defaults(func=run)


# ---------------------------------------------------------------------------------------------- media


def list_media(path: Path, exclude: list[str] | tuple[str, ...] = ()) -> list[Path]:
    """One media file, or every media under a folder, sorted by path (case-insensitive)."""
    if path.is_file():
        return [path]
    excluded = [x.lower() for x in exclude]
    found = (
        p
        for p in path.rglob("*")
        if p.is_file()
        and p.suffix.lower() in MEDIA_SUFFIXES
        and not any(x in str(p.relative_to(path)).lower() for x in excluded)
    )
    return sorted(found, key=lambda p: str(p.relative_to(path)).lower())


def srt_path_for(media: Path, root: Path, d: Path) -> Path:
    """Where the subtitles of a media are: a provided file next to it, else sources/CODE/raw/<name>.srt.

    The raw/ name comes from the path relative to the PATH given on the command line. A long name is cut
    and ends with a hash of the path, so two long paths never share (and overwrite) one .srt.
    """
    for neighbour in (media.with_suffix(".srt"), media.with_suffix(".SRT")):
        if neighbour.is_file():
            return neighbour
    bare = media.with_suffix("")  # subtitles provided without extension
    if bare != media and bare.is_file() and looks_like_srt(bare):
        return bare
    rel = str(media.relative_to(root)) if root.is_dir() else media.name
    name = slug(rel, 10_000)
    if len(name) > SRT_NAME_MAX:
        digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:8]
        name = name[: SRT_NAME_MAX - 9].strip("-") + "-" + digest
    return d / "raw" / f"{name}.srt"


# ----------------------------------------------------------------------------------------------- pass


@dataclass
class PassReport:
    total: int = 0
    skipped: int = 0  # already had a .srt
    done: list[Path] = field(default_factory=list)
    silent: list[Path] = field(default_factory=list)
    errors: list[tuple[Path, str]] = field(default_factory=list)
    stopped: bool = False  # three errors in a row with no success
    interrupted: bool = False


def run_pass(
    media: list[Path],
    srt_paths: dict[Path, Path],
    make_transcriber: Callable[[], Callable[[Path], list[Cue]]],
    log: Callable[[str], None] = print,
) -> PassReport:
    """Transcribe every media that has no .srt yet. The model is loaded only if there is work to do."""
    todo = [m for m in media if not srt_paths[m].exists()]
    report = PassReport(total=len(media), skipped=len(media) - len(todo))
    log(f"{len(media)} media, {report.skipped} already transcribed, {len(todo)} to do.")
    if not todo:
        return report
    transcribe = make_transcriber()
    in_a_row = 0
    for i, m in enumerate(todo, start=1):
        log(f"[{i}/{len(todo)}] {m.name} ...")
        t0 = time.time()
        try:
            cues = transcribe(m)
            write_srt(cues, srt_paths[m])
        except KeyboardInterrupt:
            log("Interrupted. Run the same command again to resume at the first media without a .srt.")
            report.interrupted = True
            return report
        except Exception as e:  # noqa: BLE001 (one bad file must not stop the pass)
            report.errors.append((m, str(e) or type(e).__name__))
            in_a_row += 1
            log(f"    ERROR: {e}")
            if in_a_row >= MAX_FAILURES_IN_A_ROW and i == in_a_row:
                log("Three errors in a row and no success: check the environment before running again.")
                report.stopped = True
                return report
            continue
        in_a_row = 0
        report.done.append(m)
        if not cues:
            report.silent.append(m)
            log("    NO SPEECH: 0 segments. Recorded in the INDEX and never re-transcribed.")
        else:
            log(f"    ok: {hhmmss(cues[-1].end)} of audio in {hhmmss(time.time() - t0)}")
    return report


# -------------------------------------------------------------------------------------------- build


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def build_units(
    media: list[Path],
    srt_paths: dict[Path, Path],
    d: Path,
    code: str,
    title: str,
    source: Path,
    min_words: int,
    max_words: int,
) -> list[dict]:
    """Rebuild units/chNN-*.md and INDEX.md from the .srt files. Notes are never touched."""
    for f in (d / "units").glob("ch*.md"):
        f.unlink()
    root = source if source.is_dir() else source.parent
    rows: list[dict] = []
    silent: list[str] = []
    missing = 0
    total_s = 0.0
    total_w = 0
    target = (min_words + max_words) // 2
    for n, m in enumerate(media, start=1):
        srt = srt_paths[m]
        if not srt.exists():
            missing += 1
            continue
        cues = read_srt(srt)
        if not cues:
            silent.append(f"ch{n:02d} `{m.relative_to(root)}`")
            continue
        duration = cues[-1].end
        paras = stamped(paragraphs(cues))
        parts = split_parts(paras, max_words, target)
        for k, block in enumerate(parts):
            ch = f"ch{n:02d}" + (chr(ord("a") + k) if len(parts) > 1 else "")
            body = "\n\n".join(block)
            count = words(body)
            span = f"{block[0][1:9]} to {block[-1][1:9]}"
            unit_title = m.stem + (f" (part {k + 1}/{len(parts)}, {span})" if len(parts) > 1 else "")
            name = f"{ch}-{slug(m.stem)}"
            (d / "units" / f"{name}.md").write_text(
                f"# {code} {ch}: {unit_title}\n\n"
                f"File: `{m.relative_to(root)}`; duration about {hhmmss(duration)}; "
                f"{thousands(count)} words. "
                "Automatic transcript: flag a garbled passage (above all a number) instead of guessing. "
                f"Cite `{code} {ch} [HH:MM:SS]`.\n\n{body}\n",
                encoding="utf-8",
            )
            rows.append(
                {
                    "unit": ch,
                    "Unit": ch,
                    "Content": _cell(unit_title),
                    "Duration": hhmmss(duration) if len(parts) == 1 else span,
                    "Words": thousands(count),
                    "Text": f"`units/{name}.md`",
                }
            )
            total_w += count
        total_s += duration
    header = [
        f"Source: `{source}` ({len(media) - missing} of {len(media)} media transcribed, about "
        f"{hhmmss(total_s)}, {thousands(total_w)} words).",
        f"Citations: `{code} chNN [HH:MM:SS]`. "
        "Automatic transcripts: a garbled passage is flagged, never guessed.",
    ]
    if silent:
        header.append(
            "No speech (0 segments, never re-transcribed since Whisper would invent text): "
            + ", ".join(silent)
            + "."
        )
    if missing:
        header.append(f"Not transcribed yet: {missing} media (run `assara transcribe` again to resume).")
    write_index(d, code, title, header, ["Unit", "Content", "Duration", "Words", "Text"], rows)
    return rows


# ---------------------------------------------------------------------------------------------- run


def run(args, cfg) -> int:
    path: Path = args.path.expanduser()
    if not path.exists():
        raise AssaraError(f"Not found: {path}")
    media = list_media(path, args.exclude)
    if not media:
        raise AssaraError(f"No audio or video file found in {path}.")
    d = source_dir(cfg, args.code)
    root = path if path.is_dir() else path.parent
    srt_paths = {m: srt_path_for(m, root, d) for m in media}

    if path.is_dir() and cfg.copy_originals:
        print("copy_originals is on, but PATH is a folder: linked in original/, not copied (too large).")
    keep_original(cfg, d, path)

    report = None
    if not args.index_only:
        device = args.device or cfg.whisper_device
        model = args.model or cfg.whisper_model
        language = args.language or cfg.language or None
        from ..whisper import compute_type_for, make_transcriber

        overridden = bool(args.device) and args.device != cfg.whisper_device
        compute = compute_type_for(device, cfg.whisper_compute_type, overridden)

        def factory():
            print(
                f"Loading faster-whisper '{model}' on {device} ({compute}), language: {language or 'auto'}."
            )
            return make_transcriber(model, device, compute, language)

        todo = sum(1 for m in media if not srt_paths[m].exists())
        if todo >= LONG_PASS:
            print(
                "Long pass: run it detached and gently, e.g. `nohup "
                + shlex.join(["nice", "-n", "19", "assara", "transcribe", args.code, str(path)])
                + " > transcribe.log 2>&1 &`, or inside tmux. "
                "It can be resumed at any time."
            )
        report = run_pass(media, srt_paths, factory)
        if report.interrupted or report.stopped:
            _print_report(report)
            return 1

    title = args.title or (path.name if path.is_dir() else path.stem)
    with NotedUnitsGuard(d, force=args.force):
        rows = build_units(media, srt_paths, d, args.code, title, path, cfg.min_words, cfg.max_words)
    print(f"{args.code}: {len(rows)} unit(s) built. Index: {d / 'INDEX.md'}")
    if (d / "raw" / "modules.txt").exists():
        print(f"This source is grouped into modules: run `assara regroup {args.code}` again.")
    if report is not None:
        _print_report(report)
        return 1 if report.errors else 0
    return 0


def _print_report(report: PassReport) -> None:
    print(
        f"\nReport: {len(report.done)} transcribed ({len(report.silent)} without speech), "
        f"{report.skipped} skipped (already had a .srt), {len(report.errors)} error(s)."
    )
    for m, e in report.errors:
        print(f"  - {m}: {e}")
    if report.errors or report.interrupted:
        print("Run the same command again to retry: transcribed media are skipped.")
