# Handoff

Read `PARSER_BACKLOG.md` first. It is the current state: what is parsed, what
is validated, and everything still worth fixing, ordered by value per hour.

## Checkpoint (2026-11-18): attachment probability and spread recall

A recall round on the two tranche-level fields the atlas's layer view needs
(`src/parse_deal.py`, `TIER2_PATTERNS`). Tests 2343 -> **2611** (378 -> 419
unit; golden pin 1965 -> 2192, ten pages added and every new spread value
adds per-tranche guard checks). `data/tranches.csv` 2051 -> 2052 rows; no
existing value of any field changed or was lost.

Spread (`spread_risk_margin`): 519 -> **887** tranches, 372 -> 577 deals
(core property cat 321 -> 512 of 834). Method as always: 163 core 2019-2022
deals read, 89 without a settled spread, 83 of whose pages state one. One
mechanism dominated: the settlement reported as a BAND of guidance with the
number after it ("pricing has now been fixed at the upper-end of initial
guidance, at 5.5%", "settled at the top-end of guidance, at 4.75%", "priced
at the low-end of reduced guidance, at a 6.75% initial coupon spread",
"fell to below the low-end of guidance, settling at 5.75%", "settled at the
low-end of guidance, to offer investors a 6.75% coupon", "fixed in the
bottom-half of guidance at 4.75%", "priced at the top of elevated guidance,
at 16%"); the old anchors needed the number right after "settled/fixed at".
Nine anchors, in order after the originals so they only fire where nothing
fired before: the band form; a settlement verb then "at"/"of" within 40
characters ("coupon was finalised at 5%", "priced its $95 million of notes
at 2.9%", "finalised at the 8.5% coupon level", "the fixed level of a 14%
coupon"); "at a fixed 7.75%"; the offered coupon after a settlement verb
("priced to pay investors a 6.9% coupon", "settled down some 16% from the
initial midpoint of spread guidance, to offer a 6% coupon"); "the initial
risk interest spread to be paid to investors is 7%"; the per-class list
"Class 11 - $35 million; coupon 12.5%"; and zero-coupon equivalents stated
number first or as a "coupon equivalent price/premium of" ("settled at 88%
of par, so a roughly 12% coupon equivalent"; the price lands first and
`_spread_is_price` drops it). Every anchor carries the same guards
(`SETTLED_PCT`): not a range endpoint in either direction, not a change
("at 2.25%, which represents a 25% drop" reads 2.25%; "an increase in
pricing of 6.7% from the mid-point" reads nothing), not one entry of a
per-class pricing list ("finalised at 11.25% for the A-1 notes, 4.5% for
the B-1 notes": those labels are not windowed, so the first value would
have gone to a single unlabelled row), not expectation language ("pricing
looks set to settle at 8.25%", "looks likely to end up at the top-end, of
4.5%" stay None), and no loss or probability between the verb and the
number. Backward references are excluded as before (Phoenician 2020-2 does
not take 2020-1's 3%; Residential Re 2019-1 Class 13 does not take a 2018
deal's 3.25%). Every anchor and guard is mutation-tested against
`unit_spread_recall` (41 synthetic sentences quoting the pages); one
redundant anchor and one redundant guard were deleted when the sweep showed
them untested. Hand check: 32 of the 367 new values sampled at random
against their pages, 32 right, plus the five validation findings the new
values raised (Sanders III 2022-1, Integrity 2017-1, Topanga 2021-1,
Casablanca 2020-1, Marlin 2022-1), all five the page's own numbers
(elevated or zero-coupon pricing, a 15% fixed coupon on a low-EL tranche).

Class labels of four letters. The one wrong value the sample found was
Gateway Re 2026-1 Class A at 3.5%: the page's Class AAAA notes were not a
label (`CLASS_RE` and the label binders allowed `[A-Z]{1,3}`), so AAAA's
"priced at $160 million in size, with a spread of 3.5%" sat in Class A's
window. `{1,4}` in `mentions.py` and `parse_deal.py`; Class AAAA is now its
own row with $160m and 3.5%, Class A reads its own 10%, and the deal's
tranche-sum check goes from "incomplete" to OK (five sizes, -0.7%). One new
tranche row, 2051 -> 2052; nothing else moved.

Against the publisher's yearly average spread (`validate_dashboards.py`,
`data/validation_dashboards/el_spread.csv`, 2011-2026): mean absolute
difference 0.54pp -> 0.40pp; 2022 8.85 -> 8.35 (publisher 8.34), 2023 8.25
-> 8.85 (8.90), 2020 6.63 -> 7.14 (7.46), 2017 5.57 -> 6.15 (6.51); 2016
moved away, 6.38 -> 7.87 (7.04), on 12 -> 27 tranches. Per year for core
deals:

| year | core tranches | AP before | AP after | spread before | spread after |
|---|---:|---:|---:|---:|---:|
| 2012 | 42 | 22 | 22 | 14 | 19 |
| 2013 | 39 | 32 | 32 | 14 | 26 |
| 2014 | 42 | 28 | 28 | 23 | 30 |
| 2015 | 31 | 25 | 25 | 14 | 22 |
| 2016 | 42 | 31 | 31 | 10 | 24 |
| 2017 | 73 | 62 | 62 | 20 | 47 |
| 2018 | 50 | 41 | 41 | 8 | 30 |
| 2019 | 43 | 12 | 13 | 12 | 21 |
| 2020 | 73 | 5 | 6 | 33 | 66 |
| 2021 | 66 | 11 | 11 | 30 | 59 |
| 2022 | 80 | 37 | 37 | 25 | 61 |
| 2023 | 94 | 85 | 86 | 23 | 78 |
| 2024 | 104 | 98 | 98 | 45 | 82 |
| 2025 | 133 | 131 | 131 | 84 | 116 |
| 2026 | 131 | 118 | 119 | 92 | 107 |

Attachment probability: 802 -> **806**. This one is the source's gap, not
the parser's: of the 115 core 2019-2022 deals without an attachment
probability, two pages state one ("a 5.9% attachment probability and a
3.65% expected loss", Hexagon II 2019-1, number before the cue; "attachment
probability and expected loss of 0.888%", MetroCat 2020-1, one number for
both), and 113 never do. Both phrasings are read now (plus MetroCat 2023-1
and one 2026 tranche); the 2019-2022 layer view has to band by expected
loss (stated on 1,037 tranches) or stay thin. The deal-level
`spread_history` column was checked for a single-tranche adoption rule and
has nothing to adopt: its non-guidance entries are the same "priced to pay
... risk margin of" sentences the tranche anchors already read.

`data/validation.csv` 272 -> 286 rows: `riskier_tranche_pays_more` 15 ->
22, `spread_outside_guidance` 2 -> 4 (all read, all the page's numbers,
above), `spread>EL_plausibility` 3 -> 3; Gateway 2026-1's two size
findings closed. Precision risks accepted, named: a sentence that moves
guidance to a single point ("the pricing has moved to the upper-end of
guidance, at 9.5%", Hestia 2022-1; "price guidance moved to the low-end of
4.5%", Torrey Pines 2025-1) is read as the settlement, and in every case
read the final equalled it; "expected to settle ... with pricing at the
mid-point of 8.75%" (SD Re 2021-1) reads the then-current value. Left
open: Gateway 2025-1 Class C-1 carries Class C 2's 9.5% because a label
with a space inside ("Class C 2") is not a window (pre-existing; its own
"8.25% equivalent spread" anchor exists and would read right once the
window splits); the 24 multi-term deals without class labels are unchanged.

## Checkpoint (2026-11-17, night): class-level repayment; loss timing as an option

Two more roll-forward items (`src/roll_forward.py`). Tests 2307 -> **2343**
(342 -> 378 unit; golden pin 1965). Dashboards regenerated on the default
settings; the committed numbers below are the defaults.

Class-level repayment (`--cusip-classes PATH`, default the analysis
repository's `data/bridge_cusip_classes.csv` when present;
`--no-cusip-classes` off). `load_class_maturities` joins the bridge's
TRACE maturity per CUSIP with the holders' unanimous class label (588
CUSIPs, 391 deals) into one TRACE month per (deal, class), the month shared
by most of the class's CUSIPs, latest on a tie, flag
`class_months_disagree=<classes>` when they differ. `tranche_sizes_usd`
reads tranches.csv's per-class sizes through the same USD conversion as
the deal size. For a multi-term deal whose maturity is TRACE's
(`trace_maturity_tranches_disagree`), `class_split` repays each labelled
class with a USD size at its own month and the rest at the majority month
(`maturity_split=class_level:k_of_n_classes`, with
`_unlabelled_remainder` when a bridged CUSIP has no label or the sizes do
not reach the deal size). Guards: class sizes above the deal size by more
than 0.5% fall back to the whole deal at the majority month
(`maturity_split=fallback_class_sizes_exceed_deal:X_of_Y`); within 0.5%
they are capped to it; no labels -> `majority_no_class_labels`; labels
with no matching sized tranche -> `majority_no_class_size_match`. A
write-down or extension scales every class in proportion to the deal's
remainder, and a class month before the last settled loss moves to it,
as the deal's repay month does. Classes maturing at the majority month add
nothing and stay in the remainder. `outstanding_deals.csv` carries the
events in `class_repay` ("B1@2028-04=100.000"); `monthly_flows` and
`upcoming_maturities` emit them. Labels are normalised to letters and
digits ("Class A-1" = "A1").

Of the 54 multi-term deals in the book: 24 take the class path (19 with a
class off the majority month, 22 class events; 5 whose labelled classes
all sit at the majority month), 24 have no class label in any holder
title (Residential Re's numbered classes, the pre-2010 programmes), 1 has
labels but no sized tranche of that name, 5 keep the page's stated date
and are not split. The class events: Caelus Re VI 2020-1/2 B1 $92m at
2024-06 (scaled by its write-down), Sanders Re II 2025-1 B1 $100m at
2028-04, Sanders III 2026-1B and IV 2026-1A $275m each at 2030-04, Mona
Lisa 2025-1 B $175m at 2028-01, Galileo 2023-1 B $175m at 2026-01, Alamo
2024-1 C $400m at 2026-06, Ursa Re II 2025-2 F/G $500m at 2028-06, and
the rest.

| ($m, ex-mortgage) | whole deal at majority month | class-level (now default) |
|---|---:|---:|
| outstanding minus publisher 2023 | -757 | -840 |
| 2024 | +1,020 | +960 |
| 2025 | +2,274 | +2,012 |
| 2026 (at 2026-08) | +4,791 | +3,916 |
| 2019-2022 | unchanged | unchanged |
| mean absolute gap 2010-2026 | 959 | 894 |
| upcoming maturities, mean absolute quarterly difference | 630 | 581 |
| upcoming maturities, window total (publisher 62,372) | 65,751 | 65,426 |

Loss timing (`--loss-timing loss|settlement`, default `loss`, the
behaviour to date). Under `settlement`, `settlement_month` places a
settled write-down at the month the row says it was paid: a "N months" or
"N years" `time_to_resolution` after the loss month
(`loss_timing=settlement:+Nm`); a dated phrase in either cell, "principal
reduced to zero at end of Feb 2023", "notes delisted with zero balance
Mar. 2019", "redeemed in April 2026" (`:dated`); "paid out in 2020" /
"loss payments finished in 2020" to that December (`:year`); else the loss
month, flagged `loss_settlement_unknown`. Of the 83 settled, linked,
amount-bearing rows, 36 get a settlement month and 47 do not ("Ongoing",
"?", weeks-long resolutions, no statement). `build(loss_timing=...)` and
the CLI pass it through; `--no-write` prints the comparison without
touching the dashboards, which is how the settlement column below was
produced. Nothing else changes under either setting.

| year | loss (default) | settlement |
|---|---:|---:|
| 2010 | -455 | +140 |
| 2011 | -202 | +1,214 |
| 2012 | -372 | +338 |
| 2013 | -707 | -311 |
| 2014 | -249 | +56 |
| 2015 | +818 | +818 |
| 2016 | +452 | +967 |
| 2017 | -1,014 | -248 |
| 2018 | -1,510 | -141 |
| 2019 | -347 | +832 |
| 2020 | -24 | +390 |
| 2021 | -706 | -15 |
| 2022 | +612 | +1,046 |
| 2023 | -840 | -602 |
| 2024 | +960 | +1,207 |
| 2025 | +2,012 | +2,259 |
| 2026 | +3,916 | +3,916 |
| mean absolute gap 2010-2026 | 894 | 853 |

Reading it: settlement timing closes the 2017-2021 gaps the losses read
opened (Frontline, Caelus, Residential Re principal held until paid) and
moves the stock above the publisher in 2010-2012 and 2019-2020, where
the publisher evidently removed those losses earlier than the resolution
column says they settled. Neither setting is uniformly closer; the choice
is Caro's, and the default stays `loss`. The two runs are reproducible
with `python src/roll_forward.py --no-write` and `--loss-timing
settlement --no-write`.

Left open: the 24 multi-term deals with no holder-title class labels
(Residential Re's numbered classes above all; the N-PORT titles for those
name "Class 11" etc. only on some filings, so the labels file could be
extended on the analysis side with a non-unanimous majority rule); the
loss-timing choice; the 47 settled rows with no settlement statement.

## Checkpoint (2026-11-17, evening): the losses table's derived amounts

The analysis repository's read of the fund-mark outliers named eight
distressed deals as missing from `losses.csv`. Five of them are in the
table, linked by name (Caelus Re V 2017-1 and 2018-1, Residential Re
2015-1 and 2016-1, Blue Halo 2016-1); the roll-forward already wrote the
Caelus rows down. The other three (FloodSmart Re 2021-1 and 2023-1, Mystic
Re IV 2025-1) are in no table and their Artemis pages carry no loss,
write-down or extension sentence at all, so the marks are the market's
view and nothing on the page can be parsed for them. What the read did
expose is in the DERIVED columns of `losses.csv` (`src/parse_losses.py`),
fixed here. Tests 2293 -> **2307** (328 -> 342 unit; golden pin 1965).

- "Principal reduced to $19.55m (priced for a further 15% loss of
  principal)" (Residential Re 2015-1 Class 11) was read as a stated loss of
  $19.55m by `AMOUNT_WITH_PCT_RE`; the figure is what is LEFT. Rows with a
  "reduced to" amount are now `partial_loss` with `orig_minus_remaining`
  before the amount-with-percent rule runs: 19.55 -> 80.45; Residential Re
  2016-1 Class 11 "reduced to ~$74.67m" 74.67 -> 0.33 (the tilde had also
  hidden the remaining principal from `_remaining_principal`).
- Seven settled rows stated the amount that left without a "reduced to":
  "$47.87m reduction in principal" (Blue Halo 2016-1 B), "$94.43m paid out"
  (Citrus 2017-1 A), "~$200m paid out" and "$76.37m paid out" (Frontline
  2018-1 A and B), "Approx. $33m recovered by sponsor" (Matterhorn 2020-2
  A), "$3.2m recovered" (Sanders II 2020-1 B), "~$6m in loss payments made"
  (Espada 2016-1), "$14.84m paid out to sponsor" (Manatee III 2019-1).
  `PAID_OUT_RE` reads them (basis `paid_out`). With nothing else stated,
  size less the amount "returned to investors" is the loss (Residential Re
  2016-1 Class 10, $65m less $14m = $51m, basis `orig_minus_returned`).
- "50% of principal returned, leaving $30m extended. Mark to market implied
  ~20% loss" (Residential Re 2019-1 Class 12) was a 50% loss; the share
  returned is not a loss, and an implied percentage is an estimate even in
  a settled row. Now no derived amount (the $30m is an open extension).
- `loss_amount_basis` column added (stated 47, orig_minus_remaining 25,
  paid_out 8, percent 7, orig_minus_returned 1, none 26).
- Roll-forward: principal "returned to investors" is no longer added back
  as a recovery. It is the remainder repaid early, and every live row that
  carries it already nets it in the loss amount (Frontline A: $200m paid
  out beside $25.5m returned), so the add-back double-counted. Only a stated
  reversal (`REVERSAL_RE`: "write-down reversed", "principal restored")
  counts; the flag `principal_returned_to_investors` records the rest.
  Documented in the module docstring.

Settled realised loss in the table: $5.13bn -> $5.63bn (12 rows moved,
listed above). Roll-forward, ex-mortgage ($m): written down 5,084 ->
5,598, recovered 114 -> 0 (the 14 was Residential Re 2016-1's returned
principal, the 100 Residential Re 2021-1's); outstanding minus publisher
2017 -814 -> -1,014, 2018 -1,034 -> -1,510, 2019 +21 -> -347, 2020 +253 ->
-24, 2021 -411 -> -706, 2022 +615 -> +612, 2023 -720 -> -757, 2024 +1,120
-> +1,020, 2025 and 2026 unchanged; mean absolute gap 2010-2026 900 -> 959.
The gap widens in 2017-2021 because the ledger removes a loss at the loss
year (December when only a year is given) while the publisher's chart
keeps extended, loss-affected principal outstanding until it is paid or
redeemed, often years later (Frontline 2018-1's $276m is written down at
2018-12 here). That is a timing convention, recorded in the backlog as the
next thing to decide, not a reason to count less capital as lost.

`validate_annual_deal_counts.py` rerun the same evening (the dashboard was
fetched live): directory 1,311 deals, dashboard 1,236 ex-mortgage, scope
gap 77, 13 of 31 years exact, and one FAIL_MISSING: 2026 shows 94 in the
directory against 96 on the dashboard. The index was crawled 2026-08-29
and the dashboard is today's, so the two are deals listed since the
crawl; a re-crawl of the index is the fix, not the parser. The output is
local (`data/annual_deal_count_validation.csv`, gitignored).

## Checkpoint (2026-11-17, later still): maturity recall round three

Backlog section 3's two open rules, plus the phrasings the audit-sample
deals showed the patterns missing. Tests 2256 -> **2293** (291 -> 328 unit;
golden pin 1965, unchanged: Isosceles 2023 left the maturity-shape checks
and Atlas VI 2010-1 joined them). `deals.csv`, `tranches.csv` and
`validation.csv` rebuilt with `build_review_bundle.py`; roll-forward and
dashboards rerun on the analysis repo's current bridge.

Rules (`src/parse_deal.py`):

- Single-class adoption (`_single_class_maturity`): a page whose ONLY class
  states a maturity adopts it, flag `maturity_from_single_class=<label>`,
  method `regex:maturity_date:single_class`, medium confidence. Guards: no
  second class label anywhere in the prose, no plural "tranches"/"classes"
  and no stated count above one in any sentence about this deal. 12 deals
  adopt (Herbie Re 2025-1 "The single tranche of Class A notes ... to the
  end of May 2027" among them), the 12 the 2026-09-30 count predicted.
- Series-scoped veto (`_series_scope`): on a page covering several series,
  a sentence naming some but not all of them is that series' fact and
  votes like a class. Isosceles 2023-A/C/G now reads no maturity (May and
  June 2024 disagree) instead of June 2024 by accident. Only real series
  ids count as "own" series (year, dash, 1-2 digits with optional letter,
  or a letter with optional digit); the slug token "2039-2025" (Vision
  2039 - 2025-1) does not make a one-series page look like two.
- Extension veto made positional (`EXTENSION_BEFORE_RE`): a sentence is
  dropped only when the extension word comes BEFORE the date. "due to run
  until May 2013 with the possibility to extend in three month increments"
  (Blue Fin Series 3) now reads May 2013; "maturity extended again to
  December 6th 2018" and "extended through to January 2027" stay dropped.
- `DATE_MY` accepts "April, 2015" (Mythen 2012-1's three-class list now
  agrees); `_strip_day` drops the bare comma.
- New maturity pattern: "<cover word> ... from <Month YYYY> to/until/
  through [the end of] <Month YYYY>" (Bonanza 2016-1 "running from June
  2017 to the end of December 2019", Atlas VI 2010-1 "cover ... from
  December 2010 until April 2014"), vetoed when the clause is a policy or
  loan window ("policies written primarily from April 1, 2021 through
  September 30, 2021", Oaktown Re VII; "underwritten from January 2019
  through September 2019", Triangle Re 2019-1; "Covered mortgage loans
  have an effective date from ...", Home Re 2021-2). Those three read as
  pre-issue maturities in the first draft; `maturity_not_after_issue`
  violations are 0.
- New term patterns, number restricted to the word table or digits
  (`TERM_NUM`, so "this year" is never a term): "<n>-year period / deal /
  transaction / cover / protection" (CAT-Mex, Atlas V, Residential Re
  2004), "<n> years of [up to six words] cover / coverage / protection /
  reinsurance" (Nelson Re 2008-1, Blue Ridge 2025-1, Bowline 2022-1), "<n>
  hurricane season(s) source / of" (Hestia 2025-1), and "annual risk
  periods" in the running-across pattern (Ocelot 2023-1). The plural-only
  "hurricane seasons" in the older pattern stays plural: letting it match
  the singular read "Atlantic hurricane season" as a term on five Dodeka
  pages in the first draft.
- `_series_tokens`: a letter series must end at a word boundary and may
  carry one digit. "2011-ltd" in every Residential Re slug used to yield a
  phantom series "2011-L" (harmless until series scoping existed, then it
  dropped Residential Re 2011-2's and 2014-2's stated dates); "2020-XX" is
  no longer "2020-X" (Randolph Re 2020-1's own launch sentence had been
  excluded as foreign); "2020-C1" / "2020-A1" are now tokens (Isosceles
  2020-C1's sibling sentence is excluded again, Cerulean 2020-B gains one
  exclusion; no size moves).

Measured over `raw/` (1,311 deals), before -> after:

| | before | after |
|---|---:|---:|
| stated maturities | 355 | 375 (21 gained, Isosceles 2023 lost) |
| term_length filled | 451 | 644 |
| maturity_scheduled filled | 611 | 763 |
| maturity_not_after_issue violations | 0 | 0 |
| single-class adoptions / class agreements | 0 / 1 | 12 / 2 |
| stated_derived_mismatch | 95 | 121 (more terms to disagree with) |
| other deal-level values moved | | none (Randolph Re 2020-1's size evidence sentence only) |

Roll-forward (ex-mortgage, $m, outstanding minus publisher), commit
535277c -> now: 2019 +21, 2020 +253, 2021 -411, 2022 +615 unchanged; 2023
-620 -> -720; 2024 +979 -> +1,120; 2025 +2,374 -> +2,274; 2026 +4,791
unchanged; mean absolute gap 2010-2026 953 -> 900. Coverage of the
maturity leg by issued dollars: stated 25.7 -> 27.1%, derived 4.0 -> 6.0%,
TRACE 58.7 -> 57.7%, imputed public 8.7 -> 6.8%, private 3.0 -> 2.4%;
known from page or TRACE 88.4 -> 90.8%. Stated vs TRACE: kept 176 -> 190
($43.6bn -> $45.9bn), derived replaced by TRACE 189 -> 283, imputed
replaced 318 -> 209, overrides unchanged (6 later-TRACE, 1 page-later
kept, class-vote overrides 1 -> 2). Upcoming maturities: mean absolute
quarterly difference 649 -> 630, window total unchanged.

## Checkpoint (2026-11-17): TRACE maturities in the roll-forward; the cancelled-status false positive closed

Two items from the 2026-10-25 "left open" list. Tests 2227 -> **2256**
(262 -> 291 unit; the golden pin is unchanged at 1965). Both repositories
now live under `~/projects/`. Two commits: the first carried a symmetric
stated-vs-TRACE rule and the bridge as it stood that morning; the second
(same day) made the rule one-sided and re-ran on the bridge after the
analysis side moved CUSIP 577092AR0 (TRACE maturity 2027-01-25) from
Matterhorn Re 2022-1 to Matterhorn Re Argon 2022-1. The numbers below are
the second run's.

### TRACE maturities as a maturity tier (`src/roll_forward.py`)

The companion repository's strict bridge (`data/bridge.csv`, one row per
Artemis deal x TRACE CUSIP, 1,196 rows, 700 deals) carries the legal final
maturity of every bridged CUSIP. `load_trace_maturities` reduces it to one
month per deal: the month shared by the most of the deal's CUSIPs, the
latest on a tie. 645 deals have one month; 55 do not (Residential Re's
one-year and four-year classes and the like; span 1 to 49 months, median
24), and those carry `trace_maturity_tranches_disagree=<span>m`. The bridge
is read with `--trace-maturities PATH`, default the sibling checkout's
`data/bridge.csv` when it exists; `--no-trace-maturities` reproduces the
2026-10-25 output leaf for leaf (checked by diff). `net_supply.py` passes
the same options through. The parser runs without the analysis repository.

Precedence per deal, recorded in `maturity_source` and the flags, with the
page's own maturity kept beside it (`page_maturity_month`,
`page_maturity_source`, `trace_maturity_month`, `trace_vs_page_months` in
`data/outstanding_deals.csv`):

- stated on the page: kept when TRACE is within 3 months
  (`trace_corroborates_stated=+Nm`; 176 deals, $43.6bn: 96 at +0, 80 at +1,
  so the page's month is the risk-period end and the legal final sits a
  month later in 45% of them); replaced by TRACE only when TRACE is LATER
  than the page by more than that (`trace_maturity_overrides_stated=+Nm`,
  6 deals, $1.1bn: Sanders III 2022-3 +48m, ResRe 2023-2 +37m, Casablanca
  2020-1 +25m, Bonanza 2023-1 +24m, Vita IV +12m, Queen Street X 2015 +6m,
  every one a one-year class's or a predecessor's date read as the deal's)
  or when the page date was a per-class vote (`_class_vote`; Montana Re
  2010-1, same month). A page date later than TRACE stands and is flagged
  (`page_later_than_trace=+Nm`; 1 deal, Kilimanjaro II 2024-1 +35m: the
  bridge holds only the two 2025 classes of a page that states July 2028,
  and a deal matures with its longest class). The asymmetry is the rule,
  not a patch: the bridge can miss a deal's long classes, it cannot invent
  a later one.
- derived from a stated term: TRACE replaces it
  (`trace_maturity_replaces_derived=+Nm`; 189 deals, $52.4bn; 63 at +0, 84
  at +1, 10 at +2, 6 at -1; 23 beyond 3 months, the largest being page
  terms read off another sentence -- Fidus 2021-1 "twelve-year" -121m, Ursa
  II 2021-1 "nine month" -63m, Matterhorn 2022-2 "6 month" -48m, Gateway
  2023-1 and Alamo 2021-1 "one-year" +24m/+25m -- and multi-term series
  where the majority class is the long one, ResRe 2016-2 +37m, Bonanza
  2020-2 +36m; the two-month cases are in `data/validation_dashboards/trace_maturities.csv`
  as aggregates).
- nothing on the page: TRACE replaces the imputed term
  (`trace_maturity_replaces_imputed`; 318 deals, 310 public $76.6bn and 8
  private $1.3bn, Matterhorn Re Argon 2022-1 among them since the bridge
  fix: imputed 2023-04 -> TRACE 2027-01; Matterhorn Re 2022-1 keeps
  2025-03). What the imputation had been getting wrong: the public
  terms TRACE gives are 36 or 37 months for 141 of the 310, longer than 42
  for 96 ($27.6bn, the four- and five-year deals the 2026-10-25 note
  expected), shorter than 30 for 40 ($7.0bn); size-weighted mean 40.6
  months against the flat 36.
- a TRACE month at or before the issue month is rejected
  (`trace_maturity_rejected_not_after_issue`, 0 deals today) and the deal
  is imputed as before.

Coverage of the maturity leg by issued dollars, ex-mortgage, before ->
after: stated 26.1% -> 25.7%, derived from term 26.7% -> 4.0%, TRACE 0 ->
58.7% (514 deals, $131.6bn), imputed public 43.7% -> 8.7% (450 -> 136
deals, $97.9bn -> $19.4bn), imputed private 3.5% -> 3.0%. Known from a page
or TRACE: 52.8% -> 88.4%.

Outstanding vs the publisher ($m, ex-mortgage; roll-forward of 2026-10-25 ->
with TRACE): 2010 -2,076 -> -455; 2011 -1,253 -> -202; 2012 -857 -> -372;
2013 -1,523 -> -1,203; 2014 -1,764 -> -549; 2015 -970 -> +908; 2016
-2,263 -> +452; 2017 -3,259 -> -889; 2018 -2,114 -> -1,109; 2019 -1,594
-> +21; 2020 -4,678 -> +253; 2021 -3,291 -> -411; 2022 -2,468 -> +615;
2023 -3,805 -> -620; 2024 -2,181 -> +979; 2025 +724 -> +2,374; 2026 (at
2026-08) +4,121 -> +4,791. Mean absolute gap 2010-2026: 2,291 -> 954. (The
first commit's run had -770 / +829 / +2,024 / +4,441 for 2023-2026; the
one-sided rule holds Kilimanjaro II's $200m to 2028-07 and the bridge fix
holds Argon's $150m to 2027-01, +150 in 2023-2024 and +350 in 2025-2026.)
The
2020-2024 shortfall the 2026-10-25 note attributed to 36-month imputation
of 48-to-60-month cohorts is gone; what is left is 2025-2026 running high,
and the upcoming-maturities check says where: against the publisher's
chart (Q3 2026 to Q2 2030) our scheduled remainder is now 65,751 vs 62,372
(was 67,041), mean absolute quarterly difference 649 (was 1,621), Q4 2026
+891 (was +2,626), and the largest remaining quarter is Q2 2027 at +2,228
(was +1,733) with Q3 2029 at -1,435. Those are TRACE legal finals, so the
residual is either the publisher retiring notes at the risk-period end
rather than the legal final, or deals the publisher's chart does not
carry; `data/validation_dashboards/maturities.csv` has the quarters.
`legacy_3y` in `outstanding.csv` still reproduces the old rule from the
page alone (TRACE did not exist for it), so `double_subtraction_m` keeps
its meaning; `no_netting` and `netted` use this book's maturities.

Convention, not fact: a deal with a one-year and a four-year class is held
in full to the majority class's month. Tranche sizes are in `tranches.csv`
but the bridge does not say which CUSIP is which class, so the split is not
done; 55 deals, flagged.

### `deal_status = cancelled` (`src/parse_deal.py`)

All five "cancelled" statuses were false positives and each was one of
three vetoes the size reader already applied elsewhere. `_deal_cancelled`
now takes a `CANCELLED_RE` hit as a deal fact only when the sentence is
not tranche-scoped (a class label, or "tranche(s)" unless "all/both/every
tranches" or "the entire deal"), not a sibling or predecessor reference
(`_is_backward_reference`: "The Series 2024-2 notes ... withdrawn" on the
Everglades Re II 2024-1 page; "that issuance was cancelled ... UnipolSai's
2022 cat bond" on Azzurro Re II 2024-1), and not an earlier attempt ("a deal
that was not completed earlier this year", Titania Re 2024-1, which
completed in November). Atlas IX 2013-1 ("one tranche of notes has been
pulled completely") and Tradewynd 2013-2 ("One of the four tranches ...
withdrawn") are the tranche cases. Gateway 2024-3 ("this Gateway Re 2024-3
... issuance has been cancelled") and Queen Street X ("was not completed";
Tier-1 "Not issued") still read as terminal.

Effect on the tables (`build_review_bundle.py`, offline): exactly the five
deals change `deal_status` to `issued` (1,300 issued, 11 not_issued, 0
cancelled); four of them regain the derived and scheduled maturity the
status had blanked (Everglades May 2027, Tradewynd Dec 2014, Azzurro April
2028, Titania November 2027; Atlas IX states none); Azzurro's single
tranche gets its `final_from_tier1` size and its sum check goes n/a -> OK.
`validation.csv` is unchanged (272 findings). Issuance vs the publisher
does not move: the sums come from `index.csv` and always included the
five. The roll-forward's `deal_status_cancelled_ignored` flag count goes
5 -> 0; its stock did not move, since TRACE covers those deals.

Also found while rebuilding: the tables on disk predated the 2026-10-21
separate-series-totals rule for the Merna Re II 2022-2/2022-3/2024-1,
Merna 2025-1 to 2025-4 and Seaside 2017-1 pages (HEAD's parser gives the
new values, checked against the committed `parse_deal.py`), so
`size_change.csv` Q2 2022 moves from 12 deals at mean 19.3% to 10 at 33.2%
with this rebuild. Not a change in this commit's code.

- Tests: 9 `deal-cancelled` unit checks on the five false-positive
  sentences, the two true positives and two synthetic edges; 19 TRACE
  checks (the deal-level rule, tie, blank dates, path resolution, each
  precedence outcome including the page-later case, the rejection, the
  no-`deal_url` case, the page columns, the legacy fallback on both an
  imputed and a replaced stated deal, coverage, the check table).
  Mutations, each run through the whole suite: tranche veto off (2 fail),
  earlier-attempt veto off (1), sibling veto off (2), tolerance 0 (3), tie
  to the earliest month (1), derived not replaced (2), legacy variant
  reading TRACE instead of the page (1 after the stated-replaced pin was
  added; 0 before it, which is why it was), stated rule made symmetric
  again (3).

Left for Caro: decide whether the 55
multi-term deals should be split by class size once the bridge carries
class labels; `validate_annual_deal_counts.py` was not rerun (its
cumulative-issuance dashboard is not in the cache and the run was offline;
it does not read `deal_status`).

## Checkpoint (2026-10-25, later): outstanding principal as a deal-level roll-forward

`src/roll_forward.py` replaces the approximation in `net_supply.py` (issue +
3 years where no maturity was stated, settled losses subtracted at the loss
date and the full size subtracted again at maturity). Per deal, monthly:
issued at the issue month; written down at the loss month (`losses.csv`,
tranche rows summed to the deal, year-only dates placed in that December and
flagged); recoveries returned to investors added back; the remainder repaid
at the scheduled maturity, or at the last loss settlement if that came
later; a stated extension carries its portion to the stated date; an
unresolved loss with no date is carried past maturity to the as-of month or
36 months after the scheduled maturity, whichever is first (flag
`extension_open_capped_36m`). Stock is measured at each December and at
2026-08 for the final year, the directory snapshot month. `net_supply.py`
now takes its stock from this module; `data/net_supply.csv` has
`our_repaid`, `our_written_down`, `our_recovered` in place of `our_matured`
and `our_lost`.

- Loss linkage: the losses table links 60 of 114 rows to a deal page itself.
  A normalised-name match (tranche suffix stripped, series roman numerals
  mapped, "Seaside Re 2018-2" read as a series) links 53 more; 1 row stays
  unlinked and is written down at market level. By settled dollars: $2,443m
  table-linked, $2,688m name-matched, $0 unlinked.
- Coverage of the maturity leg by issued dollars, ex-mortgage: stated
  26.1%, derived from a stated term 26.7%, imputed 47.2% (public, 36 months,
  450 deals, $97.9bn, 43.7%; private, 12 months, 208 deals, 3.5%). The
  imputed terms are the medians of the stated issue-to-maturity span by
  class (36.5 and 12 months). The quantity the publisher's 51.5% referred to
  is `stated + derived` = 52.8% here (343 stated, 237 derived). A vintage-
  specific imputation (size-weighted mean known term by issue year,
  `--impute vintage`) was run as a sensitivity and rejected: it overshoots
  the publisher by 4.0bn in 2018, 6.5bn in 2025 and 9.6bn in 2026, where the
  flat median is within 1bn in 2025.
- Outstanding vs the publisher ($m, ex-mortgage), old approximation ->
  roll-forward: 2019 -1,976 -> -1,594; 2020 -6,075 -> -4,678; 2021 -5,457
  -> -3,291; 2022 -5,345 -> -2,468; 2023 -7,414 -> -3,805; 2024 -6,167 ->
  -2,181; 2025 -4,864 -> +724; 2026 (at 2026-08) -1,664 -> +4,121. Holding
  the new book fixed and only switching the netting of write-downs off and
  on, the double subtraction alone accounted for 2,436 (2020), 3,024 (2021),
  3,395 (2022), 4,170 (2023), 4,478 (2024), 4,815 (2025) and 4,934 (2026) of
  the old gap: 40 to 56% in 2020-2023, 73% in 2024, 99% in 2025, and more
  than the whole gap in 2026, where the rest of the old rule (36 months for
  every deal without a maturity, private ones included; no extensions)
  had been pulling the other way. `data/validation_dashboards/outstanding.csv`
  carries `legacy_3y`, `no_netting`, `netted` and `double_subtraction_m` per
  year beside the publisher series and the coverage shares.
- What remains, by sign. 2020-2024 still 2.2 to 4.7bn low: 2014-2017
  vintages carry known terms of 38 to 60 months size-weighted, so 36 months
  retires the imputed half of those cohorts a year early; the publisher
  also keeps unresolved notes on its books longer than the cap in some
  cases. 2026 4.1bn high: our scheduled maturities exceed the publisher's
  upcoming-maturities chart (`data/validation_dashboards/maturities.csv`,
  Q3 2026 to Q2 2030) by 4.7bn in the window, with +2.6bn in Q4 2026 (12
  imputed late-2023 deals, $2.5bn) and +4.7bn in Q4 2028 against -1.8bn in
  Q1 2029 and -3.1bn in Q3 2029: December issues mature in January in the
  stated sample (median offset +1 month, n=16), and recent large deals run
  four years where 36 months is imputed. Stated maturities sit at issue +
  term in 41% of dollars, +1 month in 24%, +2 in 9%, -1 in 8%; the mode is
  used, no offset. The binding input is the imputed 43.7%: the companion
  repository holds TRACE maturity dates for 700 bridged deals, and feeding
  those back as a maturity source would replace most of the imputation.
- Found and not fixed (parser): `deal_status = cancelled` is a false
  positive on all five deals carrying it. Everglades Re II 2024-1 ($1.1bn):
  the page says the 2024-2 sibling was withdrawn; Atlas IX 2013-1 and
  Tradewynd 2013-2: one tranche was pulled; Azzurro II 2024-1 and Titania
  2024-1: no withdrawal language found. The publisher's 2013 and 2024
  issuance totals include all five to within 1m. The roll-forward keeps
  them (`select_book`, flag `deal_status_cancelled_ignored`); the
  `terminal_status` cue in `parse_deal` needs a sibling and tranche veto.
  Backlog item.
- Tests 2196 -> **2227** (231 -> 262 unit): synthetic-deal checks for the
  write-down netting, late settlement, stated extension, open-extension cap
  and carry, recovery add-back, class imputation and vintage map, coverage
  shares, legacy decomposition, book selection, `loss_month`, and the
  name linker on five real loss-table names. Six mutations: netting off
  (5 fail), cap off (2), extension date ignored (2), recoveries off (2),
  year-only losses in June (3), status filter back (1 after the selection
  was factored out so the unit tier reaches it; it was green before that).

## Checkpoint (2026-10-25): issue-month FX for non-USD sizes; mortgage filter fixed in the dashboards

Repository moved the same day from `~/Desktop/cat-bond-issuance` (iCloud
Drive sync; 185 raw pages and 6,008 venv files were evicted) to
`~/cat-bond-issuance`; the venv's embedded interpreter paths were rewritten.
The analysis repository is at `~/cat-bond-flow-analysis`.

- `src/fx_monthly_usd.csv` (tracked, 1,368 rows): USD per unit, monthly
  averages, EUR/CAD/NZD from the ECB reference rates (CAD and NZD as the
  cross of two ECB series), GBP from the Bank of England series XUMAUSS; the
  file header cites both and the download date. `net_supply.convert_size`
  is the single derivation: `usd` as stated, `usd_equiv` where the page gives
  a parenthetical dollar figure (7 deals; the local amount is kept beside
  it), `usd_converted` at the issue-month rate (32 deals, 4,450m local ->
  $4,848m), `fx_rate_missing` when the month has no rate (0 deals today; the
  USD value is None and the local amount and currency are kept), plus the
  existing `unit_missing` (2) and `excluded` placeholders (11). Nothing is
  summed as dollars that is not dollars, and nothing disappears:
  `data/validation_dashboards/size_basis.csv` counts every deal by year and
  basis, and the local `data/fx_conversions.csv` lists each converted deal
  with its rate.
- Found while comparing: `validate_dashboards.py` applied `MORTGAGE_RE` to
  the slug, where "eagle re", "home re", "triangle re" and "sierra ltd" never
  match a hyphenated slug. 23 of 62 mortgage deals stayed in the sums, which
  is the whole +3.8% in the tracked issuance table and the +9 to +20pp
  indemnity gap in 2019-2021. Both charts now exclude by issuer name
  (`ex_mortgage`), as `net_supply.py` always did.
- Issuance vs publisher, 1997-2026, ex-mortgage: tracked file before this
  commit +3.804% signed, 3.96% summed absolute, 11 years over 1%; with the
  filter fixed and no FX -0.070% / 0.586% / 6 years; committed (filter + FX)
  +0.107% / 0.549% / 6 years. FX moved 2019 from -19.0m to -0.3m, 2023 from
  -5.0m to +1.5m, 2024 from -39.3m to -0.8m, 2026 from -30.5m to +1.7m; it
  moved 2005 from +200.0m to +235.7m and 2006 from +251.9m to +304.9m, and
  those two residuals are exactly FCC Sparc 2005 (EUR200m, motor) and
  Crystal Credit 2006 (EUR252m, credit), so the publisher excludes them
  from its cat bond total; 2020 (-223m) and 2021 (-199m) remain the open
  years, 2025 is +65m.
- Trigger mix, mean absolute gap in pp, tracked file -> committed:
  indemnity 3.36 -> 2.00, industry loss 2.53 -> 1.31, parametric 6.12 ->
  6.07, unknown 1.72 -> 1.46. 2019, 2022, 2023, 2025 and 2026 now match the
  publisher to 0.0pp on every trigger. Still open: parametric is -4.7pp in
  2012 and the 2005-2006 shares differ by 8-25pp (the EUR deals above, and
  the publisher's basis for those years); 2016 indemnity went from -5.9 to
  -7.4pp, so one 2016 mortgage deal may be inside the publisher's trigger
  chart.
- Golden suite 2175 -> **2196** (210 -> 231 unit, 1965 golden unchanged):
  21 new UNIT checks pin the table's source values and coverage, the
  cross-rate direction, `issue_month`, and `convert_size` on every basis.
  Mutations: divide instead of multiply (4 checks fail), ignore the issue
  month (6 fail), fall back to the local amount as dollars when no rate
  exists (2 fail); restored, 2196/2196.
- `net_supply.py` outstanding series: converted sizes raise 2021-2026
  issued by 70-130m a year; the 5 to 7bn gap to the publisher's outstanding
  figure is untouched and is item 3's roll-forward.

## Checkpoint (2026-10-21): separate-series programme totals

- Merna Re II 2022-2 and 2022-3 no longer take their combined $500m placement
  as each series' launch size. The same rule removes the four-series $1.55bn
  total from Merna 2025-1 and 2025-2 while retaining their own stated $200m
  and $300m launches. The general rule requires explicit component evidence:
  one sentence must enumerate distinct series and equally many same-currency
  amounts whose sum equals the candidate aggregate. A directory entry
  representing multiple series itself (Everglades 2023-1/2023-2) keeps its
  aggregate.
- All four Merna pages are now in the golden corpus. Expected suite size is
  210 unit + 1965 golden = **2175** checks.
- Work is on `fix/merna-programme-total`, based on local `main` after
  fast-forwarding `fix/live-golden-guards`. The guard-fix commit was already
  pushed; local `main` is one commit ahead of `origin/main` until next push.

## Checkpoint (2026-09-30): offline unit tier + per-class maturity

Done in an environment with no `raw/` and no `data/`; the golden suite over
`raw/` was NOT run there.

Verified locally over `raw/` the same day: **1775/1775** (208 unit + 1567
golden, both pins hold; main was 1759/1759 immediately before). Bundle rebuilt
on main and on the branch and diffed: one deal changes, Montana Re 2010-1
(maturity January 2014, correct against the page); 354 -> 355 stated
maturities; `tranches.csv` and `validation.csv` byte-identical. See
`PARSER_BACKLOG.md` item 3 for what the rule did not reach.

- `tests/test_golden.py` is now two tiers. UNIT checks (192 existing + 16 new)
  run anywhere. Everything that parses a page, or reads `data/queue.csv`
  (including the two sibling-registry unit functions), is GOLDEN and is skipped
  with a printed count when `raw/` is absent. A partial `raw/` is an error, not
  a skip. `ARTEMIS_OFFLINE=1` is forced and `requests.get/post/request` raise,
  so a cache miss cannot reach the network.
- Pins: the single 1759 pin is split into 208 unit + 1567 golden (192 + 1567 =
  1759, the old total; the 1567 is derived from the old pin and unverified
  here). Expected local total is now 1775 (1759 + 16). If it is not, stop.
- Backlog 3, per-class "Notes due": when at least two distinct classes state
  maturities and all resolve to one Month YYYY, that date is the deal-level
  maturity (`maturity_from_class_agreement` flag, medium confidence). One class
  alone, disagreement, extensions, replacements and backward references keep
  current behaviour. Mutation-tested (four mutations, each failed a test).
  Effect on real pages is unmeasured: expect `maturity_date` recall to rise on
  Montana Re 2010-1 / Isosceles 2023-type pages, and check no golden MATURITY
  or backref guard moves.
- Fixed 2026-10-02: the guards after the `check-count` block in `main()`
  (pct-in-range, spread-not-price, EL<=AP per tranche, seaside, citrus) sat
  inside the failure branch, after the page loop, so they ran only when the
  count was already wrong and then only over the last page. They now run per
  page: +340 golden checks, all passing, pin 1567 -> 1907, total **2115**.
  Mutation-tested: the old comma-deleting `_pct_to_float` fails pct-in-range
  (EL=223.0), and disabling `REGULATORY_CLASS_RE` fails the Seaside guard.
- Noticed, not changed: `data/validation_dashboards/*.csv` are tracked in git,
  contrary to `DATA_POLICY.md` (`git ls-files | grep -c csv` prints 5).

## Takeover checkpoint (2026-09-23)

- Recovered the uncommitted patch left after `10ff45f`. Compact labels now
  canonicalise before binding (`A1`/`A-1`, `M1-A`/`M-1A`) without changing the
  uppercase key contract used by the size solver. Integrity Re III 2025-1 and
  Bellemeade Re 2020-1 are pinned end to end.
- Percentage changes no longer enter `spread_risk_margin`: Everglades II
  2015-1's "upsized by 20%" and Ibis Re II 2013-1's "increase in pricing of
  6.7%" are rejected. A spread-vs-guidance plausibility warning is the backstop.
- `./.venv/bin/python tests/test_golden.py` is **1759/1759**, offline. Four
  mutations (compact-label grammar, each spread exclusion, and the validator
  backstop) all made the suite fail before the good code was restored.
- Full local bundle rebuilt from cache: 1,311 deals, 2,051 tranche rows, 272
  validation findings; tranche sums are 1,147 OK / 28 mismatch / 136 n/a.
  Publisher validation is unchanged at displayed precision: spread corr 0.89,
  mean difference -0.03pp; size-change readings remain corr 0.74 / 0.69.
- New visible open: the guidance backstop flags both duplicated Kilimanjaro III
  Re 2019 entries. Class B-2 has the correct 9.5% settled spread but inherited
  Class A's 15%-16% guidance; its own guidance is 8.75%-9.75%. Fix the grouped
  cross-series label binding rather than suppressing the warning.

The current working tree is tested but not committed or pushed.

## NEXT — start here (set 2026-09-15)

1. **Human-check** these against their Artemis pages. Round one (launch
   sizes that were not sizes):
   - PoleStar Re 2024-3: launch $75m (not the $800m attachment point, not the
     "$400m maximum" speculation)
   - Kilimanjaro III Re 2026-2: launch None, flagged
     `launch_target_shared_across_series` ($530m is across two entries)
   - Sanders Re III 2022-2: launch $250m (not Series 2022-1's $550m)
   - Everglades Re II 2023-1/2023-2: one entry for two series, so "$600m
     across the two series" is kept as this deal's update
   - Meadows Ltd 2025-1: launch $125m (not the investor's $8bn AUM)

   Round two (launch sizes that were one component's; spread = price of par):
   - Kilimanjaro II Re 2025-1: launch None ("$125 million" is the A-1/A-2
     pair's target); Tar Heel Re 2013-1: launch $200m, +150% (page says so)
   - Acorn Re 2024-1: no launch, update $450m (not "$200 million each")
   - Residential Re 2019-2 Class 1: spread 22.75% (not "priced at 77.25%")
   - Merna Re II 2022-2: launch "$500 million" is WRONG (programme total);
     known open, see backlog 10.
2. **Backlog 3 (maturity)** round one done: 120 -> 354 stated maturities.
   Human-check a few `stated_derived_mismatch` deals (stated date should win).
3. **Backlog 10 opens**: the Merna sibling-sum rule is the one with a clear
   mechanism. Backlog 9 (spread) is closed; backlog 1 is down to one
   source typo (Vita Capital VI) and one window bleed (Vitality Re VII).
   Backlog 4 is measured (`src/crosscheck_losses.py`): 1 of 40 settled
   losses is read from the page; the partial-loss remainder phrasing is next.
   Backlog 2: three of four mismatch families fixed; what is left is
   headline-basis representation and phantom tranches.
4. ~~Rename the project~~ done 2026-09-14.

Everything through `10ff45f` is pushed as of 2026-09-15; see the takeover
checkpoint above for the current uncommitted work.

## State (2026-09-15)

- Full crawl done: 1,311 deals parsed; `raw/` and `data/` are gitignored under
  the Artemis licence rule (`DATA_POLICY.md`). Code is tracked, content is not.
- `./.venv/bin/python tests/test_golden.py` — expect 2175/2175, offline.
- `src/validate_dashboards.py` reproduces every publisher comparison. Issuance,
  trigger mix, EL and spread validate (spread: corr 0.90, -0.03pp after the
  2026-09-15 price-of-par fix). The offering size-change series is bracketed
  by two readings (backlog 10); the residual is the publisher's inclusion set.
- The analysis layer lives in the sibling repo `cat-bond-flow-analysis`, which
  consumes `data/deals.csv` and `data/tranches.csv`. Non-USD conversion is
  decided there, not here.

## Testing discipline (hard-won, do not regress)

- Golden tests over `raw/` before any regex surgery; add the case, then fix.
- `REJECT` table: assert the absence of specific known-wrong values. A guard
  that only checks non-`None` passes when extraction fails entirely.
- Unit-test predicates, not just end-to-end: redundant defences mask each other.
- Mutation-test every guard, and verify the mutation actually applied. Never
  trust a green suite whose check count did not move.

## Data caveats

- EL / attachment / spread are sparse before ~2010; those series start there.
- Low Tier-1 fill means a private deal, not an old one. Triage by
  `deal_is_private`, never by year.
- Crawl order is a correctness requirement: prose cites predecessor deals, so
  older siblings must be parsed first (`data/queue.csv`).
