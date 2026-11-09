"""Tests of assara.links and `assara link` (no network: requests and yt-dlp are monkeypatched)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from assara import links
from assara.config import Config
from assara.library import AssaraError


def make_library(tmp_path, max_words=17000, min_words=10000):
    (tmp_path / "assara.toml").write_text(
        f"[units]\nmin_words = {min_words}\nmax_words = {max_words}\n", encoding="utf-8"
    )
    (tmp_path / "sources").mkdir()
    return Config.load(tmp_path)


# ---------------------------------------------------------------- mode detection


@pytest.mark.parametrize(
    "url, mode",
    [
        ("https://www.youtube.com/watch?v=abc123", "youtube"),
        ("https://youtu.be/abc123", "youtube"),
        ("https://m.youtube.com/watch?v=abc123", "youtube"),
        ("https://www.instagram.com/p/AbC_123/", "instagram"),
        ("https://instagram.com/reel/XyZ/", "instagram"),
        ("https://example.org/article", "web"),
        ("https://notyoutube.com/watch?v=1", "web"),
        ("https://example.org/?ref=youtube.com/", "web"),
        ("https://attacker.example?.youtube.com", "web"),
        ("https://attacker.example#.youtube.com", "web"),
        ("https://attacker.example\\.youtube.com/watch?v=1", "web"),
        ("https://user@attacker.example/.youtube.com", "web"),
        ("https://www.YouTube.com:443/watch?v=abc", "youtube"),
        ("youtube.com/watch?v=abc", "youtube"),
        ("www.youtube.com/watch?v=abc&next=https://example.org/", "youtube"),
        ("instagram.com/p/AbC/?u=http://example.org", "instagram"),
        ("https://[::1/", "web"),
    ],
)
def test_detect_mode(url, mode):
    assert links.detect_mode(url) == mode


@pytest.mark.parametrize(
    "url, refused",
    [
        ("https://www.youtube.com/playlist?list=PL123", True),
        ("https://www.youtube.com/@somechannel", True),
        ("https://www.youtube.com/channel/UC123", True),
        ("https://www.youtube.com/c/name/videos", True),
        ("https://www.youtube.com/watch?v=abc&list=PL123", False),
        ("https://youtu.be/abc", False),
        ("https://www.youtube.com/shorts/abc", False),
    ],
)
def test_youtube_collection(url, refused):
    assert links.is_youtube_collection(url) is refused


def test_playlist_refused_before_any_network(tmp_path, monkeypatch):
    cfg = make_library(tmp_path)

    def boom(*a, **k):
        raise AssertionError("yt-dlp must not be called")

    monkeypatch.setattr(links, "run_ytdlp", boom)
    with pytest.raises(AssaraError, match="one by one"):
        links.add_youtube(cfg, "https://www.youtube.com/playlist?list=PL1", "VID1", None, "")
    assert not (tmp_path / "sources" / "VID1").exists()


def test_playlist_detected_from_metadata(tmp_path, monkeypatch):
    cfg = make_library(tmp_path)
    monkeypatch.setattr(links, "video_info", lambda url: {"_type": "playlist", "entries": []})
    with pytest.raises(AssaraError, match="playlist"):
        links.add_youtube(cfg, "https://youtu.be/x", "VID1", None, "")


def test_instagram_shortcode():
    assert links.instagram_shortcode("https://www.instagram.com/someone/p/AbC_-1/?img=1") == "AbC_-1"
    assert links.instagram_shortcode("https://www.instagram.com/reel/XyZ9/") == "XyZ9"
    with pytest.raises(AssaraError):
        links.instagram_shortcode("https://www.instagram.com/someone/")


# ---------------------------------------------------------------- subtitle choice


def test_choose_language_prefers_original_track():
    assert links.choose_language({"en": 1, "en-orig": 1, "fr": 1}, ["en"]) == "en-orig"
    assert links.choose_language({"en-US": 1, "fr": 1}, ["en"]) == "en-US"
    assert links.choose_language({"de": 1}, ["en"]) == "de"
    assert links.choose_language({"de": 1}, ["en"], any_fallback=False) is None
    assert links.choose_language({}, ["en"]) is None


def test_pick_subtitles_manual_first():
    info = {"language": "fr", "subtitles": {"en": [], "fr": []}, "automatic_captions": {"fr": []}}
    assert links.pick_subtitles(info, "", ["en"]) == ("manual", "fr")
    assert links.pick_subtitles(info, "en", ["en"]) == ("manual", "en")


def test_pick_subtitles_any_manual_rather_than_auto():
    info = {"language": "en", "subtitles": {"de": []}, "automatic_captions": {"en": []}}
    assert links.pick_subtitles(info, "", ["en"]) == ("manual", "de")


def test_pick_subtitles_auto_only_in_spoken_language():
    info = {
        "language": "en-US",
        "subtitles": {"live_chat": []},
        "automatic_captions": {"fr": [], "en-orig": [], "en": []},
    }
    assert links.pick_subtitles(info, "", ["fr"]) == ("auto", "en-orig")
    # spoken language missing from automatic captions: no machine translation, Whisper instead
    info = {"language": "ar", "automatic_captions": {"en": [], "fr": []}}
    assert links.pick_subtitles(info, "", ["en"]) is None


def test_pick_subtitles_unknown_language_uses_config():
    info = {"automatic_captions": {"es": [], "en": []}}
    assert links.pick_subtitles(info, "", ["en"]) == ("auto", "en")
    assert links.pick_subtitles({}, "", ["en"]) is None


# ---------------------------------------------------------------- SRT and automatic captions


def test_clean_auto_captions_rolling_duplicates():
    cues = [
        (0, "hello and welcome"),
        (2, "hello and welcome"),
        (2, "hello and welcome to the course"),
        (4, "to the course"),
        (5, "today we look at"),
        (7, "today we look at"),
    ]
    assert links.clean_auto_captions(cues) == [
        (0, "hello and welcome"),
        (2, "to the course"),
        (5, "today we look at"),
    ]


def test_read_srt_and_paragraphs(tmp_path):
    srt = tmp_path / "v.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\n<i>First</i> line\n\n"
        "2\n00:00:30,500 --> 00:00:32,000\nsecond\nline\n\n"
        "3\n00:01:05,000 --> 00:01:07,000\n{\\an8}third\n",
        encoding="utf-8",
    )
    cues = links.read_srt(srt)
    assert cues == [(1, "First line"), (30, "second line"), (65, "third")]
    assert links.paragraphs(cues) == [(1, "First line second line"), (65, "third")]


def test_split_parts():
    paras = [" ".join(["w"] * 100)] * 30  # 3000 words
    assert links.split_parts(paras, 5000) == [paras]
    parts = links.split_parts(paras, 1000)
    assert len(parts) >= 3
    assert sum(len(p) for p in parts) == 30
    assert all(sum(len(x.split()) for x in p) <= 1100 for p in parts)


# ---------------------------------------------------------------- YouTube end to end (mocked)


def test_add_youtube_with_auto_captions(tmp_path, monkeypatch):
    cfg = make_library(tmp_path)
    info = {
        "id": "abc",
        "title": "A Talk",
        "channel": "Some Channel",
        "upload_date": "20240102",
        "duration": 75,
        "language": "en",
        "webpage_url": "https://www.youtube.com/watch?v=abc",
        "automatic_captions": {"en": []},
    }
    monkeypatch.setattr(links, "video_info", lambda url: info)

    def fake_download(url, dest, kind, lang):
        assert (kind, lang) == ("auto", "en")
        dest.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nhello there\n\n"
            "2\n00:00:02,000 --> 00:00:03,000\nhello there\n\n"
            "3\n00:01:10,000 --> 00:01:11,000\ngeneral idea\n",
            encoding="utf-8",
        )
        return dest

    monkeypatch.setattr(links, "download_subtitles", fake_download)
    d = links.add_youtube(cfg, "https://youtu.be/abc", "TALK1", None, "")
    units = list((d / "units").glob("ch01-*.md"))
    assert len(units) == 1
    text = units[0].read_text(encoding="utf-8")
    assert "[00:00:01] hello there" in text and text.count("hello there") == 1
    assert "[00:01:10] general idea" in text
    assert "automatic subtitles" in text
    index = (d / "INDEX.md").read_text(encoding="utf-8")
    assert "`notes/ch01.md` (pending)" in index
    assert "TALK1 ch01 [HH:MM:SS]" in index


def test_whisper_missing_gives_clear_error(tmp_path, monkeypatch):
    import sys

    import assara

    monkeypatch.setitem(sys.modules, "assara.whisper", None)  # makes the import fail
    monkeypatch.delattr(assara, "whisper", raising=False)
    cfg = make_library(tmp_path)
    with pytest.raises(AssaraError, match="audio"):
        links.whisper_to_srt(cfg, tmp_path / "a.m4a", tmp_path / "a.srt", "")


# ---------------------------------------------------------------- web pages


HTML = """<html><head><title>Spaced Repetition Explained</title><script>var x = 1;</script></head>
<body><nav><a href="/">Home</a> <a href="/about">About</a></nav>
<header>Site banner</header>
<article><h1>Spaced repetition</h1>
<p>Reviewing material at <b>growing intervals</b> helps memory.</p>
<ul><li>First review after one day</li><li>Then after three days</li></ul>
<blockquote>Forgetting is part of learning.</blockquote></article>
<aside>Related posts</aside><footer>Copyright notice</footer></body></html>"""


def test_extract_main_text():
    title, text = links.extract_main_text(HTML)
    assert title == "Spaced Repetition Explained"
    assert "# Spaced repetition" in text
    assert "Reviewing material at growing intervals helps memory." in text
    assert "- First review after one day" in text
    assert "> Forgetting is part of learning." in text
    for noise in ("Home", "Site banner", "Related posts", "Copyright", "var x"):
        assert noise not in text


def test_extract_main_text_without_article():
    title, text = links.extract_main_text("<html><body><div>Just a <span>div</span> page</div></body></html>")
    assert title == ""
    assert text == "Just a div page"


def test_access_problem():
    assert links.access_problem(403, "").startswith("HTTP 403")
    assert links.access_problem(200, "").startswith("empty page")
    assert "login wall" in links.access_problem(200, "Please sign in to continue", '<input type="password">')
    assert links.access_problem(200, " ".join(["word"] * 60)) == ""


class FakeResponse:
    def __init__(self, text, status=200, ctype="text/html; charset=utf-8", url=""):
        self.text, self.status_code, self.url = text, status, url
        self.headers = {"content-type": ctype}


def test_add_web_and_inaccessible_page(tmp_path, monkeypatch):
    cfg = make_library(tmp_path)
    long_html = HTML.replace("helps memory.", "helps memory. " + "More words here. " * 30)
    pages = {
        "https://example.org/a": FakeResponse(long_html, url="https://example.org/a"),
        "https://example.org/private": FakeResponse("<html><body>Sign in</body></html>", 403),
    }
    monkeypatch.setattr(links, "http_get", lambda url, **k: pages[url])
    links.add_web(cfg, "https://example.org/a", "WEB1", None)
    links.add_web(cfg, "https://example.org/private", "WEB1", None)
    links.add_web(cfg, "https://example.org/a", "WEB1", None)  # already there: skipped
    d = tmp_path / "sources" / "WEB1"
    units = sorted(p.name for p in (d / "units").iterdir())
    assert len(units) == 1 and units[0].startswith("w01-")
    unit = (d / "units" / units[0]).read_text(encoding="utf-8")
    assert "URL: https://example.org/a; retrieved " in unit
    index = (d / "INDEX.md").read_text(encoding="utf-8")
    assert "`notes/w01.md` (pending)" in index
    assert "w02: https://example.org/private (HTTP 403" in index
    assert "notes/w02.md" not in index  # inaccessible: no note expected


# ---------------------------------------------------------------- link lists


def test_parse_link_list():
    text = """# my reading list
