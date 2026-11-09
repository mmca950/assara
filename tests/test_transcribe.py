from pathlib import Path

import pytest

from assara.cli import main
from assara.commands import transcribe as tr
from assara.config import Config
from assara.library import index_status
from assara.srt import Cue, read_srt, write_srt


def make_library(tmp_path: Path, min_words: int = 50, max_words: int = 100) -> Config:
    root = tmp_path / "lib"
    root.mkdir()
    (root / "assara.toml").write_text(
        f"[units]\nmin_words = {min_words}\nmax_words = {max_words}\n", encoding="utf-8"
    )
    return Config.load(root)


def make_course(tmp_path: Path, names: list[str]) -> Path:
    course = tmp_path / "course"
    for n in names:
        p = course / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"not really audio")
    return course


def cues_for(media: Path, n_words: int = 20) -> list[Cue]:
    return [Cue(i * 5.0, i * 5.0 + 4, f"{media.stem} " + "word " * (n_words - 1)) for i in range(3)]


class FakeTranscriber:
    """Stands in for faster-whisper: returns cues, raises, or returns nothing (no speech)."""

    def __init__(self, fail: set[str] = frozenset(), silent: set[str] = frozenset()):
        self.fail, self.silent, self.calls, self.loads = fail, silent, [], 0

    def factory(self):
        self.loads += 1
        return self.transcribe

    def transcribe(self, media: Path) -> list[Cue]:
        self.calls.append(media.name)
        if media.name in self.fail:
            raise RuntimeError("cannot decode")
        if media.name in self.silent:
            return []
        return cues_for(media)


def setup(tmp_path, names):
    cfg = make_library(tmp_path)
    course = make_course(tmp_path, names)
    d = cfg.sources_dir / "CRS1"
    for sub in ("original", "raw", "units", "notes"):
        (d / sub).mkdir(parents=True)
    media = tr.list_media(course)
    return cfg, course, d, media, {m: tr.srt_path_for(m, course, d) for m in media}


def test_list_media_sorted_recursive_and_excluded(tmp_path):
    course = make_course(tmp_path, ["b/2.mp4", "a/10.MP4", "a/1.mp3", "a/1.txt", "c/x.mp4"])
    got = [str(p.relative_to(course)) for p in tr.list_media(course, ["C/"])]
    assert got == ["a/1.mp3", "a/10.MP4", "b/2.mp4"]
    single = course / "a" / "1.mp3"
    assert tr.list_media(single) == [single]


def test_srt_path_neighbour_bare_and_raw(tmp_path):
    course = make_course(tmp_path, ["one.mp4", "two.mp4", "three.mp4", "three"])
    d = tmp_path / "src"
    write_srt([Cue(0, 1, "x")], course / "one.srt")
    write_srt([Cue(0, 1, "x")], course / "three")  # subtitles without extension
    assert tr.srt_path_for(course / "one.mp4", course, d) == course / "one.srt"
    assert tr.srt_path_for(course / "three.mp4", course, d) == course / "three"
    assert tr.srt_path_for(course / "two.mp4", course, d) == d / "raw" / "two-mp4.srt"


def test_srt_path_long_names_stay_unique(tmp_path):
    long = "a-very-long-folder-name-" * 6
    course = make_course(tmp_path, [f"{long}/lesson-1.mp4", f"{long}/lesson-2.mp4"])
    d = tmp_path / "src"
    paths = {tr.srt_path_for(m, course, d) for m in tr.list_media(course)}
    assert len(paths) == 2
    assert all(len(p.stem) <= tr.SRT_NAME_MAX for p in paths)


def test_pass_resume_skip_error_and_silence(tmp_path):
    names = ["01.mp4", "02.mp4", "03.mp4", "04.mp4"]
    cfg, course, d, media, srts = setup(tmp_path, names)
    write_srt(cues_for(course / "01.mp4"), course / "01.srt")  # provided subtitles
    srts = {m: tr.srt_path_for(m, course, d) for m in media}
    fake = FakeTranscriber(fail={"03.mp4"}, silent={"04.mp4"})
    report = tr.run_pass(media, srts, fake.factory, log=lambda s: None)
    assert fake.calls == ["02.mp4", "03.mp4", "04.mp4"]
    assert report.skipped == 1 and len(report.done) == 2 and len(report.errors) == 1
    assert [m.name for m in report.silent] == ["04.mp4"]
    assert srts[media[3]].exists() and read_srt(srts[media[3]]) == []
    assert not srts[media[2]].exists()
    assert not list(course.glob("*.srt.part")) and sorted(p.name for p in course.glob("*.srt")) == ["01.srt"]

    # second pass: only the failed media is tried again; the silent one is never re-transcribed
    fake2 = FakeTranscriber()
    report = tr.run_pass(media, srts, fake2.factory, log=lambda s: None)
    assert fake2.calls == ["03.mp4"] and report.skipped == 3

    # nothing to do: the model is not even loaded
    fake3 = FakeTranscriber()
    tr.run_pass(media, srts, fake3.factory, log=lambda s: None)
    assert fake3.loads == 0 and fake3.calls == []


def test_pass_stops_after_three_errors_without_success(tmp_path):
    names = [f"{i:02d}.mp4" for i in range(1, 6)]
    cfg, course, d, media, srts = setup(tmp_path, names)
    fake = FakeTranscriber(fail=set(names))
    report = tr.run_pass(media, srts, fake.factory, log=lambda s: None)
    assert report.stopped and len(fake.calls) == 3


