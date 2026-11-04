---
name: openfunds-terms-and-conditions
description: Extracts redemption and subscription terms from a fund's legally binding prospectus or terms document into a draft openfunds OFTC 2.14.0 Excel transmission. Use when asked to identify or populate lock-ups, gates, redemption fees, anti-dilution levies, in-kind redemptions, side pockets, suspensions, holdbacks, payout delays, minimum-retention rules, large-redemption delays or other OFTC terms. Creates a complete candidate ledger, evidence-backed rule catalogue, validation report, transmission view and human review views. The output is always a draft requiring approval by the fund manager or administrator.
license: CC-BY-ND-4.0
compatibility: Requires Python 3.9+, openpyxl and Poppler pdftotext for PDF inputs. Supports one PDF or DOCX source, including a pre-merged prospectus and supplements.
metadata:
  author: Titanbay and openfunds
  version: "2.0.1"
  openfunds-schema: "2.14.0 DRAFT_CONSULTATION, 17 September 2026"
---

# openfunds Terms and Conditions extractor

Create a fast, evidence-backed first draft. Do not present the workbook as certified or complete. The manager, administrator or another person who knows the fund must review it before publication.

## Authority and required references

Use these in this order:

1. `reference/field-schema.json` is the machine-readable authority for field names, types and controlled values. Controlled values are case-sensitive.
2. `reference/interpretation-decisions.md` resolves known ambiguities in the final workbook.
3. `reference/mapping-guide.md` explains term selection and contains corrected examples.
4. `reference/extraction-format.md` defines the intermediate JSON contract.

Do not rely on remembered openfunds values or older R&P templates. Do not invent OFIDs or controlled values.

## Scope check

Proceed only with a legally binding fund-rules document: a prospectus, offering memorandum, fund terms annex, supplement, or investor-facing offering document that sets the fund's operative terms.

Do not extract a transmission from a marketing deck, pitch deck, factsheet or KID that defers to another document for the operative terms. Produce only a short abstention note stating which binding document is missing.

The current scripts accept one PDF or DOCX. If the source comprises an umbrella prospectus and supplements, use a correctly ordered merged file and record that fact in the review notes. Fund-specific supplement wording overrides general wording where they conflict.

## Working directory

Create a temporary working directory and assign it explicitly:

```bash
WORK_DIR="<temporary-directory>"
```

Copy no source document into the skill directory.

## Step 1: stage and identify the document

```bash
python3 scripts/stage_document.py "<source>" \
  --output "$WORK_DIR/staged.md" \
  --manifest "$WORK_DIR/source-manifest.json"
```

Stop if the manifest reports unreadable pages until those pages have been visually inspected. Do not silently omit them.

Read the title page, document status, effective date, table of contents and relevant fund or sub-fund heading. Confirm the legal fund name and that the document is operative rather than promotional.

Run the scope assessor:

```bash
python3 scripts/assess_scope.py "$WORK_DIR/staged.md" \
  --manifest "$WORK_DIR/source-manifest.json" \
  --output "$WORK_DIR/scope-assessment.json"
```

Its result is a warning system, not a legal conclusion. Review every negative finding. Record `document_scope = binding` and the supporting wording in `metadata.scope_evidence` only when the supplied file itself sets the operative terms. If it is a summary controlled by an absent prospectus, abstain.

## Step 2: build the candidate ledger

```bash
python3 scripts/discover_candidates.py "$WORK_DIR/staged.md" \
  --manifest "$WORK_DIR/source-manifest.json" \
  --output "$WORK_DIR/candidates.json"
```

Discovery is a recall aid, not an answer key. Search the staged document again using the table of contents, defined terms and cross-references found in candidate passages. Add any missed candidate passage to the ledger using the same fields. In particular, follow references from a supplement to general redemption, suspension, compulsory-redemption and in-kind provisions.

Every candidate must end with one disposition:

- `mapped`: represented by one or more rules;
- `duplicate`: the same operative clause is already represented;
- `out_of_scope`: relevant wording that is not an operative OFTC term;
- `insufficient_evidence`: the document indicates a term exists but does not state enough to map it;
- `unresolved`: two or more plausible mappings remain.

No blank disposition is permitted.

## Step 3: create the document inventory

Create one entry for every share class to which the terms apply. OFST020050 Share Class Extension is always required. Populate OFST020000 only when the source gives a valid ISIN. Never put a class name, family description or placeholder in the ISIN field.

Record missing ISINs once on the share-class entry as an open question. Do not repeat the same question on every rule.

## Step 4: map evidence to rule rows

Build `$WORK_DIR/extraction.json` using `reference/extraction-format.md`.

Work at rule level before repeating anything across classes:

1. Identify one economic or operational rule package.
2. Split it into one rule row per tier or distinct component.
3. List the candidate IDs that form the package in `group_sources`.
4. Map its application to class IDs in `applies_to`.
5. Populate only OFTC fields in `fields`. The writer creates the fund name, class identifiers, grouping key and full description.
6. Add verbatim evidence records and state which populated OFIDs each quote supports.

Use exact, contiguous source wording. Do not use ellipses inside a quote submitted for automatic verification. If two passages are needed, add two evidence records.

When the text does not support a value, leave it blank and create an open question. Never fill a plausible default silently.

## Step 5: reconcile coverage

Before validation, check all five:

1. Every candidate has a disposition and reason where required.
2. Every mapped candidate names its rule IDs.
3. Every rule names its classes and group-source candidates.
4. Every populated material OFTC field is supported by evidence.
5. General prospectus provisions have either been applied to the relevant fund classes or rejected with a stated reason.

## Step 6: validate

```bash
python3 scripts/validate_extraction.py "$WORK_DIR/extraction.json" \
  --schema reference/field-schema.json \
  --staged "$WORK_DIR/staged.md" \
  --manifest "$WORK_DIR/source-manifest.json" \
  --report "$WORK_DIR/validation.json"
```

Do not write the workbook while validation errors remain. Correct mapping or formatting errors using the source. Do not resolve an error by inventing evidence.

Warnings may remain in a draft if they are visible to the reviewer.

## Step 7: write the draft workbook and review report

```bash
python3 scripts/write_form.py "$WORK_DIR/extraction.json" \
  --schema reference/field-schema.json \
  --staged "$WORK_DIR/staged.md" \
  --manifest "$WORK_DIR/source-manifest.json" \
  --out-form "<Fund> - openfunds OFTC draft.xlsx" \
  --out-review "<Fund> - openfunds OFTC review.md"
```

The workbook contains:

- `Run_metadata`: source and schema hashes plus the draft warning;
- `Transmission_view`: one row per rule row per applicable share class;
- `Grouped_view`: one row per distinct rule row with classes aggregated, preserving tiers;
- `Evidence`: field-level source support;
- `Candidate_ledger`: mapped and rejected candidates;
- `Open_questions`: deduplicated fund, class and rule questions.

The generated OFTC005050 value is assembled from the evidence quotes. The generated OFTC005005 key is deterministic for the source file and `group_sources` combination.

## Step 8: handover

Report:

- rule rows and expanded transmission rows;
- mapped, unresolved and insufficient-evidence candidate counts;
- missing share-class identifiers;
- validation warnings;
- the workbook and review-report paths.

End by stating that the files are drafts requiring review by the fund manager or administrator.

## Non-negotiable stops

Stop rather than writing a workbook when:

- the supplied document is not the binding rules document;
- unreadable pages have not been inspected;
- the fund or applicable share classes cannot be identified;
- a candidate has no disposition;
- a populated field has no source evidence;
- validation reports an error.
