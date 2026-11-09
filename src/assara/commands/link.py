"""`assara link URL --code CODE`: retrieve a YouTube video, an Instagram post or web pages."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import links
from ..library import AssaraError, check_code

EPILOG = """\
modes (chosen from the URL):
  youtube    one video = one source, unit ch01 (parts ch01a, ch01b... above max_words). Manual subtitles,
             else automatic ones in the spoken language, else Whisper. Playlists and channels are refused.
             Cite: CODE ch01 [HH:MM:SS]
  instagram  CODE is a collection (one per theme), extended post by post: unit pNN per post (caption, OCR
             of images if tesseract is installed, Whisper for a video). Short note: templates/short-note.md.
             Cite: CODE pNN caption, CODE pNN s.N
  web        any other URL: one unit wNN per page, with URL and retrieval date. An inaccessible page is
             recorded in the INDEX, never invented. Cite: CODE wNN
  --file     a text file of links: copied to raw/, each web link becomes a unit wNN.

Re-running is safe: posts and pages already retrieved are skipped, notes are never touched.

Notice: you are responsible for having the right to download and use the content you retrieve, and for
respecting each platform's terms of use. Assara does not bypass logins, paywalls or DRM.
"""


def configure(sub) -> None:
    p = sub.add_parser(
        "link",
        help="retrieve a YouTube video, an Instagram post or web pages as a source",
        description="Retrieve a link as a source (needs the 'links' extra, see docs/installation.md).",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("url", nargs="?", help="YouTube video, Instagram post or reel, or web page")
    p.add_argument("--file", type=Path, help="text file of links (each link becomes a web page unit)")
    p.add_argument("--code", help="source code (Instagram: code of the collection, e.g. IGAI)")
    p.add_argument("--title", help="title of the source in its INDEX")
    p.add_argument(
        "--language",
        default="",
        help="language of the content (en, fr, ar...); default: spoken "
        "language of the video, then [transcription] language",
    )
    p.add_argument(
        "--info", action="store_true", help="describe what would be done, without writing anything"
    )
    p.set_defaults(func=run)


def run(args, cfg) -> int:
    if bool(args.url) == bool(args.file):
        raise AssaraError("Give either a URL or --file LIST.txt.")
    if args.info:
        return info(args, cfg)
    if not args.code:
        raise AssaraError("--code is required (Instagram: the code of the collection, e.g. IGAI).")
    code = check_code(args.code)
    if args.file:
        links.add_link_file(cfg, args.file, code, args.title)
        return 0
    mode = links.detect_mode(args.url)
    if mode == "youtube":
        links.add_youtube(cfg, args.url, code, args.title, args.language)
    elif mode == "instagram":
        links.add_instagram(cfg, args.url, code, args.title, args.language)
    else:
        links.add_web(cfg, args.url, code, args.title)
    return 0


def info(args, cfg) -> int:
    """Describe the link(s) without writing anything in the library."""
    if args.file:
        found = links.parse_link_list(args.file.read_text(encoding="utf-8", errors="replace"))
        print(f"{len(found)} link(s) in {args.file}; the file would be copied to raw/.")
        for url in found:
            mode = links.detect_mode(url)
            what = "web page unit" if mode == "web" else f"{mode} link, skipped (add it with `assara link`)"
            print(f"  {url}: {what}")
        return 0
    url = args.url
    mode = links.detect_mode(url)
    if mode == "youtube":
        if links.is_youtube_collection(url):
            raise AssaraError("Playlists and channels are refused: add the videos one by one.")
        data = links.video_info(url)
        print(links.describe_video(data, cfg, args.language))
        print(links.THIRD_PARTY_PREVIEW)
        print((data.get("description") or "")[:600])
    elif mode == "instagram":
        sc = links.instagram_shortcode(url)
        kind, media, caption, owner, date = links.instagram_post(sc)
        videos = sum(1 for v, _ in media if v)
        print(
            f"mode instagram | post {sc} | {kind} | by {owner} | published {date} | {len(media)} slide(s), "
            f"{videos} video(s) | would become the next pNN unit of the collection"
        )
        print(links.THIRD_PARTY_PREVIEW)
        print(caption[:600])
    else:
        page = links.fetch_page(url, cfg.allow_private_addresses)
        if page.ok:
            print(
                f"mode web | {page.title or '(no title)'} | {links.words(page.text)} words | "
                "would become the next wNN unit"
            )
            print(links.THIRD_PARTY_PREVIEW)
            print(page.text[:600])
        else:
            print(f"mode web | INACCESSIBLE: {page.error} | would be recorded in the INDEX, not invented")
    return 0
