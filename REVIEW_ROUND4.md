# Round 4 adversarial review — Artemis cat bond parser

Reviewer: Claude (Fable 5), 2026-08-30. Method: read the full diff `a9bedb3..HEAD`
(not the messages), parsed all 38 cached pages from disk via `fetch._cache_path`,
ran `validate()` with the index row on each, ran `SiblingRegistry` over all 38 in
queue order, audited `deals.csv` / `tranches.csv` / `review_long.csv` against
the pages (0 stale cells — the CSVs match the current code), scanned `queue.csv`
and `index.csv` at full scale, and grepped every constant/regex that exists in
more than one module.

**Network: none.** `raw/` is 40 files before and after (38 deal pages, the
index, the dashboard); `git status` clean at review time. The suite's `fetch()`
calls all logged `[cache]`.

Baseline: 290/290.

## On the trend (8 → 9 → 16)

Density per page reviewed is not rising; *surface* reviewed is. Of round 3's 16:
five came from the ten pages added that round, five from `build_queue` /
`fetch` / `sibling_registry` which no one had read, one was the mutation table.
On the code that rounds 1–2 had already covered, round 3 found three. This round
is the first that re-reads code *after* a fix round, and the answer to "does
each fix create new surface" is **yes, in 3 of 7 fixes** (§2, §3, §4 below) —
none of them a wrong value in the output, all of them a rule that is now
slightly too broad or a representation that will not survive scale. That is the
signature of patching a regex pipeline: fixes are local and the invariants that
would make them global (typed kinds, one money grammar, one series grammar) do
not exist. See Part 2, question 5.

---

## Part 1 — Defects, ranked

### A. Round-3 fixes, verified against `raw/`

#### 1. MEDIUM — `src/sibling_registry.py` — revived, but three of the four ways it can say "contamination" are broken

- `:130` `y < issue_year - 1` — the same off-by-one that round 1 removed from
  `parse_deal`. Repro (ResRe 2020, issued May 2020): plant a sibling entry
  `8.25%` and a tranche spread `8.25%`; the host sentence is "The Residential
  Re **2019-1** cat bond … priced with a coupon of 8.25%" → verdict
  `coincidental_match`. It should be `LIKELY_CONTAMINATION`.
- `:125` hosts are found by **string** containment (`str(value) in s`). Any
  value whose formatting differs from the prose has no host, so `backward`
  stays empty and the verdict is always coincidental. Repro: Seaside 2021-21
  final `$4m` (Tier‑1 format) vs prose "$4 million" → evidence blank. Every
  single-tranche final (which is Tier‑1-formatted) is un-auditable this way.
- No series rule. The parser excludes "2019-1" sentences; the registry does not
  know series tokens exist.
- The `size` cut (`CHECK_FIELDS`) is right in spirit — a Tier‑1 value cannot be
  contaminated by a sentence — but it is done by *field name*, and the
  provenance leaks in elsewhere: `tranche_size_final` on single-tranche deals
  *is* the Tier‑1 value (`final_from_tier1`) and is still audited (ResRe 2000
  `$200m`, Seaside `$4m`, Redwood `$150m` all matched siblings), while
  `size_history`'s launch — the only prose-mined deal-level size, and the one
  Windmill's `$46 million` actually contaminated — is not audited at all.
  So: over-audits Tier‑1 via tranche rows, under-audits the prose size.
- `:128` dead duplicate line survives.

Fix: `< issue_year`; add `_series_tokens(h) - own_series` as a backward marker;
match hosts numerically (`_numeric` of each money/percent token in the
sentence); skip candidates whose flags contain `final_from_tier1`; add
`size_history[launch]` to the deal-level candidates.

#### 2. LOW — `LOSS_LEVEL_RE` `\blayer\b` (`parse_deal.py:150`) — now kills a genuine size sentence

