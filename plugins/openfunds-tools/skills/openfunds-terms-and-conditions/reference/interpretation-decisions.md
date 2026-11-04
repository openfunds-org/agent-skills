# Interpretation decisions for FINALIZED_V2

These decisions apply until the source field workbook is corrected or clarified. `reference/field-schema.json`, generated from the Values column, remains authoritative for controlled values.

## Controlled-value casing

- Use lower-case OFTC005120 frequency values exactly as listed in the Values column: `daily`, `twice a week`, `weekly`, `twice a month`, `monthly`, `every two months`, `quarterly`, `twice a year`, `annually`.
- Use `Large redemption`, not `Large Redemption`.
- Use lower-case `other`.

## Application and calculation level

OFTC005010 has no Fund value. A term binding several classes is transmitted once for every applicable class.

OFTC005250 does allow `Fund`. Use it where the calculation or trigger is assessed against the fund, sub-fund or a stated multi-vehicle perimeter. State the exact perimeter in OFTC005310 when that field is used.

## Large redemption

Populate OFTC005440 to OFTC005480 only when a size threshold changes how or when a redemption is processed. Any row using those fields must have OFTC005020 = `Large redemption`.

A size-triggered fee remains OFTC005020 = `Redemption fee`, with the size condition in OFTC005340. A normal redemption gate remains `Redemption gate`; do not populate OFTC005340 merely to restate the cap or queue outcome already described elsewhere.

## Payout delay

Use `Payout delay` where the full proceeds are paid after the ordinary settlement date without a large-redemption classification. Do not classify the fund's ordinary settlement timetable as a payout delay.

## Day offsets

The reference date is day 0. Whole years use 365-day offsets under the final definition: 0 to 365, 366 to 730, and 731 to 1,095. The end offset is inclusive.

For a source term expressed in months where the final definition does not determine one exact integer, do not silently choose a 30-day month. Apply the published 365-day examples only where they answer the term exactly; otherwise leave the uncertain offset unresolved and ask for confirmation.

## Reference-date fields

OFTC005210 and OFTC005220 are alternatives. If OFTC005210 is used, leave OFTC005220 and OFTC005230 blank.

The final workbook describes OFTC005230 as required whenever OFTC005210 is empty. That cannot apply to a variable reference such as each investor's Subscription Date because there is no single actual date. Pending clarification, OFTC005230 is optional when OFTC005220 identifies a variable date basis. Record a note if an actual fixed date is unavailable by design.

## Staged releases

For Redemption restriction rows, OFTC005300 is the cumulative proportion of the relevant holding or tranche permitted to be redeemed at that point, not the increment released during the band. State this explicitly in OFTC005310 on every affected row.

## Term grouping key

One grouping key may link several tiers or related components in one logical rule package. It must not cause them to be collapsed into one row. The grouped view retains each distinct rule row and aggregates only the class identifiers.

The writer generates a stable UUID from the source hash and the sorted candidate IDs in `group_sources`. Rule rows with the same `group_sources` receive the same grouping key.

## Full description and evidence

OFTC005050 is generated from exact evidence quotes. Put explanation, conversion decisions and uncertainty in notes or open questions, not inside the quoted wording.

## Discretion

Record a stated maximum as the numeric value, for example `up to 5%` as 0.05, and retain the discretionary wording in evidence. Do not create a second fixed tier for a purely discretionary override unless it is itself an operative fixed term.

## General prospectus provisions

A general in-kind, suspension or compulsory-redemption provision must be considered for each relevant fund or sub-fund. Map it when it legally applies, or give the candidate an explicit rejection reason. Do not omit it because the fund-specific supplement repeats only the gate or fee provisions.

## OFST reconciliation

If existing OFST values are supplied, check OFTC output against the authoritative gate, queue and order-policy fields. Do not infer those OFST values when they are absent from the task.
