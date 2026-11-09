# Usage: from a PDF to a synthesis

This walk-through takes one book from the inbox to a synthesis sheet. The same steps apply to an EPUB, a
course on video or a web page; only step 2 changes.

## 1. Create a library

```bash
assara init ~/library
cd ~/library
```

This writes `assara.toml`, the folders, the library files (`CLAUDE.md`, `catalog.md`, `queue.md`,
`journal.md`, `lessons.md`, `.gitignore`), the templates and the four Claude Code skills in
`.claude/skills/`.

Open `CLAUDE.md` and fill every item marked `FILL:` (the list is at the top of the file): who the library
is for, the client projects and their tags, the language of the notes, the scope rules (topics to exclude),
your house style rules and the machine limits. Claude reads this file first in every session.

`assara init` on an existing library only adds what is missing. `--force-skills` refreshes the skills
and templates after an upgrade of the package (your notes and your `CLAUDE.md` are never touched).

## 2. Add a source

Drop the file in `inbox/`, choose a code, and extract:

```bash
cp ~/Downloads/book.pdf inbox/
assara add BOOK1 inbox/book.pdf --title "The Title, A. Author, 1998"
```

Result:

```
sources/BOOK1/original/book.pdf     link to the original
sources/BOOK1/raw/pages.md          full text, one [p.N] marker per PDF page
sources/BOOK1/units/u01.md ...      units of 10,000 to 17,000 words, cut on chapters when possible
sources/BOOK1/INDEX.md              units, pages, word counts (the reference size), note status
```

Other sources:

```bash
assara add BOOK2 inbox/book.epub --title "..."                      # EPUB, one unit per chapter group
assara transcribe COURSE1 inbox/course/ --title "..." --language en  # folder of videos or audio
assara regroup COURSE1                                               # many short lessons -> modules
assara link "https://www.youtube.com/watch?v=..." --code TALK1      # one YouTube video
assara link "https://example.org/article" --code WEB1               # a web page
```

A scanned PDF (no text layer) is reported: run `ocrmypdf --skip-text` on it first. If the text of a PDF
comes out reversed or glued, `assara rebuild-pdftotext BOOK1 inbox/book.pdf` rebuilds the units with
`pdftotext`.

You can also ask Claude Code to do all of this: "add inbox/book.pdf" runs the `add-source` skill, which
also proposes the code, checks the result and fills `catalog.md`, `queue.md` and `journal.md`.

## 3. Check the status

```bash
assara status
```

```
Code           Notes  Remaining
BOOK1            0/9    u01, u02, u03, u04, u05, u06, u07, u08, u09
TOTAL            0/9
```

`assara status --pending` shows only the sources with notes left. This count is the reference: it reads
the `notes/` folder.

## 4. Distill the first unit

Open Claude Code in the library and ask:

```
distill u01 of BOOK1
```

The `distill` skill reads only `units/u01.md`, writes `sources/BOOK1/notes/u01.md` following
`templates/note.md` (summary, concepts, figures table, processes, mistakes, studies, cases and anecdotes
cited, open questions, project tags), cites every fact in full form as `BOOK1 u01 [p.N]`, checks that every
cited page exists in the unit, and runs `assara status BOOK1 --sync` to mark the INDEX cell as done.

The note aims at 1,200 to 2,000 words of text (citations not counted). A dense unit may give more: the note
says so in its Source line rather than dropping figures.

## 5. Validate

Read the note. Check the depth, the language, the tags, a few citations against the pages. Ask for
changes ("more detail on the processes", "keep the original terms in parentheses"). When it is right, write
the decision in `CLAUDE.md` if it is a general rule, so every later note follows it.

Always validate one note before a batch: a mistake in the brief repeated over fifty notes is expensive.

## 6. Distill the rest

```
distill all of BOOK1
```

Claude works one unit at a time, in INDEX order. For a large batch, ask it to use sub-agents (see
[claude-code.md](claude-code.md)). Then:

```bash
assara status BOOK1
```

## 7. Synthesize

Create a project folder `synthesis/<project>/` with its `README.md` (from `templates/project-readme.md`:
purpose, tags with their decision, your decisions, sheets). Claude does it on first use and asks you to
validate the tags; in a run where nobody can answer, it writes them as "proposal, to be validated". Then:

```
synthesize the notes tagged [Study-Memory] into synthesis/study/spaced-practice.md
```

The `synthesize` skill reads the notes (never the units), merges what each source brings, keeps divergent
views side by side without deciding, fills the "Solidity of claims" table and "What is missing", and
proposes ideas "For <project>" in your own words. Every line of a sheet carries its citation. A sheet may
rest on a single source: it says so, and its divergences are then between the voices of that source
(author, translator, commentators) or between its chapters.

## 8. Ask questions

```
what do my sources say about interleaving? which ones disagree?
```

The `tutor` skill searches the catalog, the sheets, then the notes, and answers with citations. It goes
down to the units only to check a quote, and proposes to distill a unit when the answer lies in one that has
no note yet.

## Citation formats

One format per source type, always in full form, never abbreviated:

| Source type | Citation |
|---|---|
| PDF | `CODE uNN [p.N]` (page of the PDF file) |
| EPUB | `CODE uNN §N` (the `[§N]` marker, numbered through the whole unit, not per chapter) |
| Audio, video | `CODE chNN [HH:MM:SS]` |
| Instagram post | `CODE pNN s.N` (slide) or `CODE pNN caption` |
| Web page | `CODE wNN` (address and access date in the note's Source line) |

A book that numbers its own paragraphs or verses (sometimes with `§`) is referred to in words in a note
("verse 11"); `§N` is kept for the unit marker.

### Rebuilding a source that already has notes

`assara add` and `assara transcribe` rebuild `units/` on every run. If a rebuild would change the
text of a unit that already has a note (other `min_words` or `max_words` in `assara.toml`, a new media
in a transcribed folder), the command restores the previous units and stops: the note's citations would
otherwise point to other passages. Keep the previous settings, or run again with `--force` and then review
the notes it lists. Units without a note may change freely.

## Known extraction quirks

- **Word counts**: the Words column of `INDEX.md` is the reference size of a unit. `wc -w` on a unit gives
  more, because it also counts the `[p.N]`, `[§N]` or `[HH:MM:SS]` markers and the headings.
- **EPUB commentary brackets can be unbalanced**: in annotated classics the commentary sits in square
  brackets, but the source does not always balance them. In the Project Gutenberg *Art of War* (eBook
  #132), a bracket opens without closing in `AOW u03 §9` and `AOW u03 §92`, and closes without opening in
  `AOW u03 §251`. Telling the text from the commentary then relies on the verse numbers (a verse of the
  text starts with its number, "7. ...").
- **A book's own `§`**: the same translator writes "see § 11" for verse 11 of a chapter. That is the book's
  numbering, not the unit marker `[§N]`.
- **Scanned PDF**: almost no text layer; run `ocrmypdf --skip-text` first and say in the INDEX that the
  text comes from OCR.
- **Reversed or glued PDF text** (right-to-left scripts, odd fonts): `assara rebuild-pdftotext`.

## A full example

[`examples/art-of-war/`](../examples/art-of-war/) is a complete library built from a public-domain text:
units, notes, INDEX and a synthesis sheet.