Citrus 2014-2: "With the deal currently offering **$50m of notes**, but this
higher layer being $100m in size" — `$50m` is vetoed because "layer" sits 30
characters after it. No output change (another sentence carries `$50m`), but
the prompt's question has a concrete yes. "term loan" is fine. At scale,
"a $X million layer" is often *the* size on single-layer deals, so a ±45-char
window on "layer" is the wrong instrument. Fix: veto on "layer/tower"
only when it directly follows the amount (`$2.5 billion layer`) or governs it
(`layer being $100m`, `layer of $X`), i.e. a −25/+12 window, not ±45.
Verified: Everglades stays `$400m → $1.5bn`, Ursa's `$500m layer` still vetoed.

#### 3. MEDIUM — range low-end (`TRANCHE_SIZE_RES`, first entry) — right for launch, wrong as final

IBRD 111-112 Class B now reads launch `$25 million` ✓ but **final `$25m`**
(page: "priced offering **$95 million** of notes"). The range pattern matches
in Updates 1 and 2, nothing matches Update 3, so the last range's low end is
promoted to final. A range endpoint can be a launch state; it can never be a
final. Corpus check: all four `between $X and $Y` occurrences describe size
targets, so "a range describing something else" has no instance here — but
the deal-level `size_history` loop has no range rule at all (skips the
sentence), and "seeking an **up to** $100 million" (Gateway) takes the *cap*
as launch. Two paths, three answers. Fix: tag sizes with `kind`; final = last
non-range mention, else `None` + `final_from_range_low_end`; add the idioms
that still miss (`priced (?:to offer|offering) $X`, `targeting at least $X`,
`aiming for $X`, `$X of (?:notes|cover)`). With those, IBRD A/B become
`$75m→$225m`, `$25m→$95m`, sum = `$320m` = Tier 1.

#### 4. LOW — `_segment_prose` labels — gluing is right, labels are not usable

No false split anywhere in the corpus (scanned every "update…:" in prose).
But the labels are `update_3_(5th_may_2015)`, `update,_may_2018`: not
sortable, ordinal lost for the comma form, and two bare `Update:` blocks
would collide on `update`. These labels are the `state` key in `size_history`
and `spread_history`. Fix: `update_<ordinal>` plus a parallel
`_meta["prose_state_dates"]`. (Operational Re is 5 states as claimed; IBRD is
14, not 15.)

#### 5. LOW — `build_queue.family_root` — no wrong merge found; one wrong transform; the family concept is wrong for platforms

- Orphan strip `[-–]\s*\d+[A-Za-z]?\b` runs unconditionally, so "IBRD CAR
  111-**112**" → "IBRD CAR 111", likewise 118-119, 123-124. Harmless today
  (singletons) but it is the year-strip bug's shape again. Fix: require a
  preceding space (`(?<=\s)[-–]\s*\d+`), which is exactly what the year strip
  leaves behind.
- Roman numerals to XXX: 433 → 396 families, 1,108 serial deals as claimed. The
  24 multi-sponsor families are all renamings/acquisitions (Bellemeade: United
  Guaranty → Arch) or shared vehicles; none is a numeral-induced merge.
- What *is* wrong at scale: **platform families**. Seaside Re (69), Eclipse Re
  (59), Dodeka (28), Artex (21), Market Re (13), Kane (10) — 262 index rows
  have sponsor `Unknown`. These are transformer cells, not programmes; Artemis
  prose never cites an earlier cell. The registry loads 68 "sibling sizes" for
  Seaside 2026-61 and small round numbers repeat, so at scale it will emit
  coincidental matches by the hundred and a `LIKELY_CONTAMINATION` whenever the
  boilerplate says "earlier"/"previous". Fix: mark `family_kind=platform` when
  most sponsors are Unknown and size ≥ 5; the registry treats those as
  sibling-less.

#### 6. Same-month ordering — sound. Eclipse Oct 2021 now 05A, 06A, 07A, 08A.

#### 7. LOW — `fetch._normalise` — still two keys for one page

Strips trailing slash and fragment only. `http://` vs `https://`, `artemis.bm`
vs `www.artemis.bm`, and `?utm=…` remain distinct keys. The three consumers
now go through `_cache_path` ✓. Add: lowercase scheme/host, drop query, and an
`ARTEMIS_OFFLINE=1` guard that raises on a miss so "no network" is provable
rather than declared.

