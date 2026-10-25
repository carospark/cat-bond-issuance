# Handoff

Read `PARSER_BACKLOG.md` first. It is the current state: what is parsed, what
is validated, and everything still worth fixing, ordered by value per hour.

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
