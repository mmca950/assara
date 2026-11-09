# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - Unreleased

### Added

- `assara init`: new library with `assara.toml`, folders, `CLAUDE.md`, catalog, queue, journal,
  lessons, `.gitignore`, templates and Claude Code skills.
- `assara add`: PDF and EPUB extraction into units with page markers, cut on chapters.
- `assara rebuild-pdftotext`: rebuild PDF units with `pdftotext` when PyMuPDF garbles the text.
- Rebuild guard: `add` and `transcribe` refuse to change the text of units that already have a note,
  restore the previous units, and list the notes concerned (`--force` to override).
- Missing-extra errors print the install line for pip and for `uv tool`.
- `assara transcribe`: audio and video to timestamped units, reusing existing `.srt` files, with
  faster-whisper otherwise; resumable passes.
- `assara link`: single YouTube video, single Instagram post, or web page into units.
- `assara regroup`: group short lessons into modules.
- `assara status`: notes done and pending per source; `--sync` writes (done) in the INDEX.
- Skills `add-source`, `distill`, `synthesize`, `tutor`, and templates for notes, short notes, INDEX,
  synthesis sheets and project `README.md`.
- Documentation: architecture, installation, usage, configuration, Claude Code, legal.
- A new `README.md`: logo, example excerpts, diagram, features, FAQ and roadmap.
- Docker image with every extra and system tool.
- Open-source project files: `SECURITY.md`, `CITATION.cff`, issue and pull request templates, Dependabot,
  `.editorconfig`, `.gitattributes`; CI checks formatting, builds and installs the wheel; a tag-triggered
  release workflow (PyPI trusted publishing and GitHub release).

### Changed

- The `audio` extra pins `av==17.1.0` (was 16.0.1); faster-whisper 1.2.1 decodes audio with it.
- CI and release workflows use the current major versions of the GitHub actions (no Node.js 20
  warning).

### Security

- Text from every source (links, PDF, EPUB, subtitles) is cleaned: control characters in page text, titles, captions, video metadata,
  subtitles, OCR and tool error messages become spaces (lone surrogates become U+FFFD), and everything the
  CLI prints shows control characters as `?`, so a remote page cannot drive the terminal.
- `INDEX.md`: titles, URLs and cells cannot add lines, rows or note-status markers.
- Units made from a link start with a "third-party content" notice, and `assara link --info` frames its
  preview the same way.
- The skills and the library `CLAUDE.md` state that source text is data, never instructions, and that a
  link found in a unit is never fetched on its own say-so.
- Web links, link files and redirects to loopback, private or link-local addresses are refused and
  recorded as inaccessible (`[links] allow_private_addresses = true` allows them). Every redirect is
  checked, on the address as requests prepares it, so a backslash or `@` in the host cannot make the
  check and the connection read two different hosts. Redirects are followed in one session (cookies
  are kept between hops) and their targets decoded as requests does (non-ASCII paths). A name that does
  not resolve locally is refused, even behind a proxy (which could reach an internal name);
  `allow_private_addresses = true` skips the check. The address is checked again on the connection
  itself (its peer address), so DNS rebinding cannot reach a local service; through a proxy, only the
  name is checked.
- The `?` shown for control characters no longer garbles the Whisper model download progress bar, and
  `assara` runs when started with stdout or stderr closed.
- Subtitles read from a link go through the same SRT reader as `assara transcribe` (`{\an8}`-style tags
  dropped).
- The traceback of an unexpected error is printed with control characters shown as `?`.
- Commands printed for you to copy (the `ocrmypdf` advice for a scanned PDF, the `nohup` hint of a long
  transcription) quote every argument for the shell: a file name with a quote, `$` or `;` cannot run a
  command.
- Downloads have limits: 10 MB and 2 minutes for a web page, 1 GB and 30 minutes for an Instagram image
  or video, 2 GB and 3 hours for the audio of a YouTube video. A page over its limit is recorded as
  inaccessible; a media over its limit leaves no partial file.
- Unit numbers read every digit: after `w99`, `w100` and `w101` follow, and a new unit is refused if its
  name is already used (no overwritten page). INDEX rows follow the unit number (w9 before w10).
- Link mode detection parses the host properly (`https://attacker.example?.youtube.com` is a web page).
- `docs/claude-code.md`: the recommended permissions no longer allow `assara link`, `assara add`,
  `assara transcribe`, shell `grep`, `head` or `wc` without a prompt, and deny writing a `CLAUDE.md` or a
  `.claude/` folder inside `sources/` or `synthesis/`. Existing libraries: see "Updating the skills".
