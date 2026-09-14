# Parser backlog — pick-up-when-bored list

State when written: 1,311 deals parsed, 967 tests, 19% of deals carry a flag,
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

## 9. Spread series bias (~1 evening, found by dashboard validation)

Our yearly average spread runs +2-4pp above the publisher's in 2019-2020 and
2023-2025 while matching in 2021/2026. EL matches at corr 0.93, so it is the
spread column specifically. Candidates: selection (we only emit spread when
prose states it, skewing to riskier narrated deals), residual price-vs-spread
captures, or coupon-including-collateral-yield phrasings. Start: list emitted
spreads for 2019 and 2023 against their pages; compare an issuance-weighted
mean; check mortgage-ILS SOFR-plus coupons.

## 10. size_change series: level bias remains (~half evening)

**2026-09-14 round one done.** Correlation with the publisher's quarterly
offering-size-change series went 0.22 -> 0.72 (`data/validation_dashboards/
size_change.csv`). The launch column was the problem, not their definition:
launch sizes were being read from amounts that were never sizes (an index
threshold, an investor's AUM, a trigger value, an attachment point, a layer
width, a programme ceiling) or never this deal's (a predecessor named as
"(Series 2022-1)", a target "across the two series", cover held "after this
deal"). Each is now a classified kind or a sentence veto with a golden pin;
25 deals changed, all read against their pages.

What remains is a **level** bias: our quarterly mean runs ~11pp above theirs.
Selection is the likely cause - we emit a delta only when prose states a
launch size, which skews to upsized, narrated deals - plus their metric may
include zero-change deals. Start: compute our series including
`no_size_change_detected` deals as 0 and see if the level closes; if it does,
that is the definition and the remaining gap is recall on launch sizes
(910/1,311 deals have one). Also still open from this round:

- "Both Series target $500m ... each" (Galilei 2016-1/2017-1): a per-series
  target stated with "each" is vetoed as cross-series. Handle "each".
- Kilimanjaro III 2026-1/2026-2: Artemis states ONE target across two
  entries. Launch is None with `launch_target_shared_across_series`; if the
  analysis wants it, splitting is the analysis side's arithmetic.
- Single-tranche deals whose only launch sentence is class-scoped ("$175m
  Class A notes", Aozora 2016-1) have no deal launch by design. Could adopt
  the tranche launch when the deal states exactly one tranche.
- `could secure as much as $358.4 million` (Bellemeade 2022-2) is a ceiling,
  not a launch, and slips the speculative veto (no "maximum").

## Standing rules (hard-won, do not relearn)

- Honest `None` beats a plausible wrong value; delete weak patterns, don't
  repair them.
- One derivation, one place — five duplicated-derivation bugs and counting.
- Assert every patch anchor; verify the mutation actually applied; never trust
  a green suite whose check count didn't move.
- Random samples, fixed seed; the hand-picked pages flatter you.
- Verbatim is canonical; derived columns are additions, never replacements.