### B. The outputs (nobody had audited the product)

#### 8. HIGH (for the analysis) — `price_guidance`, `attachment_point`, `spread_history` are deal-level columns holding one tranche's value

The category error already fixed for EL/AP/spread survives in three fields:

| deal | deal-level `price_guidance` | belongs to | deal-level `spread_risk_margin` | belongs to |
|---|---|---|---|---|
| IBRD 111-112 | 12.25% to 13% | **Class B** | 6.9% | **Class A** |
| Kilimanjaro | 9% to 9.75% | Class D | 9.25% | Class D |
| Hoplon II | 6.5% to 7.5% | Class A | 6.5% | Class A |
| FloodSmart | 14.5% to 15.5% | Class A | 14% | Class A |
| ResRe 2026 | 5.75% to 6.5% | Class 14/A? | 6.5% | Class 14 |

`attachment_point`: ResRe 2026 `$4.975bn` (Class 14), Kilimanjaro `$1.257bn`
(Class D), Hoplon `€85m` (Class A), FloodSmart `$9bn` (Class A).
`spread_history` on ResRe 2026 mixes Class 14's launch guidance, Class 15's
update-1 guidance and Class A's update-2 guidance in one series. "Final spread
vs guidance midpoint" — the core of the proposed absorption series — computed
from these columns gives IBRD −570 bps. Fix: mine all three per tranche window
(add to `TRANCHE_PATTERNS`), and null the deal-level columns when more than
one window exists, with `tranche_level_only:n=K`.

#### 9. MEDIUM — `attachment_point` accepts a percentage

Finca: Artemis writes "initial attachment point of **2.47%**" meaning the
probability. Parser: `attachment_point = 2.47%`, `attachment_probability =
None`. Fix: a `%` attachment point is a probability — move it, flag
`from_attachment_point_pct`.

#### 10. LOW — derived maturity on a deal that never issued

Gateway 2024-3: `deal_status = not_issued` yet `maturity_scheduled = Jun 2027`,
`maturity_date_derived = Jun 2027`. Fix: terminal status nulls derived
maturity (keep `term_length` and the launch target — those are honest facts
about the offering).

#### 11. LOW — `deal_is_private` is "Tier 1 is sparse", not "private"

Merna (public, rated 144A) is `True` because a 2007 page has "?" for agents,
modeller and ratings. Radnor, Dodeka, Seaside, Eclipse, Artex are private and
say so in prose ("unregistered private offering", "private cat bond"); Beazley
("private Section 4(2)") is *not* flagged. Fix: derive from prose
private-placement language; report the placeholder cluster as
`tier1_sparse=N` instead.

#### 12. LOW — `data_dictionary.csv` is prose, not a contract

9 of the 13 flag kinds actually emitted are not in it (`candidates`,
`source_placeholder`, `terminal_status`, `tranche_count_understated`,
`weak_pattern`, …); no `deals.csv`/`tranches.csv` column is documented by its
exact name; 5 documented flags are never emitted. It cannot be diffed against
the output, so it will keep drifting. Fix: generate it from code (a
`FLAG_DOCS` dict asserted complete by a test).

### C. Duplicated derivations — the class behind both process failures

Each of these is one fact defined in two places that can now disagree:

