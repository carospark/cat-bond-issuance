# Parser backlog — pick-up-when-bored list

State when written: 1,311 deals parsed, 1,263 golden checks, 19% of deals carry a flag,
issuance validated to 0.6% against the publisher. Nothing here blocks analysis;
every item is a *visible, flagged* gap, ordered roughly by value-per-hour.
Method that has worked every time: read the page, verify the mechanism, fix the
class not the instance, pin it in `tests/test_golden.py`, mutation-test the pin.

## 1. The 7 remaining arithmetic impossibilities (~1 evening)

`data/validation.csv`, checks `EL<=attachment_probability` / `severity<=1` /
`exhaustion<=EL`. Three distinct one-off capture errors, no shared mechanism:

- `mythen-re-ltd-series-2012-2` — Class A EL=1.7 vs AP=0.36; one of the two is
  a mis-capture, read the page to see which.
- Two of the same class fixed 2026-09-15 while pinning other pages: "probability
  of attachment of 21.38%" (Residential Re 2013-2, word order) and "4% of
  expected losses, followed by energy at 5.2%" (Tradewynd 2013-1, a peril
  share). Read the remaining pages the same way.
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

## 3. Recall on maturity/term — round one done 2026-09-15

Was 120/1,311 deals with a stated maturity. The pages say it five other ways;
all now read, in priority order (`_apply_patterns` stops at the first hit):
"Notes due January 8, 2014", "due on", "term/protection/risk period ...
(running/until/through/to) [the end of] Month YYYY", "expires in / due to end
in". A day of the month is stripped so the value stays "Month YYYY". Three
sentence classes are dropped before matching (`MATURITY_EXCLUDE_RE` +
`CLASS_SCOPED_RE`): loss-development EXTENSIONS ("maturity extended again to
December 6th 2018", which the lifecycle fields hold), a PREDECESSOR's expiry
("Lakeside Re I ... expires ... so this deal seeks to replace it"), and one
CLASS's term on a multi-class page. Result: 354 stated maturities,
`maturity_scheduled` (stated, else issue + term) 489 -> 607 of 1,311, zero
`maturity_not_after_issue` violations. Mutation-tested. Still open:

- Per-class "Notes due <date>" lists (Montana Re 2010-1, Isosceles 2023):
  every class carries the same date and the class veto drops them all. Adopt
  the date when all classes agree.
- `stated_derived_mismatch` is now a real signal (month ordinals, not
  strings): where it fires the stated date wins and the term was approximate
  ("three-year" issued March, matures June). 94 deals; read a few.
- Remaining ~700 deals with neither: mostly page-silent (sampled 5/6 before
  this round). Private deals are 332 of them.

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

## 9. Spread series bias — CLOSED 2026-09-15

Was +2-4pp against the publisher's yearly average in 2019-2020 and 2023-2025.
One mechanism: **zero-coupon prices of par in the spread column** — "priced
at 77.25%, so a coupon equivalent of 22.75%" (Residential Re 2019-2),
"settled at 90.5% of par" (Matterhorn 2020-3), "fixed at 88.625% of par"
(Everglades 2023). Eight values at 77-94% among ~380 spreads were the whole
bias; the yearly medians had matched all along. Fix is numeric, not a phrase
veto: `_spread_is_price` drops any spread candidate >= 50% (flag
`discount_price_not_spread`), and a "coupon/spread equivalent of X%" pattern
reads the stated equivalent. Result (`el_spread.csv`): corr 0.90, mean diff
-0.03pp, every year 2012-2026 within 1.2pp. Still open, lower value:

- Recall: spread is emitted for ~1/4 of tranches before 2025 (`n_spread`).
- Guidance endpoints still leak as settled spreads ("guidance reduced to 16%
  to 16.25%" -> 16%): NOT_RANGE only guards the anchors that carry it.
- `price_guidance` still holds prices of par for zero-coupon notes.

## 10. size_change series — round two done 2026-09-15; level bracketed

**Round one (2026-09-14)**: corr 0.22 -> 0.72 by removing launch sizes that
were never sizes or never this deal's (see the golden PAGES comments).

**Round two (2026-09-15)**: the remaining +11pp level was two things.
(a) Launch sizes that were ONE COMPONENT's: tranche labels without "Class"
("$125 million across the ... A-1 and ... A-2 notes", Kilimanjaro II 2025-1,
+300%), per-tranche "each" ("each tranche having a preliminary size of $50m",
Residential Re 2016-1, +400%), counted tranches ("Two $50 million tranches",
3264 Re 2024-1), "This tranche", "annual aggregate" rescuing an enumeration
as a total (Caelus VI 2020), plus "$100m industry loss" as a size and a
sentence split inside "Atlas VI Capital Ltd. Series 2011-1 Class A". 18
launch values changed, all read against their pages; every veto is
mutation-tested. (b) Definition: the dashboard text says the average is over
"all cat bond issues ... where we have the information", so unchanged deals
count as 0%. Counting EVERY deal with a launch state as 0 overshoots (-14pp,
corr 0.33): a single post-pricing size is a final, not a tracked target, and
private deals are most of them. `validate_dashboards.py` now emits both
readings: `ours_changed_mean` (corr 0.75, +8.2pp) and `ours_tracked_mean`
(launch stated AND a later update restated it, unchanged = 0: corr 0.69,
-4.9pp, median -2.5pp). The publisher sits between them; Q2 2021 read deal
by deal is all genuine upsizes, so the residual is their inclusion set, not
our parse. Further work here is recall on launch sizes, not level.

Still open from both rounds:

- "Both Series target $500m ... each" (Galilei 2016-1/2017-1): the sentence
  names both series, so the sibling rule excludes it before "each series"
  (which is now accepted, Kilimanjaro 2018-1) can apply.
- Merna Re II 2022-2 / 2022-3: "Enabling State Farm to source $500 million
  ... with a full 144A cat bond" is the programme total ($300m + $200m) and
  is now the launch of both (-60% / -40%). No phrase cue; the right rule is
  a sibling-registry check "launch == sum of same-year sibling finals".
- Vita Capital IV (programme-level page): "The Series II issuance in May
  2010 saw $50m" is an earlier series of the same entry.
- Kilimanjaro III 2026-1/2026-2: ONE target across two entries, launch None.
- Single-tranche deals whose only launch sentence is class-scoped (Aozora
  2016-1, Successor X "three series of $50m each") have no deal launch.
- `could secure as much as $358.4 million` (Bellemeade 2022-2) is a ceiling.

## Standing rules (hard-won, do not relearn)

- Honest `None` beats a plausible wrong value; delete weak patterns, don't
  repair them.
- One derivation, one place — five duplicated-derivation bugs and counting.
- Assert every patch anchor; verify the mutation actually applied; never trust
  a green suite whose check count didn't move.
- Random samples, fixed seed; the hand-picked pages flatter you.
- Verbatim is canonical; derived columns are additions, never replacements.
