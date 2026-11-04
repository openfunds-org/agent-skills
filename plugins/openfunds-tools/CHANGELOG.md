# Changelog

## 2.0.1

- Aligned against the openfunds v2.14.0 consultation draft release package (`openfunds_Fieldlist_v2.14.0_DRAFT.xlsx`, 17 September 2026) and official standalone empty template (`openfunds_OFTC_v2.14.0_Empty_Template.xlsx`).
- Expanded schema to all 32 fields (3 linkage fields plus 29 OFTC fields, incorporating `OFTC008010 Term Valid From` and `OFTC008020 Term Valid To`).
- Standardised controlled values (`Redemption restriction` and `Subscription anti-dilution levy`) and field descriptions.
- Aligned `Transmission_view` tab headers, column order and validation lists with the official openfunds v2.14.0 template.

## 2.0.0

- Initial v2 architecture built against `openfunds_oftc_2.14.0_FINALIZED_V2.xlsx`.
- Added scope assessment, deterministic candidate ledger discovery, rule-level extraction and strict evidence validation.
- Added multi-tab Excel output (`Run_metadata`, `Transmission_view`, `Grouped_view`, `Evidence`, `Candidate_ledger`, `Open_questions`) and Markdown review report.
