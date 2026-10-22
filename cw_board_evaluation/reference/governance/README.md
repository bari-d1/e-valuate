# Governance code clauses

Extracted clause data for the governance code library. The source PDFs are **not** in the repo.

| File | What it is |
|---|---|
| `NCCG_2018.json` | Nigerian Code of Corporate Governance 2018: 7 parts, 29 principles, 367 recommended practices (incl. the 30 definitions under 29) |
| `NAICOM_2021.json` | NAICOM Corporate Governance Guidelines for Insurance and Reinsurance Companies 2021: 13 sections, 8 subsections |
| `tag_rules.csv` | Heading → subject types / theme. Edit this to change how clauses are tagged |

Each fixture has a `checks` section to review alongside the clauses: counts per part or section, differences from the document's table of contents, numbering gaps, citations to other codes, and clauses that look truncated or contain stray text.

## Regenerate and load

From `cw_board_evaluation/`:

```bash
pip install pymupdf   # only needed for extraction
python scripts/governance/extract_clauses.py --source-dir "<folder with the PDFs>"
python scripts/seed_reference_data.py              # registers the codes
python scripts/governance/load_clauses.py          # loads clauses, then applies tag_rules.csv
```

Loading is idempotent. After editing `tag_rules.csv`, run `load_clauses.py` again.

## Tagging rules

- A clause whose heading matches a row gets exactly that row's subject types (separate several with `;`) and theme.
- Other clauses inherit their parent's tags. Parts (e.g. "Part B. Assurance") are never tagged.
- Subject types only where the heading names who it applies to; a theme only where the heading makes it obvious.
- Codes must exist in the `subject_types` and `themes` tables; `load_clauses.py` reports rules that match no clause and clauses left untagged.

## Known source quirks

- NAICOM page 15 (sections 12.0 and 13.0) is a scanned image with no text layer; those two clauses were transcribed and carry an `extraction_note`. Its dates are handwritten.
- NAICOM numbers section 2's subsections 2.01–2.06 and then 2.1, 2.2, as printed. Section 6.0 is printed "6. 0".
- NCCG 28.9 ends with a stray "a." in the source; NCCG 19.4.1, NAICOM 2.2 and NAICOM 11.0 end without a full stop in the source.
- NAICOM cites "Principle 2.7" and "Principle 11.1.6" of NCCG; in NCCG these are recommended practices, and they are linked as such.
