# Configuration

Each library has a `assara.toml` at its root, written by `assara init`. Every key is optional:
a missing key takes its default.

The library root is found, in order: `--library` on the command line, the `ASSARA_HOME` environment
variable, then the first parent of the current folder that contains `assara.toml`.

## `[library]`

| Key | Default | Meaning |
|---|---|---|
| `sources` | `"sources"` | folder of the sources, relative to `assara.toml` |
| `synthesis` | `"synthesis"` | folder of the synthesis sheets |
| `copy_originals` | `false` | `false`: `original/` holds a symbolic link to the original file. `true`: a copy. Use `true` when originals live on a removable or network drive, or inside a Docker mount that will not exist later |

## `[units]`

| Key | Default | Meaning |
|---|---|---|
| `min_words` | `10000` | smallest unit of raw text; a cut is made at the next chapter start once this size is reached |
| `max_words` | `17000` | largest unit; a cut is forced before this size. Must be at least `min_words` |

One note is written per unit. Larger units give fewer, denser notes (more compression, more risk of
dropping details); smaller units give more notes. The defaults suit books and long courses. A short tail
(under a third of `min_words`) is merged into the previous unit.

## `[transcription]`

| Key | Default | Meaning |
|---|---|---|
| `model` | `"small"` | faster-whisper model: `tiny`, `base`, `small`, `medium`, `large-v3` |
| `device` | `"cpu"` | `cpu` or `cuda` (NVIDIA GPU) |
| `compute_type` | `"int8"` | `int8` on CPU; `float16` on GPU |
| `language` | `""` | language of the audio (`en`, `fr`, `ar` ...). Empty: automatic detection. `--language` on the command line wins |

See [installation.md](installation.md) for speeds.

## `[links]`

| Key | Default | Meaning |
|---|---|---|
| `subtitle_languages` | `["en"]` | subtitle languages to try first for YouTube, in order |
| `allow_private_addresses` | `false` | allow web links (and redirects) to loopback, private or link-local addresses; leave off unless you add pages from your own network. It also skips the local name lookup of that check (useful behind a proxy without local DNS) |

## Example

```toml
[library]
sources = "sources"
synthesis = "synthesis"
copy_originals = true

[units]
min_words = 8000
max_words = 14000

[transcription]
model = "medium"
device = "cuda"
compute_type = "float16"
language = "en"

[links]
subtitle_languages = ["en", "fr"]
```

## Settings that live in `CLAUDE.md`

The note length (default 1,200 to 2,000 words of text, citations not counted), the language of notes, the
client projects, their tags, the scope rules and any house style rules are instructions for Claude, not for
the CLI: set them in the library's `CLAUDE.md` (every item marked `FILL:`). Once a project has its folder,
its tags live in `synthesis/<project>/README.md`.