| fact | copies | already diverged? |
|---|---|---|
| backward year rule | `parse_deal` (`< year`), `sibling_registry:130` (`< year-1`), `measure_contamination` | **yes** (§1) |
| series token grammar | `_series_tokens` (`(19\|20)\d\d-\d+[A-Za-z]?`), `parse_tranches:1130` and `validate:130` (`20\d\d-\d+`) | **yes**: Eclipse "2021-01A" is visible to one, invisible to two; 388/1,311 index names have no token visible to any |
| stated-count grammar | `STATED_COUNT_RE` (tranches\|classes, one–eight), `validate:121` (tranches, one–six) | agree on corpus by luck |
| number words | `WORD_NUM`, `COUNT_WORDS`, `WORD_COUNT` — three ranges | latent |
| money grammar | `MONEY_RE`, `_M`, `sibling_registry:66`, `_money_to_number` | `_M` has no `b\b`, registry regex ignores "b", none know CHF/EUR |
| month vocabulary | `MONTHS` regex (has "Sept"), `build_queue.MONTHS` dict, `_month_ord` list | latent |
| "launch" state literal | `parse_deal` ×3, `validate`, tests | latent |
| `TRANCHE_ONLY`, `BASE` URL | 2 and 4 modules | latent |
| `queue.csv` schema (`family`, `family_seq`, `sibling_sizes`) | produced by `build_queue`, consumed by registry and bundle, never asserted; not rebuilt when `index.csv` changes | **the zero-rows incident's shape** |

Fix: one definition each, imported; a `queue.csv` freshness assertion (row
count and a hash of `index.csv` stored in the queue header).

### D. `queue.csv` as a crawl plan — what 38 pages cannot show

- Platform families (§5): ~200 deals whose "siblings" are unrelated cells.
- Series grammar (§C): `Series 3`, `Series FE0004`, `2019-E1`, `2010-I`,
  `2021-01A` — 388 names carry a token the same-year-sibling rule cannot see.
- Kaith Re boilerplate: "Class 3 Bermuda-based insurer … Kaith Re Ltd." is on
  every recent Seaside page. Known-open #1 is one phantom tranche today and
  ~69 at scale. Fix: exclude `Class \d (?:Bermuda|insurer|reinsurer|licen)`.
- Failure handling: `fetch()` raises on any non-200 and no caller catches it;
  one dead link ends a 1,311-page crawl with nothing written. There is also no
  429/backoff. Fix: per-URL try/except that records `fetch_failed` and
  continues; write outputs incrementally.
