# Parser backlog — pick-up-when-bored list

State when written: 1,311 deals parsed, 1,263 golden checks, 19% of deals carry a flag,
issuance validated to 0.6% against the publisher. Nothing here blocks analysis;
every item is a *visible, flagged* gap, ordered roughly by value-per-hour.
Method that has worked every time: read the page, verify the mechanism, fix the
class not the instance, pin it in `tests/test_golden.py`, mutation-test the pin.

## 1. Arithmetic impossibilities — three of four read 2026-09-15

`data/validation.csv`, checks `EL<=attachment_probability` / `severity<=1` /
`exhaustion<=EL`. Read against their pages:

- `queen-street-vi-re-ltd` (EL 2.71 vs AP 1.8) and `mythen-re-ltd-series-2012-2`
  (Class A EL 1.7 vs AP 0.36): ONE pattern gap. "attachment probability for
  the transaction is 3.87%" / "for the Class A tranche of notes is 2.16%"
  were not accepted (only "for the notes"), so the next per-peril figure was
  captured. Fixed; both now order correctly.
- `vitality-re-vii-ltd-series-2016-1` (EL 0.18 vs AP 0.03): the 0.03% is
  Vitality Re II's, cited without a year or series. Numbered vehicles are
  now series tokens ("RE II" vs own "RE VII", from deal name and slug), so
  the sentence is a foreign reference. AP is None; the 0.18% EL is still
  Class B's read into Class A's window (tranche-window bleed, unfixed).
- `vita-capital-vi-limited-series-2021-1` (Class B EP 1.16 > EL 0.75): the
  PAGE says AP 1.06%, EP 1.16%, EL 0.75%. EP above AP is impossible; this is
  a source typo, and the check is doing its job. Leave flagged.
- Earlier the same day: "probability of attachment of 21.38%" (Residential
  Re 2013-2) and "4% of expected losses, followed by energy at 5.2%"
  (Tradewynd 2013-1). Read the rest of the list the same way.

## 2. Sum-final mismatches — 45 -> 27 on 2026-09-15 (OK 1104 -> 1146)

`tranche_sum_check == MISMATCH` in `deals.csv`. Read against their pages,
the 45 were four families, two of them mechanisms and now fixed:

- **Stale per-tranche finals** (Sakura 2021-1, Blue Ridge 2023-1, Tomoni
  2024-1, Hypatia 2020-1, Acorn 2024-1): the upsizing is stated for all
  tranches at once -- "each tranche now targeting $200 million", "Both
  tranches of notes priced at $100 million", "the two $150 million
  tranches" -- with no class label, so no tranche window saw it.
  `_per_tranche_amount` reads the clause (each-scoped amount, "both/all
  tranches", counted tranches), binds it as `*EACH*`, and the parts-vs-whole
  solver offers it to every class. Only a unique reconciling combination is
  applied.
- **The headline as a tranche** (Chartwell 2025-1 Class C = $330m, Compass
  Re II Class A = $300m, East Lane VII both classes = $150m, Mayflower
  Class A = $150m): `equals_deal_total_accepted` existed for Residential Re
  2020-1, where Class 12 "will not be issued" and the total IS Class 13.
  Now gated on a dropped-class cue (`TRANCHE_DROPPED_RE`); without one the
  tranche is an honest None and the sum is n/a.
- **Headline-basis** (unchanged): mortgage ILS with exact amounts vs a
  rounded headline (Bellemeade, Radnor, Eagle, Oaktown, Home Re), IBRD
  FONDEN 2020, Horse Capital. Representation, not parsing: `headline_basis`
  + `notes_principal` + `other_instruments` columns (partially built).
- **Finals the label binder did not read** (3264 2025-1 "The Class A notes
  were priced to provide $100 million of cover", Tailwind 2017-1 "this
  tranche has now grown to $150 million" 130 chars after its label, Bonanza
  2023-1 "$65 million from the Class B notes"): fixed in `mentions.py` --
  size cues for "priced to provide / grown to / upsized to / offering /
  of cover", class scope bounded by the sentence rather than 120 chars, and
  a tight forward form ("$X of/from the Class B notes") that wins over a
  label behind the amount. Spectrum 2017-1, Torrey Pines 2017-1 and
  Matterhorn 2026-3 still have no unique reconciling combination.
- **Phantom and withdrawn tranches** (read 2026-09-15 from the 20 "parsed >
  stated" count findings): bare parent labels beside their own sub-labels
  ("the Class A tranches" on a page that sizes A-1 and A-2: Kilimanjaro
  2018-1, Cerulean 2019-1) are dropped and their per-tranche "each" amount
  routed to the sub-labels; "class is as yet unsized" no longer grows a
  "Class IS" row (CLASS_RE is case-insensitive; function words added to
  CLASS_STOPWORDS); a class the prose says was "pulled from the issuance",
  "being pulled and not being issued" or "dropped from this issuance" is
  `tranche_not_issued` with no size, and `check_tranche_sum` counts it as
  zero (Residential Re 2020-1 / 2022-1, Integrity 2022-1). Sanders III
  2022-2's Class C was real ("eventually confirmed as $37.5 million") and
  lost to a payout cue firing on "expected loss of 17.43%"; fixed. Still
  open: Bellemeade 2022-2's $358.4m ceiling as a tranche, twin-series pages
  whose other series' tranches are listed alongside (Kilimanjaro 2018-1
  stays n/a), and the Kilimanjaro II 2017 pages where "three tranches" means
  three classes across two series.

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

## 4. Lifecycle extractor breadth — measured 2026-09-15, still thin

`src/crosscheck_losses.py` now runs the cross-check the note below asked for
and writes `data/validation_dashboards/losses_crosscheck.csv`: the losses
table's 40 settled rows against the page-side `principal_loss_pct`. Result:
1 agree, 0 disagree, 39 page-silent. Before this round it read 4 agreeing,
but every one came from a HEDGED sentence ("The Class B tranche would face a
100% loss of principal", IBRD 111-112) that happened to come true; a
speculation guard (`LC_SPECULATIVE_RE`) now drops those, a single unlabelled
tranche takes clauses with no Class (Silver Crane: "attached the notes and
eroded their full principal"), and the total-loss vocabulary is wider. The
extractor is honest but covers 1 in 40. What the silent pages say, in order
of count, is the worklist:

- Partial, stated as a remainder: "a payout of the remaining $48 million of
  principal" (Claveau 2021-1), "principal ... reduced to $25.45 million"
  (Randolph Re 2024-1), "$10 million still outstanding" (FloodSmart 2020-1).
  Derive pct from tranche size; `loss_basis = "derived:remaining"`.
- "X% loss of principal" appears on 14 pages but 24 carry mark-to-market
  hedges ("bids of 5 cents", "suggesting", "implying"); only an unhedged
  clause is a settlement.
- Recoveries: "made an additional $2.2 million recovery" (Matterhorn
  2020-2). Sponsor-side amounts; the investor loss is size minus returned.
- IBRD Jamaica 2024 never states the settlement plainly; the table does.

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

Takeover follow-up 2026-09-23: two more false settled spreads are closed.
"At final pricing ... upsized by 20%" and "an increase in pricing of 6.7%"
are percentage changes, not spreads. A spread-vs-guidance backstop now exposes
two duplicated Kilimanjaro III 2019 rows where Class B-2 inherited Class A's
15%-16% guidance beside its correct 9.5% spread; B-2's page-stated guidance is
8.75%-9.75%. This is grouped cross-series binding, not a spread-value defect.

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
