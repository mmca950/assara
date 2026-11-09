# Architecture

Assara splits the work in two:

- **The CLI** (`assara`) does the mechanical part: it extracts text from PDF and EPUB files,
  transcribes audio and video, fetches links, and cuts everything into **units** of raw text with stable
  page markers or timestamps. It never summarises anything.
- **Claude Code**, driven by the skills that `assara init` installs in the library, does the
  intellectual part: it reads one unit at a time and writes a **note**, then crosses notes into
  **synthesis** sheets.

## The three layers

| Layer | Folder | Content | Size | Who reads it |
|---|---|---|---|---|
| 1. Raw | `sources/<CODE>/units/` | extracted text or timestamped transcript, cut into units | 10,000 to 17,000 words per unit | nobody in full; lookup and quotes only |
| 2. Notes | `sources/<CODE>/notes/` | one structured, cited note per unit | 1,200 to 2,000 words of text, citations not counted | you and Claude: the working layer |
| 3. Synthesis | `synthesis/<project>/` | one sheet per concept or target work, crossing sources (or the voices of one source) | as long as needed | the projects that use the library |

Why three layers:

- **Units** keep the source readable by a model in one go (a unit fits easily in a context window) and keep
  every quote traceable to a page or a timestamp.
- **Notes** compress a unit by about ten, without dropping figures, definitions or doubts. Answering from
  notes is fast and cheap; the raw text is only reopened to check a quote.
- **Syntheses** are where sources meet: agreements, divergences shown side by side, the solidity of each
  claim and what is still missing. Projects draw from syntheses, never from raw text.

```
  original file          layer 1: units              layer 2: notes            layer 3: synthesis
 (PDF, EPUB, mp4,   -->  sources/BOOK1/units/   -->  sources/BOOK1/notes/  --> synthesis/<project>/
  URL, .srt)             u01.md [p.1] ...            u01.md (cited)            topic.md
                         u02.md [p.48] ...           u02.md                    (crosses BOOK1, AOW,
                                                                                 COURSE2 ...)
      assara add / transcribe / link            skill: distill            skill: synthesize
      (Python CLI, no AI)                            (Claude Code)             (Claude Code)

                                  skill: tutor answers questions from layers 3 and 2,
                                  and goes down to layer 1 only to check a quote.
```

## Source codes and citations

Each source gets a short code (2 to 10 uppercase letters or digits, e.g. `BOOK1`, `AOW`). Every fact in a
note or a sheet is followed by its citation:

| Source type | Unit names | Citation | N is |
|---|---|---|---|
| PDF | `u01`, `u02` ... | `CODE uNN [p.N]` | the `[p.N]` marker: page number of the PDF file, not of the printed book |
| EPUB | `u01`, `u02` ... (groups of chapters) | `CODE uNN §N` | the `[§N]` paragraph marker, numbered through the whole unit (not per chapter) |
| Audio, video | `ch01-title` ... | `CODE chNN [HH:MM:SS]` | the timestamp of the paragraph in the unit |
| Instagram post | `p01`, `p02` ... | `CODE pNN s.N` or `CODE pNN caption` | the slide number (`## Slide N` in the unit) |
| Web page | `w01`, `w02` ... | `CODE wNN` | no marker; the address and access date are in the note's Source line |
| Other export | as listed in the INDEX | `CODE <unit>` | |

Citations are always written in full form, in notes and syntheses alike: never abbreviated (no `[p.62]` or
`§12` standing alone). Several markers of the same unit may follow one full citation (`AOW u03 §2, §4`).
Some books number their own paragraphs or verses, sometimes with `§`: notes refer to that numbering in
words ("verse 11") and keep `§N` for the unit marker only.

Codes never change once notes cite them.

## Library layout

```
~/library/
├── assara.toml            settings (see configuration.md)
├── CLAUDE.md                   entry point for Claude: owner, projects, scope rules, method
├── catalog.md                  one row per source
├── queue.md                    what is left to do
├── journal.md                  sessions and decisions, most recent first
├── lessons.md                  technical traps and methods
├── inbox/                      files you drop for processing (never modified)
├── sources/
│   └── BOOK1/
│       ├── original/           link to (or copy of) the original file: never published
│       ├── raw/                raw extraction (pages.md, .srt, .json): never published
│       ├── units/              layer 1: u01.md, u02.md ...: never published
│       ├── notes/              layer 2: u01.md, u02.md ...
│       └── INDEX.md            units, word counts, note status (pending, done)
├── synthesis/
│   └── <project>/
│       ├── README.md           purpose, tags (reference), owner decisions, sheets
│       └── <topic>.md          layer 3
├── templates/                  note.md, short-note.md, index.md, synthesis.md, project-readme.md
└── .claude/skills/             add-source, distill, synthesize, tutor
```

## The INDEX

`sources/<CODE>/INDEX.md` is written by the CLI. Its last column holds the note cell,
`` `notes/u03.md` (pending) `` or `` (done) ``. `assara status` counts done and pending notes from it
(it checks the `notes/` folder, so the count is right even if the cell was not updated);
`assara status CODE --sync` writes `(done)` in the cells whose note exists. The Words column is the
reference size of a unit: `wc -w` on a unit gives more, because it also counts the markers. Rebuilding
units or an INDEX never touches existing notes.

## Package layout

```
src/assara/
├── cli.py                  argument parsing, one sub-command per module
├── config.py               assara.toml, library discovery
├── library.py              codes, units grouping, INDEX writing, status
├── commands/               init, status, add, transcribe, link, regroup, rebuild-pdftotext
└── data/
    ├── skills/             Claude Code skills copied into each library by `init`
    └── templates/          note, index, synthesis, CLAUDE.md and the library files
```