- Sub-named vehicles ("Arthur Re Ltd. – Tranquil Re 2026-1", "Artex – Tenby
  Notes") stay singleton families — harmless for contamination, wrong for
  "programme".

### E. Still open from round 3 (confirmed untouched)

Forward binding (Merna B/C still shifted, A missing); CHF/EUR/C$/NZ$
(Operational Re 0/3); `coupon of X% to Y%` low end (Lion I); tranche delta
tolerance (Dodeka −0.3%); the deletable-green guards.

### Judged sound this round

Tier‑1 reader (0 disagreements with `index.csv` on 38 pages); same-month
ordering; `Update` gluing boundaries; the negation regex additions (Baltic
"remains at" now caught); `CANCELLED_RE` additions (Queen Street X prose now
matches); `EXPECTED_CHECKS` pin; `_cache_path` used by all three consumers;
`validate` vs parser stated counts (no disagreement on corpus); the
data CSVs are not stale.

---

## Part 2 — Design and analysis

### Tier‑1 "Size" across the 38 pages

| basis of the Tier‑1 figure | pages | examples |
|---|---|---|
| = note principal, one tranche, one currency | 23 | most |
| = sum of note tranches | 10 | ResRe 2026, FloodSmart, Radnor (rounded: $399.2m vs $399,159,000) |
| = notes **+ term loans** | 1 | Merna ($1,058.6m notes + $122m loans) |
| = notes, **excludes parallel swaps** | 1 | IBRD 111-112 ($320m notes; $105m swaps beside it) |
| = USD conversion of native-currency notes | 2 | Hoplon ($67m = €50m), Operational Re ($222m = CHF220m) |
| dual-quoted | 2 | Windmill (€100m ($113m)), Lion (€190m ($262m)) |
| "Not issued" | 2 | Gateway, Queen Street |
| rounded vs prose | 2 | Beazley ($45m vs $45.06m), Radnor |

So parts-vs-whole is exact on 33/36 issued pages, needs a currency conversion
on 4, and is *structurally* wrong on 2 (5%). In the full index the currency
case is 50/1,311 (3.8%); hybrid loan/swap structures are rare (State Farm's
Merna family, the World Bank pandemic and a few IBRD CAR deals). **Right
representation:** Tier‑1 Size is a *headline* — "risk capital secured, in
Artemis's headline currency". Model it as `size_headline` (verbatim),
`size_headline_ccy`, `size_headline_usd` (Artemis's own parenthetical when
present), `notes_principal` (sum of tranche notes, native ccy),
`other_instruments` ([{kind: term_loan|swap, amount}]) and
`headline_basis ∈ {notes, notes+loans, notes_excl_swaps, converted,
not_issued}`. Parts-vs-whole then compares `notes_principal + loans` to the
headline in native currency, with a ±0.5% rounding tolerance and a reported
absolute gap. The absorption series should use `notes_principal` in USD, not
the headline, because swaps and loans are not cat-bond supply.

### Round‑4 verification of round‑3 design calls

Typed events: unchanged, strengthened — §3 (range as final) and §8
(tranche-level guidance) are both "kind" and "scope" confusions.
Entity-first: unchanged. Two-pass crawl: unchanged, and §5 (platform
families) adds that *family* should carry a `kind` so the registry can decline
to audit platforms.

### The plan

**1. Fields the absorption series needs, and their state today (38 pages):**

| field | needed for | fill | trustworthy today? |
|---|---|---|---|
| issue month (T1) | everything | 38/38 | yes |
| headline size (T1) | gross issuance | 36/38 | yes as headline; see basis above |
| notes principal (tranche sum) | gross issuance | 29/38 | yes when complete; missing on CHF/EUR-word pages, Merna, IBRD |
| launch size (prose) | upsize % | 24/38 | **no** — 13 pre‑2010 pages have no Tier‑2 money at all; range/cap handling differs by path |
| final spread (tranche) | spread vs guidance, multiple | 13/38 | yes where present, after the `coupon of X to Y` fix |
| guidance range (tranche) | spread vs guidance | 14/38 deal-level | **no** — deal-level column is one tranche's (§8) |
| EL (tranche) | multiple | 16/38 | yes |
| term / maturity | net issuance | 12–13/38 | partially; derived-from-term is scheduled not final; extension periods not modelled |
| payout / loss of principal | net issuance | 1/38 | not extractable at useful coverage |

Era matters more than any single bug: the 13 pages before 2010 have empty
Tier‑2 scalars. The series is supportable from roughly 2011 on.

**2. Minimum viable version, this corpus only, no join:** monthly, from
`index.csv` alone (1,311 rows, no page parse): count, gross issuance in USD
(headline, with the 50 non-USD rows converted at a stated fixed rate), and
share "Not issued". Then, from parsed pages 2011+: share of deals upsized
(final ÷ launch > 1.01), median upsize %, and median (final spread − guidance
midpoint) in bps and spread/EL multiple, all *per tranche* then aggregated by
issue month. Net issuance needs maturities: use `term_length` where stated,
else the 3-year modal term, and label it "scheduled, no extensions".

**3. What would falsify it:** (a) upsize share and spread-vs-guidance should
move together and *against* the Swiss Re index spread level; if they diverge
for several quarters, the extraction is biased (e.g. only multi-tranche deals
have guidance text). (b) Compare the 2024–2026 quarters against Artemis's own
quarterly reports (the dashboard page cached already validates counts;
the same page has issuance totals) — a >5% gap in gross issuance means the
headline basis is wrong. (c) Coverage bias: if the fields are present mainly
for large public sponsors (USAA, FEMA, World Bank) and absent for private
platforms (Seaside, Eclipse — 262 Unknown-sponsor rows), the "market" series
is a large-sponsor series; report fill rate by sponsor class next to every
number. (d) A single mis-scoped guidance (§8) produces a −570 bps outlier;
winsorise and list outliers with evidence strings so they can be checked.

**4. Post-issuance tier — how to model, and how much exists:** across the 38
pages, **3 pages / 13 segments** carry post-issuance content: Lion (1 reset),
Operational Re (1 reset-ish, 1 structural), IBRD 111-112 (10: loss events,
marks, the $195.84m payout). One deal records capital leaving. Model it as
events `{deal, tranche, date, kind ∈ {reset, loss_event, mark, payout,
extension, maturity}, amount, pct_of_principal, evidence}` — but the honest
finding is that the directory page is not where Artemis records losses;
its news articles are. From this corpus you can build a *flag* (deal has any
post-issuance update) and a handful of events; you cannot build a loss
series. Net issuance should therefore use scheduled maturities and carry
"payouts not modelled" as a stated limitation, not a field.

**5. Patch or rebuild?** Rebuild the Tier‑2 *size and pricing* pipeline
around typed mentions before the crawl; keep everything else.

- *What carries over unchanged:* Tier‑1 reader, sentence segmenter,
  backward-reference rule, tranche windows and label binding, `validate.py`,
  the golden fixtures (every `EXPECT`/`TRANCHE_SIZES`/`SIZE_HISTORY` value is
  a property of the page, not of the implementation), the queue.
- *What is replaced:* `size_history` loop, `_mine_sizes`, `TRANCHE_SIZE_RES`,
  `LOSS_LEVEL_RE`, `AGGREGATE_RE`, `CLASS_SCOPED_RE`, `NEGATED_RESIZE_RE`,
  the spread/guidance patterns — ~450 lines of vetoes — by one pass that
  emits, for every money or percent token, `{amount, ccy, kind, scope,
  segment, sentence}` where kind and scope are decided once, by the
  surrounding idiom, and every downstream field is a *query* over that list.
- *Cost:* 2–3 days; the classifier is the same regex knowledge already in the
  file, re-homed. The fixtures are the acceptance test: 290 checks must pass
  with **zero** changes to expected values, plus the seven pages currently
  missing from `PAGES`.
- *How you would know it helped:* (i) the next review round finds no defect
  whose fix is "add one more veto word"; (ii) per-field fill rate does not
  drop; (iii) `check_tranche_sum` is n/a on fewer pages (today 9/38); (iv) the
  same code answers both deal-level and tranche-level size questions, so the
  Gateway three-answers case cannot recur.
- *Why not keep patching:* this round shows the failure mode directly — the
  `layer` fix, the range fix and the label fix each solved the reported page
  and each created a rule that is wrong somewhere else visible in the same
  corpus. Seven more pages of vetoes will not converge.

### Null results

- I could not find a wrong Tier‑1 value or a numeral-induced wrong merge.
- I could not find a range describing something other than size in this
  corpus; the problem is the *state* it is assigned to, not the pattern.
- I could not find an alternative to platform-family exclusion for
  Unknown-sponsor cells; sponsor-based grouping is the only signal and it is
  absent by definition.
- Post-issuance data is too sparse on directory pages to model as a series;
  no parser change fixes that.

---

## Fixes applied (working tree, uncommitted) — 2026-08-30

Everything below was run with `ARTEMIS_OFFLINE=1` (new `fetch()` guard: a cache
miss raises instead of requesting). `raw/` is still 40 files. Suite:
**532/532** (was 290; 8 pages and ~60 unit checks added). `data/*.csv`
regenerated offline; `validation.csv` is now written by the bundle.

| # | defect | fix |
|---|---|---|
| A1 | registry `< issue_year - 1`, string hosts, no series rule, provenance | `sibling_registry.py`: `< issue_year`; hosts matched by number; `_series_tokens` backward marker; skip `final_from_tier1` tranche finals; audit `size_history[launch]`; skip `family_kind=platform`; money regex imported |
| A2 | `layer` ±45 veto killed Citrus's "$50m of notes" | `LAYER_RE` in a −25/+12 window only |
| A3 | range low end promoted to final (IBRD B `$25m`) | `TRANCHE_SIZE_RES` carries a kind; `_launch_final()` never takes a range as final; range needs a governing sizing word (Citrus's "from $200m to $450m of its tower" is not one); idioms added (`priced (to offer\|offering) $X`, `targeting at least`, `aiming for`, `$X of notes/cover`, `issue a $X`); IBRD A/B now `$75m→$225m`, `$25m→$95m`, sum = Tier 1 |
| A4 | segment labels unusable | positional `update_N`; dates in `_meta["prose_state_dates"]` |
| A5 | orphan strip ate "IBRD CAR 111-**112**"; platform families | `(?<=\s)` lookbehind; `family_kind` column (12 platforms, e.g. Seaside, Eclipse, Artex, Dodeka, Kane, Market Re) with no sibling sizes |
| A7 | cache key still scheme/host/query-sensitive | `_normalise` lowercases scheme+host, drops query (existing keys unchanged — no re-fetch); `ARTEMIS_OFFLINE` guard; `DEAL_DIRECTORY_URL` constant |
| B8 | deal-level guidance/attachment = one tranche's | both mined per tranche window (`tranches.csv` +6 cols); deal columns nulled with `tranche_level_only:n=K` when >1 window |
| B9 | `attachment_point = 2.47%` | a `%` attachment point is a weak `attachment_probability` pattern |
| B10 | derived maturity on a not-issued deal | nulled with `no_maturity:<status>` |
| B11 | `deal_is_private` = sparse Tier 1 | prose private-placement language; placeholder count kept as `tier1_placeholders=N` |
| C | duplicated grammars | one `CCY`/`MONEY_RE` (CHF, EUR-as-word, C$, NZ$, US$); `_currency` returns ISO codes; `_series_tokens`, `STATED_COUNT_RE`, `COUNT_WORDS`, `TRANCHE_ONLY` imported by `validate`/builders; `validate.py` parts-vs-whole delegates to `check_tranche_sum` |
| D | Kaith "Class 3 Bermuda-based insurer" | `REGULATORY_CLASS_RE` — Seaside 2026-61 now one unlabelled tranche |
| E (round 3) | Merna forward binding | `FORWARD_BOUND_RE` first; A/B/C = $256m/$647.6m/$155m |
| E | Tier-1 "Size" basis | `other_instruments` field (term loans, swaps); `check_tranche_sum` reports `basis=notes` / `notes+term_loan` / `mismatch`; Merna sums with its $122m of loans |
| E | `coupon of X% to Y%` low end | `NOT_RANGE` lookahead on every settled-price anchor; "settled to offer investors a yield of X%" added; Lion still 2.25%, now from the settled sentence |
| E | tranche delta without tolerance | ≤1% → `None` + `size_rounding_only` |
| E | conversions "(EUR 80m)", "(around $223m)" | `PAREN_CONVERSION_RE`: not a second amount; the headline-currency figure is preferred (Windmill launch `EUR 80m → €100m +25%`) |
| E | tranche path lacked `own_series` | passed through `_extract_tranche_metrics` |
| E | AP "is"/"for the notes is"; settled-at budget | patterns widened (Everglades AP 2.89%, spread 7.5%) |
| Tests | 8 deletable-green guards | 8 pages added to `PAGES` with `EXPECT`/`TRANCHE_SIZES`/`SIZE_HISTORY`; new `SIZE_CHANGE`, `TRANCHE_FIELDS`; direction-vs-evidence guard; multi-tranche deal-column guard; `unit_predicates()` (loss-level, negation, cancellation, bindings, size idioms, range-never-final, spread ranges, currency, segment labels, regulatory class); `unit_registry_rules()` (year−1, numeric hosts); `EXPECTED_CHECKS = 532` |

Not fixed (design, not patch): platform detection is a heuristic (≥5 deals,
≥50% Unknown sponsor); "Pte." / "Merna Re" vs "Merna Reinsurance" splits;
crawl-loop error handling (no crawler exists yet); `data_dictionary.csv`
generation; the typed-events rebuild.

Output changes worth knowing: `tranches.csv` gained `price_guidance`,
`attachment_point` (+conf/flags); `deals.csv` gained `other_instruments`;
`size_history` entries carry `kind` (`stated` / `range_low` / `cap`, with
`:converted`); `queue.csv` gained `family_kind`; `deal_is_private` semantics
changed; `_meta.prose_states` are now `update_N` throughout.
