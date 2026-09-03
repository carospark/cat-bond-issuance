# Parser backlog — pick-up-when-bored list

State when written: 1,311 deals parsed, 626 tests, 19% of deals carry a flag,
issuance validated to 0.6% against the publisher. Nothing here blocks analysis;
every item is a *visible, flagged* gap, ordered roughly by value-per-hour.
Method that has worked every time: read the page, verify the mechanism, fix the
class not the instance, pin it in `tests/test_golden.py`, mutation-test the pin.

## 1. The 7 remaining arithmetic impossibilities (~1 evening)

`data/validation.csv`, checks `EL<=attachment_probability` / `severity<=1` /
`exhaustion<=EL`. Three distinct one-off capture errors, no shared mechanism:

- `mythen-re-ltd-series-2012-2` — Class A EL=1.7 vs AP=0.36; one of the two is
  a mis-capture, read the page to see which.
- `vitality-re-vii-ltd-series-2016-1` — EL=0.18 vs AP=0.03. Health deal;
  sibling of the fixed benefit-ratio class but a different sentence shape.
- `queen-street-vi-re-ltd` — EL=2.71 vs AP=1.8, unlabelled tranche.
- `vita-capital-vi-limited-series-2021-1` — EP=1.16 > EL=0.75.

## 2. The 49 sum-final mismatches (~2 evenings, or accept)

`tranche_sum_check == MISMATCH` in `deals.csv`. Spot-checks say two families:

- **Headline-basis**: Tier-1 "Size" includes term loans (Merna, +$122m) or
  excludes swaps (IBRD), so parts *correctly* fail to equal it. Right fix is
  representation, not parsing: `headline_basis` + `notes_principal` +
  `other_instruments` columns (Fable round-4 design note; partially built).
- **Invisible tranches**: a class the label detector never finds, so the sum is
  short. Overlaps with the 61 `tranche_count_matches_prose` undercounts.
  Start with deals where stated count > found count AND sum is short.

## 3. Recall on maturity/term (~1 evening, high analysis value)

850/1,311 deals have no maturity — mostly genuine (sampled 5/6 page-silent),
but the sixth ("Successor X") had discount-note phrasing worth a look, and the
maturities-dashboard comparison says we hold 69% of the $62.4bn forward
schedule. Each recovered maturity directly improves the outstanding line in
`net_supply.py`. Look for: "risk period ending", "notes due", "X-season".

## 4. Lifecycle extractor breadth (~1 evening)

`apply_tranche_lifecycle` was built from ONE deal (Citrus 2015-1) plus the
losses table. `losses.csv` has 60 joinable rows; run the cross-check (deal-page
lifecycle vs losses row) over all of them and extend the clause patterns for
whatever phrasings miss. The cross-source disagreements ARE the worklist.

## 5. Derived entity columns beyond agents (~half evening)

`agents_entities` exists. Same treatment for `ratings` (agency + per-tranche
grades — "DBRS Morningstar rated BBB (sf); Moody's Baa2 (sf)") and
`perils_covered` (peril list + geography). Verbatim stays canonical.

## 6. Non-USD conversion convention (~half evening, analysis-side)

$4.45bn of sizes are non-USD without a parenthetical equivalent
(`net_supply.usd_millions` tags them `non_usd_unconverted`). Decide an FX
convention (issue-month rate?) instead of dropping them.

## 7. Known-opens from reviews never closed

- `coupon of X% to Y%` returns the low end (round-3; Lion I was right by luck).
- Mutation table said several guards deletable-green (round-3 report §Priority D
  in `REVIEW_ROUND3.md`, local); re-run the mutation sweep after any batch.
- Sibling registry audits Tier-2 fields only; extend to tranche EL/spread once
  those matter downstream.
- 663-vs-723 UN-CAT CUSIP count discrepancy (analysis repo, WRDS manifest).

## 8. Second labelling round (when a human volunteers)

Protocol fixes learned in the pilot, already applied to the sheet generator:
all nine Tier-1 fields, lifecycle fields, `price_guidance` /
`exhaustion_probability` / `attachment_point` at tranche level. Remaining
rules: **label only what the page states** (no arithmetic, no outside
knowledge), **format date cells as text** before typing (Excel ate two years),
and the labeller writes the verbatim cell, not the extracted entity.
~12 deals stratified by decade ≈ 2 hours; `src/build_labelling_set.py` then
`src/score_labels.py`.

## Standing rules (hard-won, do not relearn)

- Honest `None` beats a plausible wrong value; delete weak patterns, don't
  repair them.
- One derivation, one place — five duplicated-derivation bugs and counting.
- Assert every patch anchor; verify the mutation actually applied; never trust
  a green suite whose check count didn't move.
- Random samples, fixed seed; the hand-picked pages flatter you.
- Verbatim is canonical; derived columns are additions, never replacements.
