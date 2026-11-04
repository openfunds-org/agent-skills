# Mapping guide

Use the exact controlled values in `field-schema.json`. These examples demonstrate structure; source evidence still determines every output.

## Term selection

- A prohibition on redemption is `Redemption restriction`.
- A periodic cap on aggregate redemptions is `Redemption gate`.
- A charge on redemption is `Redemption fee`.
- A threshold that changes how or when a large request is processed is `Large redemption`.
- A delay not caused by a large-redemption classification is `Payout delay`.
- A retained portion of proceeds is `Holdback`.
- Settlement through assets rather than cash is `Redemption in kind`.
- A forced action when the remaining holding falls below a floor is `Minimum retention`.
- Use `other` only when none of the 13 named values fits. Explain it fully.

## Application and calculation

Ask two separate questions:

1. Where does the term legally apply? Populate OFTC005010 with `Share Class` or `Investor`.
2. At what level is its calculation or trigger assessed? Populate OFTC005250 with `Fund`, `Share Class`, `Investor` or `Subscription Tranche`.

Do not use application-level repetition as evidence that the calculation is share-class level.

## Example 1: tiered early-redemption fee

Source meaning: 3% in year 1, 2% in year 2 and 1% in year 3 from each subscription date.

Create three rule rows with one grouping key:

| Field | Tier 1 | Tier 2 | Tier 3 |
|---|---:|---:|---:|
| OFTC005020 | Redemption fee | Redemption fee | Redemption fee |
| OFTC005110 | Specified Period | Specified Period | Specified Period |
| OFTC005140 | 0 | 366 | 731 |
| OFTC005150 | 365 | 730 | 1095 |
| OFTC005160 | calendar days | calendar days | calendar days |
| OFTC005180 | no | no | no |
| OFTC005220 | Subscription Date | Subscription Date | Subscription Date |
| OFTC005250 | Subscription Tranche | Subscription Tranche | Subscription Tranche |
| OFTC005300 | 0.03 | 0.02 | 0.01 |
| OFTC005310 | NAV of shares redeemed | NAV of shares redeemed | NAV of shares redeemed |

Do not add a fourth 0% row merely to show that the fee ends.

## Example 2: fund-level quarterly gate

For a 5% cap assessed across the fund and parallel vehicles:

- OFTC005010 = `Share Class`
- OFTC005020 = `Redemption gate`
- OFTC005030 = `Redemption gate`
- OFTC005110 = `Recurring Frequency`
- OFTC005120 = `quarterly`
- OFTC005250 = `Fund`
- OFTC005300 = `0.05`
- OFTC005310 = the exact fund and parallel-vehicle NAV perimeter

Repeat the row across every applicable class through `applies_to`. Do not put the queue result in OFTC005340; reconcile queue and order policies with existing OFST fields when supplied.

## Example 3: size-triggered delayed execution

For a request above the higher of EUR 5 million and 3% of Fund NAV that is deferred by 180 calendar days:

- OFTC005020 = `Large redemption`
- OFTC005110 = `Perpetual`
- OFTC005250 = the level at which the threshold is assessed
- OFTC005320 = `5000000`
- OFTC005330 = `EUR`
- OFTC005440 = the complete compound threshold
- OFTC005450 = the execution consequence
- OFTC005470 = `180`
- OFTC005480 = `calendar days`

Do not use `Payout delay` merely because the result is a delay. The large-redemption fields determine the term type.

## Example 4: staged redemption restriction

Create one row per band. OFTC005300 is cumulative and OFTC005310 says so explicitly:

| Start | End | In perpetuity | Percentage | Basis |
|---:|---:|---|---:|---|
| 0 | 180 | no | 0 | Cumulative proportion of tranche NAV permitted to be redeemed |
| 181 | 210 | no | 0.50 | Cumulative proportion of tranche NAV permitted to be redeemed |
| 211 | 240 | no | 0.75 | Cumulative proportion of tranche NAV permitted to be redeemed |
| 241 | blank | yes | 1.00 | Cumulative proportion of tranche NAV permitted to be redeemed |

Use OFTC005250 = `Subscription Tranche` when each subscription has its own clock.

## Example 5: holdback

For up to 5% of full-redemption proceeds withheld pending final NAV confirmation:

- OFTC005020 = `Holdback`
- OFTC005110 = `Perpetual`
- OFTC005250 = `Investor`
- OFTC005300 = `0.05`
- OFTC005310 = `NAV being redeemed`
- OFTC005340 = the full-position trigger if that condition determines whether the holdback applies

The evidence retains "up to" and any discretion.

## Example 6: redemption in kind

Where the operative document permits redemption proceeds to be satisfied through fund assets:

- OFTC005020 = `Redemption in kind`
- OFTC005030 = `Redemption in kind`
- OFTC005110 = `Perpetual` unless a narrower period is stated
- OFTC005250 = the level at which the option or decision is assessed

Conditions such as investor request, fair treatment, Board approval and valuation should remain in OFTC005050 through the evidence quotes. Do not omit a general prospectus provision merely because the supplement does not repeat it.

## Minimum retention

Do not infer a retention floor from a minimum subscription amount. Populate OFTC005410 and OFTC005420 only when the source establishes both the floor and the resulting action. If it permits conversion or several discretionary outcomes, preserve all outcomes in OFTC005420 and raise a question if one value cannot describe them safely.
