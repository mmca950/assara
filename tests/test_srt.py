from assara.srt import (
    Cue,
    clean_text,
    dedupe_rolling,
    format_srt,
    looks_like_srt,
    paragraphs,
    parse_srt,
    read_srt,
    split_parts,
    stamped,
    timestamp,
    write_srt,
)

SAMPLE = """﻿1
00:00:01,000 --> 00:00:03,500
<i>Hello</i> and welcome.

2
00:00:04,000 --> 00:00:06,000
{\\an8}This is
the first lesson.

3
00:00:07,000 --> 00:00:08,000


not a cue at all

00:01:10.250 --> 00:01:12.000
No number, dot separator.
"""


def test_parse_srt_cleans_and_skips_bad_blocks():
    cues = parse_srt(SAMPLE)
    assert [c.text for c in cues] == [
        "Hello and welcome.",
        "This is the first lesson.",
        "No number, dot separator.",
    ]
    assert cues[0].start == 1.0 and cues[0].end == 3.5
    assert cues[2].start == 70.25


def test_parse_srt_crlf():
    text = "1\r\n00:00:01,000 --> 00:00:02,000\r\nOne\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\nTwo\r\n"
    assert [c.text for c in parse_srt(text)] == ["One", "Two"]


def test_timestamp_and_round_trip(tmp_path):
    assert timestamp(3661.5) == "01:01:01,500"
    assert timestamp(-1) == "00:00:00,000"
    cues = [Cue(0.0, 1.25, "a b"), Cue(3600.0, 3601.0, "c")]
    path = write_srt(cues, tmp_path / "raw" / "x.srt")
    assert not (tmp_path / "raw" / "x.srt.part").exists()
    assert read_srt(path) == cues
    assert format_srt(cues).startswith("1\n00:00:00,000 --> 00:00:01,250\na b\n")
    assert looks_like_srt(path)


def test_empty_srt_records_silence(tmp_path):
    path = write_srt([], tmp_path / "silent.srt")
    assert path.exists() and read_srt(path) == []


def test_looks_like_srt_false(tmp_path):
    f = tmp_path / "notes"
    f.write_text("just text", encoding="utf-8")
    assert not looks_like_srt(f)


def test_clean_text():
    assert clean_text('<font color="red">a</font>   b\n c') == "a b c"


def test_dedupe_rolling():
    cues = [Cue(0, 1, "we buy"), Cue(1, 2, "we buy"), Cue(2, 3, "we buy the stock"), Cue(3, 4, "today")]
    assert [c.text for c in dedupe_rolling(cues)] == ["we buy", "the stock", "today"]


def test_paragraphs_by_time_and_words():
    cues = [Cue(t, t + 1, "word " * 10) for t in range(0, 130, 10)]
    paras = paragraphs(cues, seconds=60, max_words=1000)
    assert [p[0] for p in paras] == [0, 60, 120]
    paras = paragraphs(cues, seconds=1000, max_words=30)
    assert all(len(text.split()) <= 30 for _, text in paras)
    assert stamped([(3725, "hi")]) == ["[01:02:05] hi"]


def test_split_parts():
    paras = [f"[00:00:{i:02d}] " + "w " * 99 for i in range(10)]  # 100 words each
    assert split_parts(paras, max_words=1000, target_words=400) == [paras]
    parts = split_parts(paras, max_words=500, target_words=400)
    assert len(parts) == 3
    assert sum(parts, []) == paras
    assert all(parts)


def test_parse_srt_drops_control_characters():
    cues = parse_srt("1\n00:00:01,000 --> 00:00:02,000\nhi\x1b]0;x\x07 there\n")
    assert [c.text for c in cues] == ["hi ]0;x there"]
