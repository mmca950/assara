"""`assara init FOLDER`: create a new, empty library ready for Claude Code."""

from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path

from ..config import CONFIG_NAME, DEFAULT_CONFIG

# Files written at the library root from data/templates/, if missing.
ROOT_FILES = {
    "CLAUDE.md": "CLAUDE.md",
    "catalog.md": "catalog.md",
    "queue.md": "queue.md",
    "journal.md": "journal.md",
    "lessons.md": "lessons.md",
    ".gitignore": "library.gitignore",
}
# Note and synthesis templates copied to <library>/templates/.
TEMPLATES = ("note.md", "short-note.md", "index.md", "synthesis.md", "project-readme.md")


def configure(sub) -> None:
    p = sub.add_parser("init", help="create a new library (folders, config, Claude Code skills, templates)")
    p.add_argument("folder", type=Path, help="folder to create or complete")
    p.add_argument(
        "--force-skills", action="store_true", help="overwrite skills and templates already present"
    )
    p.set_defaults(func=run, needs_library=False)


def _copy_tree(src, dest: Path, force: bool) -> list[Path]:
    written = []
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            written += _copy_tree(item, target, force)
        elif force or not target.exists():
            target.write_bytes(item.read_bytes())
            written.append(target)
    return written


def run(args, _cfg) -> int:
    root: Path = args.folder.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    data = resources.files("assara") / "data"
    created: list[Path] = []

    config = root / CONFIG_NAME
    if not config.exists():
        config.write_text(DEFAULT_CONFIG, encoding="utf-8")
        created.append(config)

    for sub in ("sources", "synthesis", "inbox", "templates", ".claude/skills"):
        (root / sub).mkdir(parents=True, exist_ok=True)

    for name, template in ROOT_FILES.items():
        target = root / name
        if not target.exists():
            target.write_text((data / "templates" / template).read_text(encoding="utf-8"), encoding="utf-8")
            created.append(target)

    for name in TEMPLATES:
        target = root / "templates" / name
        if args.force_skills or not target.exists():
            target.write_text((data / "templates" / name).read_text(encoding="utf-8"), encoding="utf-8")
            created.append(target)

    created += _copy_tree(data / "skills", root / ".claude" / "skills", args.force_skills)

    print(f"Library ready: {root}")
    for path in created:
        print(f"  + {path.relative_to(root)}")
    missing = [tool for tool in ("pdftotext", "ffmpeg", "tesseract", "ocrmypdf") if not shutil.which(tool)]
    if missing:
        print("Optional system tools not found: " + ", ".join(missing) + " (see docs/installation.md).")
    print("Next: put a file in inbox/, then run `assara add CODE inbox/<file>`.")
    return 0
