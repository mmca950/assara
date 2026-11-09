# Installation

Assara needs Python 3.10 or later. The core package has no heavy dependency; each kind of source is an
optional extra.

## Python package

The package is installed from GitHub until its first release on PyPI. Pick the extras you need, separated
by commas (`pdf`, `epub`, `audio`, `links`, or `all` for everything):

| Extra | Adds |
|---|---|
| (none) | core only: `init`, `status`, `regroup` |
| `pdf` | PDF (PyMuPDF) |
| `epub` | EPUB (ebooklib, BeautifulSoup) |
| `audio` | audio and video transcription (faster-whisper) |
| `links` | YouTube, Instagram, web pages (yt-dlp, instaloader, requests) |
| `all` | everything |

With uv (recommended, as a global tool in its own environment):

```bash
uv tool install "assara[pdf,epub] @ git+https://github.com/mmca950/assara"
# add an extra later: install again with the full list and --force
uv tool install --force "assara[pdf,epub,audio] @ git+https://github.com/mmca950/assara"
```

With pip, in the environment of your choice:

```bash
pip install "assara[all] @ git+https://github.com/mmca950/assara"
pip install "assara[pdf] @ git+https://github.com/mmca950/assara"     # only PDF
```

From a clone, for development:

```bash
git clone https://github.com/mmca950/assara
cd assara
uv venv .venv
uv pip install -p .venv/bin/python -e ".[dev]"
```

A command that needs a missing extra stops and prints the install line, for pip and for `uv tool`.

## System tools

| Tool | Package (Debian, Ubuntu) | Homebrew | Used for |
|---|---|---|---|
| `pdftotext` | `poppler-utils` | `poppler` | `rebuild-pdftotext`, checking tables |
| `ffmpeg`, `ffprobe` | `ffmpeg` | `ffmpeg` | decoding audio, durations |
| `tesseract` | `tesseract-ocr` (+ `tesseract-ocr-<lang>`) | `tesseract` | OCR of images and scanned PDFs |
| `ocrmypdf` | `ocrmypdf` | `ocrmypdf` | adding a text layer to a scanned PDF |

```bash
sudo apt install poppler-utils ffmpeg tesseract-ocr ocrmypdf
```

All are optional: `assara init` lists the ones it cannot find.

## Whisper: the `av` pin

The `audio` extra installs `faster-whisper` with `av==17.1.0`. faster-whisper 1.2.1 calls PyAV with an
argument (`metadata_errors`) that PyAV 19 no longer accepts, which fails with
`open() got an unexpected keyword argument 'metadata_errors'`. PyAV 17.1.0 still accepts it. If pip
picks another version, force it:

```bash
pip install --only-binary=:all: "av==17.1.0"
```

The Whisper model is downloaded on first use (about 500 MB for `small`, 1.5 GB for `medium`) into the
Hugging Face cache (`~/.cache/huggingface`, or `HF_HOME`).

## CPU or GPU

| Machine | Settings (`[transcription]`) | Speed |
|---|---|---|
| CPU only | `model = "small"`, `device = "cpu"`, `compute_type = "int8"` (default) | about 7 to 8 times real time: 80 hours of audio take 10 to 12 hours |
| NVIDIA GPU with recent driver | `model = "medium"`, `device = "cuda"`, `compute_type = "float16"` | many times faster than real time, better accuracy |

Subtitles that already exist (a `.srt` next to a video, YouTube subtitles) are always preferred: faster,
and often better than a transcript.

## Docker

The image bundles every extra and every system tool.

```bash
docker build -t assara .
docker run --rm -v ~/library:/library assara init /library
docker run --rm -v ~/library:/library -v ~/books:/in:ro assara add BOOK1 /in/book.pdf --title "Title, Author, Year"
docker run --rm -v ~/library:/library assara status
```

- `/library` is the library root (`ASSARA_HOME`). Mount your originals read-only (`:ro`) on another
  path, and set `copy_originals = true` in `assara.toml` if the links in `original/` must stay valid
  outside the container.
- Mount a cache volume to keep the Whisper model between runs:
  `-v assara-cache:/cache`.
- Claude Code runs on the host, in `~/library`: the container only prepares units.

## Claude Code

Install Claude Code (see <https://docs.claude.com/en/docs/claude-code>), then open it in the library folder.
See [claude-code.md](claude-code.md).
