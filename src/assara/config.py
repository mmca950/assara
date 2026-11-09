"""Library configuration, read from assara.toml at the library root.

The library root is found, in order: --library on the command line, the ASSARA_HOME environment
variable, then the first parent of the current directory that contains assara.toml.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

CONFIG_NAME = "assara.toml"

DEFAULT_CONFIG = """\
# Assara library configuration.
# Docs: https://github.com/mmca950/assara/blob/main/docs/configuration.md

[library]
# Folder names, relative to this file.
sources = "sources"
synthesis = "synthesis"
# Copy originals into sources/<CODE>/original/ instead of linking to them.
# Use true when originals live on a removable or network drive.
copy_originals = false

[units]
# Target size of one unit of raw text (layer 1). One note is written per unit.
min_words = 10000
max_words = 17000

[transcription]
# faster-whisper model and device. Without an NVIDIA GPU, "small" on "cpu" runs at about 7 to 8 times
# real time. With a GPU: model = "medium", device = "cuda".
model = "small"
device = "cpu"
compute_type = "int8"
# Language of the audio ("en", "fr", "ar"...). Empty = automatic detection.
language = ""

[links]
# Subtitle languages to try first for YouTube, in order.
subtitle_languages = ["en"]
# Web links to loopback, private or link-local addresses (an intranet, a router, a cloud metadata
# service) are refused. Set to true only if you add pages from your own network.
allow_private_addresses = false
"""


@dataclass
class Config:
    root: Path
    sources: str = "sources"
    synthesis: str = "synthesis"
    copy_originals: bool = False
    min_words: int = 10_000
    max_words: int = 17_000
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    language: str = ""
    subtitle_languages: list[str] = field(default_factory=lambda: ["en"])
    allow_private_addresses: bool = False

    @property
    def sources_dir(self) -> Path:
        return self.root / self.sources

    @property
    def synthesis_dir(self) -> Path:
        return self.root / self.synthesis

    @classmethod
    def load(cls, root: Path) -> Config:
        data: dict = {}
        path = root / CONFIG_NAME
        if path.exists():
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        lib = data.get("library", {})
        units = data.get("units", {})
        tr = data.get("transcription", {})
        links = data.get("links", {})
        cfg = cls(
            root=root,
            sources=lib.get("sources", "sources"),
            synthesis=lib.get("synthesis", "synthesis"),
            copy_originals=bool(lib.get("copy_originals", False)),
            min_words=int(units.get("min_words", 10_000)),
            max_words=int(units.get("max_words", 17_000)),
            whisper_model=tr.get("model", "small"),
            whisper_device=tr.get("device", "cpu"),
            whisper_compute_type=tr.get("compute_type", "int8"),
            language=tr.get("language", ""),
            subtitle_languages=list(links.get("subtitle_languages", ["en"])),
            allow_private_addresses=links.get("allow_private_addresses", False) is True,
        )
        if cfg.min_words <= 0 or cfg.max_words < cfg.min_words:
            raise SystemExit(f"{path}: [units] needs 0 < min_words <= max_words.")
        return cfg


def find_root(explicit: str | os.PathLike | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("ASSARA_HOME")
    if env:
        return Path(env).expanduser().resolve()
    here = Path.cwd().resolve()
    for p in (here, *here.parents):
        if (p / CONFIG_NAME).exists():
            return p
    raise SystemExit(
        "No Assara library found. Run `assara init <folder>`, then work inside it, "
        "or set ASSARA_HOME, or pass --library."
    )