Good intro: https://example.org/intro.
(see https://example.org/b?x=1) and https://example.org/intro again
not a link: www.example.org
https://www.youtube.com/watch?v=abc
"""
    assert links.parse_link_list(text) == [
        "https://example.org/intro",
        "https://example.org/b?x=1",
        "https://www.youtube.com/watch?v=abc",
    ]


def test_add_link_file(tmp_path, monkeypatch):
    cfg = make_library(tmp_path)
    body = "<html><head><title>T</title></head><body><main><p>" + "text " * 80 + "</p></main></body></html>"
    calls = []

    def fake_get(url, **k):
        calls.append(url)
        return FakeResponse(body, url=url)

    monkeypatch.setattr(links, "http_get", fake_get)
    lst = tmp_path / "reading.txt"
    lst.write_text("https://example.org/1\nhttps://example.org/2\nhttps://youtu.be/xyz\n", encoding="utf-8")
    links.add_link_file(cfg, lst, "LST1", "Reading list")
    d = tmp_path / "sources" / "LST1"
    assert calls == ["https://example.org/1", "https://example.org/2"]
    assert (d / "raw" / "links-reading.txt").exists()
    index = (d / "INDEX.md").read_text(encoding="utf-8")
    assert index.startswith("# LST1: Reading list (index)")
    assert "`notes/w01.md` (pending)" in index and "`notes/w02.md` (pending)" in index
    assert "Link files kept in `raw/`" in index


# ---------------------------------------------------------------- command line


def test_cli_info_writes_nothing(tmp_path, monkeypatch, capsys):
    from assara.commands import link as link_cmd

    cfg = make_library(tmp_path)
    monkeypatch.setattr(links, "http_get", lambda url, **k: FakeResponse(HTML))
    args = SimpleNamespace(
        url="https://example.org/a", file=None, code=None, title=None, language="", info=True
    )
    assert link_cmd.run(args, cfg) == 0
    out = capsys.readouterr().out
    assert "mode web" in out
    assert list((tmp_path / "sources").iterdir()) == []


def test_cli_help_has_rights_notice():
    import argparse

    from assara.commands import link as link_cmd

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    link_cmd.configure(sub)
    help_text = sub.choices["link"].format_help()
    assert "responsible for having the right" in help_text


def test_youtube_falls_back_to_whisper(tmp_path, monkeypatch):
    from assara import whisper
    from assara.srt import Cue

    cfg = make_library(tmp_path)
    info = {"title": "No Subs", "duration": 5, "language": "ar", "automatic_captions": {"en": []}}
    monkeypatch.setattr(links, "video_info", lambda url: info)
    monkeypatch.setattr(links, "download_subtitles", lambda *a: pytest.fail("no subtitle should be tried"))

    def fake_audio(url, stem):
        media = stem.with_suffix(".m4a")
        media.write_bytes(b"x")
        return media, ""

    monkeypatch.setattr(links, "download_audio", fake_audio)
    monkeypatch.setattr(links, "_TRANSCRIBERS", {})
    monkeypatch.setattr(whisper, "make_transcriber", lambda *a: lambda media: [Cue(3.0, 4.0, "marhaba")])
    d = links.add_youtube(cfg, "https://youtu.be/q", "NOSUB", None, "")
    assert (d / "raw" / "video.srt").exists()
    text = next((d / "units").glob("ch01-*.md")).read_text(encoding="utf-8")
    assert "[00:00:03] marhaba" in text and "Whisper (small, cpu)" in text


# ---------------------------------------------------------------- text from outside


ESC, BEL = "\x1b", "\x07"
OSC52 = ESC + "]52;c;ZWNobyBoaQ==" + BEL


def test_clean_text_breaks_terminal_sequences_without_gluing_words():
    from assara.library import clean_text

    assert clean_text("Title" + OSC52) == "Title ]52;c;ZWNobyBoaQ== "
    assert clean_text("alpha\x0cbeta\x0bgamma\x85delta\x1fend") == "alpha beta gamma delta end"
    assert clean_text("line one\r\nline two\rthree") == "line one\nline two three"
    assert clean_text("tab\tand\nnewline kept") == "tab\tand\nnewline kept"
    assert clean_text("lone \udc9b surrogate") == "lone \ufffd surrogate"
    assert (
        clean_text("caf\u00e9 \u0645\u0631\u062d\u0628\u0627") == "caf\u00e9 \u0645\u0631\u062d\u0628\u0627"
    )


def test_terminal_safe():
    from assara.library import terminal_safe

    assert terminal_safe("a" + OSC52 + "\n\tb\udc9b") == "a?]52;c;ZWNobyBoaQ==?\n\tb?"


def test_clean_data_cleans_nested_strings_and_keys():
    data = {"title": "T" + ESC, "subtitles": {"en" + ESC + "[2J": [{"url": "u" + BEL}]}, "duration": 5}
    assert links.clean_data(data) == {"title": "T ", "subtitles": {"en [2J": [{"url": "u "}]}, "duration": 5}


def test_hostile_page_text_is_cleaned_and_framed(tmp_path, monkeypatch):
    cfg = make_library(tmp_path)
    html = (
        "<html><head><title>Evil\ntitle"
        + OSC52
        + "</title></head><body><main><p>"
        + "word " * 60
        + "alpha\x0cbeta"
        + ESC
        + "[2Jgamma</p></main></body></html>"
    )
    monkeypatch.setattr(links, "http_get", lambda url, **k: FakeResponse(html, url="https://example.org/e"))
    links.add_web(cfg, "https://example.org/e", "EVIL1", None)
    d = tmp_path / "sources" / "EVIL1"
    files = [*d.rglob("*.md"), *d.rglob("*.json")]
    for f in files:
        content = f.read_text(encoding="utf-8")
        assert ESC not in content and BEL not in content, f
    unit = next((d / "units").glob("w01-*.md")).read_text(encoding="utf-8")
    first, rest = unit.split("\n", 1)
    assert first.startswith("# EVIL1 w01: Evil title ") and "52;c;" in first
    assert links.THIRD_PARTY in unit
    assert "alpha beta [2Jgamma" in unit  # spaces, not glued words


def test_inaccessible_page_error_is_cleaned(tmp_path, monkeypatch):
    cfg = make_library(tmp_path)
    ctype = "application/x-evil" + ESC + "[2J" + BEL + "; charset=x"
    monkeypatch.setattr(links, "http_get", lambda url, **k: FakeResponse("", ctype=ctype, url=url))
    links.add_web(cfg, "https://example.org/bin", "EVIL2", None)
    index = (tmp_path / "sources" / "EVIL2" / "INDEX.md").read_text(encoding="utf-8")
    assert "not a web page (application/x-evil [2j )" in index
    assert ESC not in index and BEL not in index


def test_youtube_metadata_and_captions_are_cleaned(tmp_path, monkeypatch):
    cfg = make_library(tmp_path)
    raw_json = (
        '{"id": "abc", "title": "Talk\\u001b]0;x\\u0007\\nsecond line", "channel": "Chan\\nnel", '
        '"duration": 5, "language": "en", "webpage_url": "https://www.youtube.com/watch?v=abc", '
        '"subtitles": {"en\\u001b[2J": [{"ext": "srt"}]}}'
    )
    monkeypatch.setattr(links, "run_ytdlp", lambda args: SimpleNamespace(stdout=raw_json, stderr=""))

    def fake_download(url, dest, kind, lang):
        dest.write_text("1\n00:00:01,000 --> 00:00:02,000\nhi" + OSC52 + " there\n", encoding="utf-8")
        return dest

    monkeypatch.setattr(links, "download_subtitles", fake_download)
    info = links.video_info("https://youtu.be/abc")
    assert "\x1b" not in links.describe_video(info, cfg, "")
    d = links.add_youtube(cfg, "https://youtu.be/abc", "TALK2", None, "")
    for f in [*d.rglob("*.md"), *d.rglob("*.json")]:
        assert ESC not in f.read_text(encoding="utf-8"), f
    unit = next((d / "units").glob("ch01-*.md")).read_text(encoding="utf-8")
    assert unit.startswith("# TALK2 ch01: Talk ]0;x  second line\n\nURL: ")
    assert "channel Chan nel;" in unit and links.THIRD_PARTY in unit
    assert "[00:00:01] hi ]52;c;ZWNobyBoaQ== there" in unit


def test_cli_output_shows_control_characters_as_question_marks(tmp_path, capsys):
    from assara.cli import main

    make_library(tmp_path)
    lst = tmp_path / "links.txt"
    lst.write_text("https://example.org/a" + OSC52 + "\n", encoding="utf-8")
    assert main(["--library", str(tmp_path), "link", "--file", str(lst), "--info"]) == 0
    out = capsys.readouterr().out
    assert ESC not in out and BEL not in out
    assert "https://example.org/a?]52;c;ZWNobyBoaQ==?" in out


def test_cli_error_message_is_made_terminal_safe(tmp_path, monkeypatch):
    from assara import cli

    make_library(tmp_path)

    def hostile(*a, **k):
        raise AssaraError("Unreadable link: " + OSC52)

    monkeypatch.setattr(links, "video_info", hostile)
    with pytest.raises(AssaraError) as err:
        cli.main(["--library", str(tmp_path), "link", "https://youtu.be/abc", "--code", "TALK3"])
    assert str(err.value) == "Unreadable link: ?]52;c;ZWNobyBoaQ==?"


def test_cli_info_frames_the_preview(tmp_path, monkeypatch, capsys):
    from assara.commands import link as link_cmd

    cfg = make_library(tmp_path)
    long_html = HTML.replace("helps memory.", "helps memory. " + "More words here. " * 30)
    monkeypatch.setattr(links, "http_get", lambda url, **k: FakeResponse(long_html))
    args = SimpleNamespace(
        url="https://example.org/a", file=None, code=None, title=None, language="", info=True
    )
    link_cmd.run(args, cfg)
    assert links.THIRD_PARTY_PREVIEW in capsys.readouterr().out


# ---------------------------------------------------------------- local and private addresses


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost:8080/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0/",
        "file:///etc/passwd",
        "ftp://93.184.215.14/",
    ],
)
def test_check_address_refuses_local_and_private(url):
    with pytest.raises(links.RefusedAddress):
        links.check_address(url)


def test_check_address_accepts_public_and_allowed_private():
    links.check_address("https://93.184.215.14/page")
    links.check_address("http://192.168.1.1/", allow_private=True)
    with pytest.raises(links.RefusedAddress):
        links.check_address("file:///etc/passwd", allow_private=True)


def fake_web(monkeypatch, routes):
    """Serve `routes` {url: (status, headers, body)} through the real requests, without a network.

    Returns the list of (url, Cookie header) of the requests sent.
    """
    import http.client
    import io

    import requests
    from requests.structures import CaseInsensitiveDict

    calls = []

    class Raw(io.BytesIO):
        def __init__(self, body, headers):
            super().__init__(body)
            lines = "".join(f"{k}: {v}\r\n" for k, v in headers.items()) + "\r\n"
            self._original_response = SimpleNamespace(
                msg=http.client.parse_headers(io.BytesIO(lines.encode("latin-1")))
            )

    def send(self, request, **kw):
        calls.append((request.url, request.headers.get("Cookie")))
        status, headers, body = routes[request.url]
        r = requests.Response()
        r.status_code, r.headers, r.url, r.request = (
            status,
            CaseInsensitiveDict(headers),
            request.url,
            request,
        )
        r.raw = Raw(body, headers)
        requests.cookies.extract_cookies_to_jar(r.cookies, request, r.raw)
        return r

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", send)
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    ):
        monkeypatch.delenv(name, raising=False)
    return calls


def redirect(location, **headers):
    return (302, {"Location": location, **headers}, b"")


PAGE = (200, {"Content-Type": "text/html"}, b"<html></html>")


def test_redirect_to_private_address_is_refused(tmp_path, monkeypatch):
    cfg = make_library(tmp_path)
    calls = fake_web(monkeypatch, {"http://93.184.215.14/a": redirect("http://127.0.0.1/secret")})
    links.add_web(cfg, "http://93.184.215.14/a", "WEB9", None)
    assert [u for u, _ in calls] == ["http://93.184.215.14/a"]  # the private address is never requested
    index = (tmp_path / "sources" / "WEB9" / "INDEX.md").read_text(encoding="utf-8")
    assert "refused: 127.0.0.1 is a local or private address" in index


def test_public_redirect_is_followed(monkeypatch):
    calls = fake_web(monkeypatch, {"http://93.184.215.14/a": redirect("/b"), "http://93.184.215.14/b": PAGE})
    r = links.http_get("http://93.184.215.14/a")
    assert r.status_code == 200 and r.url == "http://93.184.215.14/b"
    assert [u for u, _ in calls] == ["http://93.184.215.14/a", "http://93.184.215.14/b"]


def test_cookie_set_by_a_redirect_is_sent_on_the_next_hop(monkeypatch):
    routes = {
        "http://93.184.215.14/a": redirect("/b", **{"Set-Cookie": "consent=yes; Path=/"}),
        "http://93.184.215.14/b": PAGE,
    }
    calls = fake_web(monkeypatch, routes)
    assert links.http_get("http://93.184.215.14/a").status_code == 200
    assert calls[1] == ("http://93.184.215.14/b", "consent=yes")


def test_utf8_redirect_target_is_decoded_like_requests(monkeypatch):
    raw_utf8 = "/café/مقال".encode().decode("latin-1")  # how http.client hands raw UTF-8 bytes over
    target = "http://93.184.215.14/caf%C3%A9/%D9%85%D9%82%D8%A7%D9%84"
    calls = fake_web(monkeypatch, {"http://93.184.215.14/a": redirect(raw_utf8), target: PAGE})
    assert links.http_get("http://93.184.215.14/a").status_code == 200
    assert calls[-1][0] == target


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1\\@93.184.215.14/", "http://169.254.169.254\\@ 93.184.215.14/x"],
)
def test_backslash_host_confusion_is_refused(monkeypatch, url):
    calls = fake_web(monkeypatch, {})
    with pytest.raises(links.RefusedAddress):
        links.http_get(url)
    assert calls == []


def test_backslash_in_a_redirect_is_refused(monkeypatch):
    calls = fake_web(
        monkeypatch, {"http://93.184.215.14/a": redirect("http://169.254.169.254\\@93.184.215.14/")}
    )
    with pytest.raises(links.RefusedAddress, match="169.254.169.254"):
        links.http_get("http://93.184.215.14/a")
    assert len(calls) == 1


def no_dns(monkeypatch):
    import socket

    def fail(host, *a, **k):
        if host.replace(".", "").isdigit():
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (host, 80))]
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(links.socket, "getaddrinfo", fail)


def test_unresolvable_host_without_proxy_is_unreachable(monkeypatch):
    fake_web(monkeypatch, {})
    no_dns(monkeypatch)
    with pytest.raises(links.RefusedAddress, match="allow_private_addresses"):
        links.http_get("https://example.org/article")


def test_unresolvable_host_through_a_proxy_is_refused(monkeypatch):
    # The proxy could resolve an internal name (intranet, metadata service): never let it through.
    calls = fake_web(monkeypatch, {"http://intranet/": PAGE})
    no_dns(monkeypatch)
    monkeypatch.setenv("HTTP_PROXY", "http://93.184.215.14:3128")
    with pytest.raises(links.RefusedAddress, match="allow_private_addresses"):
        links.http_get("http://intranet/")
    assert calls == []


def test_allow_private_addresses_skips_the_lookup(monkeypatch):
    calls = fake_web(monkeypatch, {"https://example.org/article": PAGE, "http://[fe80::1%25eth0]/": PAGE})
    no_dns(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://93.184.215.14:3128")
    assert links.http_get("https://example.org/article", allow_private=True).status_code == 200
    assert links.http_get("http://[fe80::1%25eth0]/", allow_private=True).status_code == 200  # IPv6 zone
    assert len(calls) == 2


def test_session_is_closed(monkeypatch):
    import requests

    closed = []
    real_close = requests.Session.close
    monkeypatch.setattr(requests.Session, "close", lambda self: closed.append(1) or real_close(self))
    fake_web(
        monkeypatch, {"http://93.184.215.14/a": PAGE, "http://93.184.215.14/b": redirect("http://127.0.0.1/")}
    )
    links.http_get("http://93.184.215.14/a")
    assert closed == [1]
    r = links.http_get("http://93.184.215.14/a", stream=True)
    assert closed == [1]  # a streamed body is still to read
    r.close()
    assert closed == [1, 1]
    with pytest.raises(links.RefusedAddress):
        links.http_get("http://93.184.215.14/b")
    assert closed == [1, 1, 1]


def test_download_reads_a_streamed_body(tmp_path, monkeypatch):
    fake_web(monkeypatch, {"http://93.184.215.14/m.jpg": (200, {}, b"JPEGDATA")})
    dest = tmp_path / "m.jpg"
    assert links.download("http://93.184.215.14/m.jpg", dest)
    assert dest.read_bytes() == b"JPEGDATA"


def test_too_many_redirects(monkeypatch):
    fake_web(monkeypatch, {"http://93.184.215.14/a": redirect("/a")})
    with pytest.raises(links.RefusedAddress, match="more than"):
        links.http_get("http://93.184.215.14/a")


def test_allow_private_addresses_setting(tmp_path):
    from assara.config import Config

    assert make_library(tmp_path).allow_private_addresses is False
    (tmp_path / "assara.toml").write_text("[links]\nallow_private_addresses = true\n", encoding="utf-8")
    assert Config.load(tmp_path).allow_private_addresses is True


def test_unexpected_traceback_is_terminal_safe(monkeypatch):
    import io
    import sys

    from assara.cli import safe_excepthook

    err = io.StringIO()
    monkeypatch.setattr(sys, "__stderr__", err)
    try:
        raise ValueError("bad " + OSC52)
    except ValueError as e:
        safe_excepthook(type(e), e, e.__traceback__)
    assert "ValueError: bad ?]52;c;ZWNobyBoaQ==?" in err.getvalue()
    assert ESC not in err.getvalue()


def test_streams_closed_at_start_stay_none(monkeypatch):
    import sys

    from assara import cli

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(cli, "run", lambda argv: print("progress") or 0)
    assert cli.main([]) == 0
    assert sys.stdout is None


def test_raw_output_unwraps_the_safe_streams(monkeypatch):
    import io
    import sys

    from assara.library import SafeStream, raw_output

    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", SafeStream(out))
    monkeypatch.setattr(sys, "stderr", SafeStream(err))
    with raw_output():
        sys.stderr.write("\r 50%")
    monkeypatch.setattr(sys, "stderr", SafeStream(SafeStream(err)))  # main() run inside main()
    with raw_output():
        sys.stderr.write("\r 50%")
    monkeypatch.setattr(sys, "stderr", SafeStream(err))
    sys.stderr.write("\r" + ESC)
    assert err.getvalue() == "\r 50%\r 50%??"
    assert isinstance(sys.stdout, SafeStream) and sys.stdout.raw_stream is out


def test_links_and_transcribe_read_srt_alike(tmp_path):
    from assara import srt

    path = tmp_path / "v.srt"
    path.write_text("00:1:05,000 --> 00:1:07,000\n<i>one</i> digit minutes\n", encoding="utf-8")
    assert links.read_srt(path) == [(65, "one digit minutes")]
    assert [(int(c.start), c.text) for c in srt.read_srt(path)] == links.read_srt(path)


# ---------------------------------------------------------------- the connection check (DNS rebinding)


@pytest.fixture
def local_server(monkeypatch):
    """A tiny HTTP server on 127.0.0.1 (port chosen by the system); yields (port, requested paths)."""
    import http.server
    import threading

    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            body = b"<html>local</html>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    yield server.server_address[1], seen
    server.shutdown()
    server.server_close()


def rebinding_dns(monkeypatch):
    """`rebind.test` resolves to a public address the first time, then to 127.0.0.1."""
    import socket

    real = socket.getaddrinfo
    answers = iter(["93.184.215.14"])

    def getaddrinfo(host, port, *a, **k):
        if host != "rebind.test":
            return real(host, port, *a, **k)
        ip = next(answers, "127.0.0.1")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


def test_dns_rebinding_is_refused_on_the_connection(local_server, monkeypatch):
    port, seen = local_server
    rebinding_dns(monkeypatch)
    with pytest.raises(
        links.RefusedAddress, match=r"rebind\.test is a local or private address \(127\.0\.0\.1\)"
    ):
        links.http_get(f"http://rebind.test:{port}/secret")
    assert seen == []  # connected, then closed before any request was sent


def test_connection_check_refuses_a_private_peer(local_server):
    import requests

    port, seen = local_server
    with requests.Session() as session:
        session.mount("http://", links.checked_adapter())
        with pytest.raises(links.RefusedAddress):
            session.get(f"http://127.0.0.1:{port}/")
    assert seen == []


def test_allow_private_addresses_reaches_a_local_server(local_server):
    port, seen = local_server
    r = links.http_get(f"http://127.0.0.1:{port}/page", allow_private=True)
    assert r.status_code == 200 and "local" in r.text
    assert seen == ["/page"]
