# Contributing

Thanks for your interest. Bug reports, fixes, new source types and improvements to the skills are welcome.

## Before you start

- Open an issue to discuss anything larger than a small fix.
- Never attach copyrighted material (books, course transcripts, units, notes of a protected source) to an
  issue or a pull request. Reproduce problems with a public-domain text or a tiny generated file.
- Contributions that bypass DRM or other technical protection measures, or that scrape platforms at scale,
  will not be accepted (see [docs/legal.md](docs/legal.md)).

## Development setup

```bash
git clone https://github.com/mmca950/assara
cd assara
uv venv .venv
uv pip install -p .venv/bin/python -e ".[dev]"
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check src tests
```

The `dev` extra does not install Whisper: tests never download a model or touch the network.

## Guidelines

- Python 3.10 or later, type hints where cheap, docstrings and messages in English.
- `ruff check` and `ruff format --check` clean, line length 110.
- One command per module in `src/assara/commands/`, exposing `configure(sub)`; reusable logic in a
  plain module; optional dependencies imported lazily, with a clear `pip install 'assara[extra]'`
  message when missing.
- Tests for pure logic (parsing, grouping, cutting), with tiny fixtures generated inside the test.
- Keep the method's guarantees: rebuilding units or an INDEX never overwrites a note; transcription is
  resumable; garbled text is flagged, never guessed.
- No em dash in code, docs, templates or skills.
- Skills and templates live in `src/assara/data/`. A change there changes every new library: explain
  why in the pull request, and add an entry to `CHANGELOG.md`.

## Pull requests

- One topic per pull request, with a short description of what and why.
- Tests and ruff pass.
- Update the docs when behaviour or options change.

## Releasing (maintainers)

1. Set the version in `pyproject.toml` and `src/assara/__init__.py`, date the section in `CHANGELOG.md`.
2. Commit, then tag: `git tag v0.1.0 && git push origin v0.1.0`.
3. The `Release` workflow checks that the tag matches the version, builds, publishes to PyPI (trusted
   publishing, no token in the repository) and creates the GitHub release.

## Security

Report vulnerabilities privately, see [SECURITY.md](SECURITY.md).

By contributing you agree that your contribution is released under the MIT licence and that you follow the
[Code of Conduct](CODE_OF_CONDUCT.md).
