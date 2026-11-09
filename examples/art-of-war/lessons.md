# Lessons learned

Updated: 7 November 2026.

Technical traps and methods that save time, one section per topic, with the date and the source where the
problem was met.

## Machine

- No machine limit recorded for this example library.

## Traps

- 7 November 2026, AOW: the commentary brackets of the Project Gutenberg EPUB are not always balanced. A
  bracket opens without closing in AOW u03 §9 and AOW u03 §92, and one closes without opening in
  AOW u03 §251. Do not rely on brackets to tell Sun Tzu's text from the commentary: rely on the verse
  numbers (a verse of the text starts with its number, "7. ...").
- 7 November 2026, AOW: Giles writes "§" for Sun Tzu's own verses ("V. § 6" is chapter V, verse 6). In
  notes, write the book's numbering in words ("verse 6 of chapter V") and keep `§N` for the unit marker.
- 7 November 2026, AOW: the Words column of `INDEX.md` (10,994 for u03) is the reference size; `wc -w` gives
  11,305 because it also counts the `[§N]` markers.