def test_pass_continues_errors_after_a_success(tmp_path):
    names = [f"{i:02d}.mp4" for i in range(1, 6)]
    cfg, course, d, media, srts = setup(tmp_path, names)
    fake = FakeTranscriber(fail=set(names[1:]))
    report = tr.run_pass(media, srts, fake.factory, log=lambda s: None)
    assert not report.stopped and len(fake.calls) == 5 and len(report.errors) == 4


def test_pass_interrupt(tmp_path):
    cfg, course, d, media, srts = setup(tmp_path, ["01.mp4", "02.mp4"])

    def factory():
        def t(m):
            raise KeyboardInterrupt

        return t

    report = tr.run_pass(media, srts, factory, log=lambda s: None)
    assert report.interrupted and not any(p.exists() for p in srts.values())


def test_build_units_index_and_notes_kept(tmp_path):
    names = ["01 Intro.mp4", "02 Long.mp4", "03 Silent.mp4", "04 Todo.mp4"]
    cfg, course, d, media, srts = setup(tmp_path, names)
    write_srt(cues_for(media[0]), srts[media[0]])
    write_srt([Cue(i * 30.0, i * 30 + 5, "word " * 30) for i in range(8)], srts[media[1]])  # 240 words
    write_srt([], srts[media[2]])
    (d / "units" / "ch09-stale.md").write_text("old", encoding="utf-8")
    (d / "notes" / "ch01.md").write_text("my note", encoding="utf-8")

    rows = tr.build_units(media, srts, d, "CRS1", "Course", course, cfg.min_words, cfg.max_words)
    units = sorted(p.name for p in (d / "units").glob("*.md"))
    assert "ch09-stale.md" not in units
    assert units[0] == "ch01-01-intro.md"
    assert [r["unit"] for r in rows][:1] == ["ch01"]
    assert all(r["unit"].startswith("ch02") and len(r["unit"]) == 5 for r in rows[1:])  # ch02a, ch02b...
    assert len(rows) >= 3
    text = (d / "units" / "ch01-01-intro.md").read_text(encoding="utf-8")
    assert "[00:00:00]" in text and "`CRS1 ch01 [HH:MM:SS]`" in text
    assert (d / "notes" / "ch01.md").read_text(encoding="utf-8") == "my note"

    index = (d / "INDEX.md").read_text(encoding="utf-8")
    assert "| Unit | Content | Duration | Words | Text | Note |" in index
    assert "No speech" in index and "ch03 `03 Silent.mp4`" in index
    assert "Not transcribed yet: 1 media" in index
    done, total, pending = index_status(d)
    assert done == 1 and total == len(rows) and "ch01" not in pending


def test_cli_index_only(tmp_path, monkeypatch):
    cfg = make_library(tmp_path)
    course = make_course(tmp_path, ["a.mp3", "b.mp3"])
    write_srt(cues_for(course / "a.mp3"), course / "a.srt")
    rc = main(["--library", str(cfg.root), "transcribe", "POD1", str(course), "--index-only"])
    assert rc == 0
    d = cfg.root / "sources" / "POD1"
    assert (d / "units" / "ch01-a.md").exists()
    assert (d / "original" / "course").is_symlink()


def test_cli_full_pass_with_fake_whisper(tmp_path, monkeypatch, capsys):
    from assara import whisper

    cfg = make_library(tmp_path)
    course = make_course(tmp_path, ["a.mp3", "b.mp3", "c.mp3"])
    fake = FakeTranscriber(fail={"b.mp3"})
    monkeypatch.setattr(whisper, "make_transcriber", lambda *a, **k: fake.factory())
    rc = main(["--library", str(cfg.root), "transcribe", "POD1", str(course)])
    out = capsys.readouterr().out
    assert rc == 1  # one error
    assert "nohup nice -n 19" in out and "1 error(s)" in out
    d = cfg.root / "sources" / "POD1"
    assert sorted(p.name for p in (d / "raw").glob("*.srt")) == ["a-mp3.srt", "c-mp3.srt"]
    assert not list(course.glob("*.srt"))  # never written next to the original


def test_missing_path(tmp_path):
    cfg = make_library(tmp_path)
    with pytest.raises(SystemExit):
        main(["--library", str(cfg.root), "transcribe", "POD1", str(tmp_path / "nope")])


def test_long_pass_hint_quotes_the_path(tmp_path, monkeypatch, capsys):
    import re
    import shlex

    from assara import whisper

    cfg = make_library(tmp_path)
    course = tmp_path / "it's; touch PWNED"
    for n in ("a.mp3", "b.mp3", "c.mp3"):
        course.mkdir(exist_ok=True)
        (course / n).write_bytes(b"not really audio")
    fake = FakeTranscriber()
    monkeypatch.setattr(whisper, "make_transcriber", lambda *a, **k: fake.factory())
    main(["--library", str(cfg.root), "transcribe", "POD2", str(course)])
    hint = re.search(r"`nohup (.+?) > transcribe\.log", capsys.readouterr().out).group(1)
    assert shlex.split(hint) == ["nice", "-n", "19", "assara", "transcribe", "POD2", str(course)]
