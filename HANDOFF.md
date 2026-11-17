# Handoff

Read `PARSER_BACKLOG.md` first. It is the current state: what is parsed, what
is validated, and everything still worth fixing, ordered by value per hour.

## Checkpoint (2026-11-17): TRACE maturities in the roll-forward; the cancelled-status false positive closed

Two items from the 2026-10-25 "left open" list. Tests 2227 -> **2255**
(262 -> 290 unit; the golden pin is unchanged at 1965). Both repositories
now live under `~/projects/`.

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
  month later in 45% of them); replaced by TRACE beyond that
  (`trace_maturity_overrides_stated=+Nm`, 7 deals, $1.3bn: Sanders III
  2022-3 +48m, ResRe 2023-2 +37m, Casablanca 2020-1 +25m, Bonanza 2023-1
  +24m, Vita IV +12m, Queen Street X 2015 +6m, all of them a one-year class
  or a predecessor's date read as the deal's, and Kilimanjaro II 2024-1 at
  -35m, where the bridge holds only the two 2025 classes of a page that
  states July 2028 -- the one override worth reading) or when the page date
  was a per-class vote (`_class_vote`; Montana Re 2010-1, same month).
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
  (`trace_maturity_replaces_imputed`; 317 deals, 310 public $76.6bn and 7
  private $1.1bn). What the imputation had been getting wrong: the public
  terms TRACE gives are 36 or 37 months for 141 of the 310, longer than 42
  for 96 ($27.6bn, the four- and five-year deals the 2026-10-25 note
  expected), shorter than 30 for 40 ($7.0bn); size-weighted mean 40.6
  months against the flat 36.
- a TRACE month at or before the issue month is rejected
  (`trace_maturity_rejected_not_after_issue`, 0 deals today) and the deal
  is imputed as before.

Coverage of the maturity leg by issued dollars, ex-mortgage, before ->
after: stated 26.1% -> 25.6%, derived from term 26.7% -> 4.0%, TRACE 0 ->
58.7% (514 deals, $131.7bn), imputed public 43.7% -> 8.7% (450 -> 136
deals, $97.9bn -> $19.4bn), imputed private 3.5% -> 3.0%. Known from a page
or TRACE: 52.8% -> 88.3%.

Outstanding vs the publisher ($m, ex-mortgage; roll-forward of 2026-10-25 ->
with TRACE): 2010 -2,076 -> -455; 2011 -1,253 -> -202; 2012 -857 -> -372;
2013 -1,523 -> -1,203; 2014 -1,764 -> -549; 2015 -970 -> +908; 2016
-2,263 -> +452; 2017 -3,259 -> -889; 2018 -2,114 -> -1,109; 2019 -1,594
-> +21; 2020 -4,678 -> +253; 2021 -3,291 -> -411; 2022 -2,468 -> +615;
2023 -3,805 -> -770; 2024 -2,181 -> +829; 2025 +724 -> +2,024; 2026 (at
2026-08) +4,121 -> +4,441. Mean absolute gap 2010-2026: 2,291 -> 912. The
2020-2024 shortfall the 2026-10-25 note attributed to 36-month imputation
of 48-to-60-month cohorts is gone; what is left is 2025-2026 running high,
and the upcoming-maturities check says where: against the publisher's
chart (Q3 2026 to Q2 2030) our scheduled remainder is now 65,401 vs 62,372
(was 67,041), mean absolute quarterly difference 671 (was 1,621), Q4 2026
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
  precedence outcome, the rejection, the no-`deal_url` case, the page
  columns, the legacy fallback on both an imputed and a replaced stated
  deal, coverage, the check table). Mutations, each run through the whole
  suite: tranche veto off (2 fail), earlier-attempt veto off (1), sibling
  veto off (2), tolerance 0 (3), tie to the earliest month (1), derived not
  replaced (2), legacy variant reading TRACE instead of the page (1 after
  the stated-replaced pin was added; 0 before it, which is why it was).

Left for Caro: read Kilimanjaro II 2024-1's page against the bridge (page
July 2028, TRACE 2025-07/08 on two CUSIPs); decide whether the 55
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
