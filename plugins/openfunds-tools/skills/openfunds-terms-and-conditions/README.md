# openfunds Terms and Conditions skill

Version 2.0.1 creates an evidence-backed draft OFTC 2.14.0 transmission from one binding fund document or a pre-merged prospectus and supplement bundle.

The pipeline includes a scope assessor that flags marketing, summary-only and prospectus-controls wording before extraction.

## Status

Generated workbooks are labelled `DRAFT FOR FUND REVIEW` and must be approved by the fund manager, administrator or another person who knows the operative terms.

## Runtime

- Python 3.9 or later
- `openpyxl`
- Poppler `pdftotext` for PDF inputs

DOCX staging uses the Python standard library and does not require `python-docx`.

## Installation

The directory follows the open Agent Skills specification. Install or upload the complete `openfunds-terms-and-conditions` folder using the instructions for the relevant skill-compatible host. A release ZIP contains the same top-level folder.

The procedure is provider-neutral. It has no Claude-specific frontmatter or tool permissions. Runtime capabilities and package availability still differ between hosts and must be tested.

## Source of truth

`reference/field-schema.json` was generated from:

`assets/openfunds_Fieldlist_v2.14.0_DRAFT.xlsx`

Source SHA-256:

`8f5449bf7f9a8c59c42613fbbf9414006c295e52a2574b0ea082193ec7231171`

Verify or rebuild it with:

```bash
python3 scripts/build_schema.py \
  assets/openfunds_Fieldlist_v2.14.0_DRAFT.xlsx \
  --output reference/field-schema.json
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Repeatability comparison

Keep the intermediate `extraction.json` from each run, then compare two runs with:

```bash
python3 scripts/compare_extractions.py run-a.json run-b.json --output comparison.json
```

The comparison ignores model-written rule IDs and matches rules through stable candidate IDs, structured identity fields and evidence hashes.

## Known boundary

Version 2.0.1 accepts one source file. Where an umbrella prospectus and supplements are needed, supply a correctly ordered merged PDF or DOCX and state the merge order in the review notes.
