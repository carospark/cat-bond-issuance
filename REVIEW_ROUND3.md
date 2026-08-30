# Round 3 adversarial review — Artemis cat bond parser

Reviewer: Claude (Fable 5), 2026-08-30. Method: read all of `src/` and `tests/`,
parsed all 39 cached deal pages directly from `raw/` (files read from disk, not
via `fetch()`), ran `validate(rec, tranches, index_row)` on every page, scanned
the prose corpus for each Priority-A regex, mutation-tested 16 guards in a
scratch copy of the tree, and prototyped five minimal fixes in a second scratch
copy to confirm they resolve the defect without regressing the suite.

**Network: none.** `raw/` held 40 files before and after; `git status` clean.
The suite's 17 `fetch()` calls all logged `[cache]`. Nothing in the working
tree was modified.

Baseline: 288/288.

---

## Part 1 — Defects, ranked

### 1. HIGH — `src/sibling_registry.py:94` — `audit()` raises on every call

`sentences = sentences(prose)` assigns a local named `sentences`, so Python
treats the name as local for the whole function and the call on the right-hand
side raises `UnboundLocalError` before anything else runs.

Repro (any page): `SiblingRegistry().audit(url, parse_deal(html, url), parse_tranches(rec))`
→ `UnboundLocalError: local variable 'sentences' referenced before assignment`.

Introduced by `2fa4242` (centralised segmentation). `data/sibling_audit.csv`
is dated Aug 29 12:52, before that commit — it is stale output from a version
that no longer runs. The contamination detector that the entire crawl-order
design exists to serve is non-functional, and no test touches it.
Lines 124–125 are also a dead duplicate.

Fix: rename the local (`sents = sentences(prose)`), delete line 124, add a
one-page smoke test that `audit()` returns a list.

### 2. HIGH — `src/parse_deal.py:946-956` `_bindings_by_label` — "Class A – $X" binds the amount to the *next* label

Merna Reinsurance prose: `Class A – $256 million Class B – $647.6 million Class C – $155 million`.
`LABEL_BOUND_RE` (`$X [tranche of] Class Y`) sees "$256 million Class B" and
binds 256 → B, 647.6 → C. Output today:

| tranche | parser | page |
|---|---|---|
| Class A | *missing* (`tranche_size_missing`) | $256m |
| Class B | $256 million | $647.6m |
| Class C | $647.6 million | $155m |

Two wrong values at ordinary confidence. `check_tranche_sum` returns n/a
because A is missing, so nothing arithmetic catches the shift; the validator
only says "1/3 labelled tranches have no size".

Fix (verified, suite green): a forward pass `Class X\s*[–—:-]\s*_M` first,
and skip any amount in the backward pass whose offset was already bound
forward. Result A/B/C = $256m/$647.6m/$155m — which then makes the sum check
**fail at −10.3%**: Tier‑1 "$1.18bn" includes $122m of term loans ($94m/$19m/$9m)
that are not notes. That is a real semantic finding, see Part 2.

### 3. HIGH — `src/parse_deal.py:474-496` + `LOSS_LEVEL_RE:148` — a layer width becomes the launch size and inverts the resize direction

Everglades Re 2014-1: "Yes, that's a **$2.5 billion layer** of Citizens
reinsurance tower, so it will be interesting to see how large the 2014-1
Everglades Re issuance can grow to." Sentence passes `SIZING_CTX_RE`
("issuance"), is not class-scoped, and "layer"/"tower" are not in
`LOSS_LEVEL_RE`. Output: `size_history` launch = `$2.5 billion`;
`size_change` = **downsized −40%** with `reason_evidence` = "…increased in
size by a stunning 213% to reach $1.25 billion". The record contradicts its
own evidence. The real launch is the *next* sentence: "beyond the **$400m
preliminary size** being marketed".

Fix (verified): add `\blayer\b` to `LOSS_LEVEL_RE` → launch `$400m`,
`+275% upsized`, suite green. Add the cheap invariant this exposed: if
`reason_evidence` matches `increas|upsiz|grew|lift` and `direction ==
"downsized"` (or vice versa), flag `VIOLATION:direction_contradicts_evidence`.

### 4. HIGH — `src/parse_deal.py:142` `CLASS_SCOPED_RE` — "tranche C term loan" is not class-scoped

Merna again: "$9 million tranche C term loan." is the only sentence that
survives every filter, so the deal's `size_history` launch is **$9 million**
(medium confidence) on a $1.18bn deal. `uncorroborated_size_change_suppressed`
saved `size_change`, but `size_history` and `ctx["deal_launch"]` still carry
the value into `deals.csv`.

Fix: `CLASS_SCOPED_RE = r"\b(?:Class|tranche)\s+[A-Z0-9]\b"` (single
capital/digit + boundary; "tranche of" stays unscoped). Independently: a
deal launch state below ~10% of the Tier‑1 final with no resize language is
implausible and should be flagged, not kept.

### 5. HIGH — `TRANCHE_SIZE_RES:755-768` — a size *range* endpoint reported as settled; common size idioms missed

IBRD CAR 111-112, Class B: Update 2 says "aiming for **between $25m and $100m**
in size". `_M\s+in size` takes the upper endpoint → launch **$100m**, final
**$100m**. Page: launched "targets $25 million of cover or greater"; priced
"offering **$95 million** of notes". Both values wrong. This is round 1's
"guidance range low end sold as settled spread" reappearing for sizes.

Class A is worse by omission: "targeting at least $75 million", "targeting
from $150 million to $200 million", "aiming for $150m to $250m", "priced to
offer $225 million of notes" — none match. `(?:tranche|notes)[^.]{0,20}?of `
misses "notes was priced to offer $225 million" by one character (21). So
A is missing, the sum check is n/a, and B's wrong $100m goes unchallenged.
(Update 3's "$325 million" is Artemis's own slip — 225+95 = 320 = Tier 1 —
and is now in `size_history` at medium.)

Fix: (a) reject an `_M` preceded by `between|from` or followed by
`\s*(?:to|and|[-–])\s*[$€£]` unless the pattern is explicitly a range
event; (b) add `(?:target\w*|aim\w*)\s+(?:for\s+|at least\s+)?_M`,
`priced\s+(?:to\s+offer|offering)\s+_M`, `_M\s+of\s+(?:notes|cover(?:age)?)`;
(c) widen the `{0,20}` budget. Better: Part 2's typed events.

### 6. MEDIUM‑HIGH — `src/build_queue.py:32-36` `family_root` — mortgage‑ILS programmes split by series suffix; roman numerals above X not merged

Stripping `\b(19|20)\d\d\b` from "Radnor Re 2020-2" leaves "Radnor Re -2".
In `queue.csv`: **27 families / 65 deals** carry a `-N` remnant —
Bellemeade Re -1/-2/-3/-4 (20 deals, four families), Radnor Re -1/-2,
Home Re, Eagle Re, Triangle Re -1/-2/-3, Quercus, Newport. Radnor Re 2020-2's
registry never sees Radnor 2020-1's size — the exact same‑year sibling case
the registry exists for.

`ROMAN` (`I{1,3}|IV|V|VI{0,3}|IX|X`) stops at X: Dodeka XI–XXIV are 14
singleton families, Vitality Re XI–XVII seven more, Queen Street XI/XII and
Redwood Capital XI stand alone.

Prototype (strip `\b(19|20)\d\d-\d+[A-Za-z]?\b` before the bare year; roman
`\b(?=[IVX]{1,6}\b)X{0,3}(?:IX|IV|V?I{0,3})\b`): 433 → 396 families, 114
deals regrouped. The only family that becomes multi‑sponsor is Bellemeade
(United Guaranty → Arch, an acquisition — correct). Wrong merges I could
find: none. Wrong splits the regex can't fix: "Pte." (Singapore vehicles —
Alamo/Nakama/Kizuna/First Coast/… Re Pte. split from their Bermuda
predecessors, ~10 families) because `family()` strips Ltd/DAC but not Pte;
and name variants ("Merna Reinsurance" vs "Merna Re", both State Farm).

### 7. MEDIUM — `src/build_queue.py:58-60` — same‑month siblings are ordered newest‑first

`sort_values([...,"ord"], kind="stable")` on an index that is newest‑first
leaves same‑month deals in descending order. Eclipse Re 2021, queue order:
Oct → 08A, 07A, 06A, 05A; Nov → 11A, 09A, 04A, 03A. The registry treats 08A
as an ancestor of 05A and cannot see 05A when parsing 08A. Seaside (69 deals,
January clusters) and Artex are the same. Fix: tiebreak on the series token,
or on reversed index position.

### 8. MEDIUM — `src/parse_deal.py:257` `_segment_prose` — dated update headings are not split

`(Update\s*\d*\s*:)` misses `Update 2 (May 4th 2016):` and `Update, May 2018:`.
- Operational Re: 4 updates → states `['launch','update_1']`; the CHF630m →
  CHF200m → CHF220m sequence collapses into one block.
- IBRD 111-112: ten post‑issuance updates (Ebola, Covid, the $195.84m payout)
  are glued onto `update_3`, the pricing state.
- Lion I Re: Update 3 (the reset) merged into Update 2.

Fix (verified: 4 / 13 / 4 states, suite green):
`(\bUpdate\s*\d*\s*(?:\([^)]{0,40}\))?\s*,?\s*(?:[A-Z][a-z]+\.?\s+(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?\d{4})?\s*:)`
and number unnumbered blocks by position (two bare `Update:` blocks currently
share the label `update`).

### 9. MEDIUM — Priority A: `deal_status` / `CANCELLED_RE:178`

- Misses: "was **not completed**", "was **withdrawn**" (Queen Street X, both
  sentences), "decision **not to proceed**" (Gateway — rescued only because
  "has been cancelled" sits in the same sentence). Queen Street X is saved
  solely by Tier‑1 "Not issued"; a withdrawn deal whose Tier‑1 reads
  "Unknown" is `issued` at medium.
- False fires on issued deals: none in corpus (only Gateway and the
  class‑scoped ResRe 2020 sentence match).
- Partial issuance: ResRe 2020 handled (`tranche_not_issued`, deal `issued`).
- Cancel‑then‑relaunch: no corpus example; Artemis creates a new directory
  entry (Gateway 2024‑3 → later series), so per‑page status is adequate.
- **Both routes are untested** — see §17. `TERMINAL_STATUS = {}` and deleting
  the prose loop are each individually green.

Fix: add `was withdrawn|was not completed|not to proceed|shelved|postponed`;
put Queen Street X in `PAGES` with `EXPECT deal_status = not_issued` and a
unit test on `CANCELLED_RE` with the three sentences above.

### 10. MEDIUM — `NEGATED_RESIZE_RE:154`

- Misses `remain**s** at` — Baltic PCC Update 1: "this issuance **remains at**
  UK £100 million in size, but the spread has been adjusted"; and "remain the
  same size" (Operational Re). Both latent today (no >1% gap on those pages).
- Wrong suppression: negation is tested against the **whole update segment**
  (`not NEGATED_RESIZE_RE.search(t)` at :537). An update reading "Class A did
  not change in size, while Class B upsized to $X" is discarded entirely, so a
  real deal‑level upsize is reported as `uncorroborated_size_change_suppressed`.
  No corpus page does this yet; ResRe‑style multi‑tranche updates make it
  likely.

Fix: `remain(?:s|ed)? (?:at|the same|unchanged)`, and evaluate negation on the
sentence that carries the resize verb, not the segment. Deletable with suite
green (§17).

### 11. `_governed_by_loss_level` — sound, one gap

Corpus scan of every sizing sentence: 5 vetoes, all correct (Citrus 2014‑1
attachment $200m, Everglades attachment $5.202bn, Finca deductible $15m,
Lion trigger €400m, Ursa trigger $1.861bn). No genuine size killed. The one
deductible‑class miss is "layer" (§3). Inside `_mine_sizes` the veto never
fires on any page — it is dead in the corpus (mutation green).

### 12. LOW — `MONEY_RE:196`, `_M:755`, `_currency:231` — CHF and word currencies invisible; `C$`/`NZ$` read as USD

Operational Re is written entirely in CHF ("CHF105m Class A‑1, CHF5m Class
A‑2, CHF110m Class B", "settled at CHF 220m") → 3/3 tranche sizes missing and
the size history reduced to the parenthetical "$223m". Crystal Credit "EUR 252
million" invisible to Tier 2. `_currency("C$150m")` == `"$"`, so a CAD final
compares as same‑currency with a USD launch. Index: 3 `EUR…`, 2 `C$`, 1 `NZ$`.
Fix: `(?:C\$|NZ\$|A\$|US\$|[$€£¥]|EUR|USD|GBP|CHF|JPY)\s?` and return the
whole prefix from `_currency`.

### 13. LOW — spread patterns `:90,:92` lack the range lookahead

Only the `priced at` pattern rejects `X% to Y%`. `coupon of ([\d.]+%)` on
Lion I matches "coupon of **2.25%** to 2.5%" and returns 2.25% at medium —
correct only because the deal happened to settle there; the evidence string
shows the range. Unit: "priced to pay investors a coupon of 4% to 4.5%" → 4%.

### 14. LOW — honest Nones that a small budget causes

Everglades: "pricing settled at the upper end of the narrowed range, at 7.5%"
fails the `{0,40}` budget by two characters; "attachment probability for the
notes **is** 2.89%" (only `of` accepted). `STATED_COUNT_RE` misses "three
**separate** tranches" (Crystal Credit) so no `tranche_count_understated`.

### 15. LOW — `_size_row:1042` — tranche delta has no tolerance

Dodeka XI: launch "$19.5 million" (rounded prose) vs final "$19.451m" →
`tranche_size_delta_pct = −0.3`, while the deal‑level rule requires >1%.
Inconsistent thresholds produce phantom sub‑1% resizes.

### 16. LOW — `src/fetch.py:20-28` cache key; `parse_index.py` sound

`_cache_path` hashes the verbatim URL: `…/slug` vs `…/slug/`, `http` vs
`https`, or a query string is a cache miss → a silent network fetch and a
second file for the same page. That is the most likely explanation for the
file that appeared during a "no network" run. Fix: normalise (lower‑case
scheme/host, force trailing slash, drop query) before hashing, and add an
`ARTEMIS_OFFLINE=1` guard that raises on a miss so the claim is provable.

`parse_index.py` against `raw/`: sound. 1,311 rows, every URL canonical with
a trailing slash, every date `Mon YYYY`, no duplicates, and `validate(rec,
trs, index_row)` over all 39 pages raises no `index_size/date/sponsor`
finding. `build_review_bundle.py` already has the index row in hand (`r`) but
never calls `validate` — that is open item 3, confirmed: `grep validate src/`
finds no producer of `data/validation.csv`.

### 17. Priority D — what can be broken with the suite still green

Mutation results (scratch copy, `tests/test_golden.py`):

| mutation | result |
|---|---|
| drop loss‑level veto in `size_history` (Finca fix) | **288/288 green** |
| drop `NEGATED_RESIZE_RE` check | **green** |
| drop the prose `CANCELLED_RE` loop | **green** |
| `TERMINAL_STATUS = {}` (Tier‑1 "Not issued" route) | **green** |
| drop loss‑level veto in `_mine_sizes` | **green** (dead in corpus) |
| drop `tranche_size_missing` flag | **green** |
| drop `uncorroborated_size_change_suppressed` (accept reason=None) | **green** |
| `CLASS_CONTEXT_RE` never filters (Bermuda‑class guard) | **green** |
| remove `VIOLATION:EL_exceeds_attachment_probability` | **green** |
| drop class‑scope guard on cancellation | caught (289/291) |
| drop terminal early‑return in `_size_single` | caught (286/287) |
| drop `tranche_not_issued` flag | **caught (288/289)** — round 2's claim is now false |
| drop multi‑amount/aggregate skip | caught |
| drop `CLASS_SCOPED` skip in `size_history` | caught |
| `unresolved_multi = False` | caught |
| remove binding fallback | caught |

So of the round‑2 fixes, only the class‑scope guard and the early return are
pinned; the deductible veto, the negation check, and both terminal‑status
routes are unprotected. Cause: Finca, Merna, Everglades, IBRD 111‑112,
Operational Re, Queen Street X and Baltic are not in `PAGES`. Note also that
the *check count* moved (287, 291, 293) under several mutations without a
failure — `assert len(results) == 288` at `:412` would have caught the
conditional guards vanishing.

Also: `seaside-re-series-2026-61` should leave `TRANCHE_SUM_OK` — its sum
passes only because the fabricated "Class 3" single tranche inherits Tier‑1's
size (open item 1, confirmed; the context is "Class 3 Bermuda‑based insurer
… Kaith Re Ltd. … has issued a $14.94 million … notes", so a ±60‑char context
window cannot separate it — require `Class X` adjacent to `notes|tranche`, or
exclude `Class \d+ (?:Bermuda|insurer|reinsurer|licen)`).

Latent, no corpus repro: `_extract_tranche_metrics:915` calls
`_apply_patterns` **without** `own_series`, so the same‑year‑sibling
exclusion protects deal‑level fields but not tranche rows. Citrus 2014‑2
escapes only because "priced at a reduced 4.25%" doesn't match any spread
pattern.

### Known‑open items — confirm / refute

1. Confirmed; fix and test change above. 2. Confirmed; second instance is
Operational Re (CHF, three states lost) — typed events are the fix.
3. Confirmed (no producer). 4. Confirmed dead. 5. Confirmed, and Operational
Re is a second instance ("two tranches" then "three tranches" after a tranche
was added): take the count from the **last** segment that states one, then
max. 6. Confirmed. 7. Not re‑examined. 8. Agree — with the Merna caveat that
when the page *does* enumerate them in a table‑like list, the parser must not
shift them (§2).

---

## Part 2 — Design

### Round‑2 proposals

**Typed lifecycle events — agree, and this round is the evidence.** Every
wrong size found here is a *type* confusion: layer width ≠ size (§3), range
endpoint ≠ settled (§5, §13), component ≠ total (§4), term loan ≠ note (§2),
post‑issuance payout glued to pricing (§8). Replaces: `size_history`,
`_mine_sizes`, `TRANCHE_SIZE_RES`, `LOSS_LEVEL_RE`, `AGGREGATE_RE`,
`CLASS_SCOPED_RE` — six regex tables that each veto one confusion — with one
classifier emitting `{amount, ccy, kind, scope, segment}` where
`kind ∈ {target, range_low, range_high, revised, priced, issued, layer,
attachment, exhaustion, deductible, component, payout, mark}` and
`scope ∈ {deal, tranche:X, term_loan, other_deal}`. `size_history` becomes a
filter, not a parser. Cost: ~300 lines rewritten; the golden `SIZE_HISTORY`
and `TRANCHE_SIZES` fixtures carry over unchanged. Breaks: nothing in Tier 1.
Verify: the 39‑page dump must show zero size states of kind ∉
{target, revised, priced, issued}; §2–§5 become `EXPECT`s. What it misses:
Artemis dates only some updates, so ordering within a page is ordinal, not
temporal — fine for launch→final, insufficient for cross‑deal time series
(use `date_of_issue` as the anchor).

**Entity‑first tranche resolution — partial agreement.** Windows did not
cause §2 or §5; *binding direction* did (forward `Class A – $X` vs backward
`$X Class A` vs shared `each`), and Radnor/Triangle work precisely because
bindings were added on top of windows. I would keep windows for metrics
(EL/AP/spread always follow the label) and make amount↔label binding an
explicit directed relation with its own unit tests. Cheaper than a rewrite,
and it is where the defects actually are.

**Two‑pass crawl — agree, strengthened.** The registry is currently
non‑functional (§1), so order‑dependence is moot today; but with two passes
the family grouping (§6, §7) stops being a correctness requirement and becomes
a cache‑locality nicety. That removes an entire class of defect from the
critical path, which is a stronger argument than "output stops depending on
parse order".

**Judged already correct — agree with all, two caveats.**
- *Honest None over plausible fallback* is right but currently unmeasured.
  Operational Re yields 0/3 tranche sizes and Crystal Credit 0 Tier‑2 money;
  a per‑field, per‑era fill‑rate table should be a tracked artifact so honest
  Nones can't quietly become 40% of a column.
- *Categorical confidence grounded in method* mislabels: Merna's "$9 million"
  launch is `medium`; Lion's 2.25% is `medium` with a range in its evidence.
  Demote on **structural** evidence (a range in the evidence window;
  launch/final ratio outside [0.2, 5]; a component idiom), not only on method.
- Invariants: agree on rejecting `spread > EL` and "no deal state equals a
  tranche size". Add: direction‑vs‑evidence (§3); launch/final ratio sanity
  (§4); tranche‑sum tolerance that reports the absolute gap (1% of $399m hides
  $4m); stated count from the last segment.

### What the proposals miss

1. **"Size" is not one thing.** Tier‑1 Size for Merna is notes *plus* term
   loans ($1.18bn = $1,058.6m + $122m); for IBRD 111‑112 it excludes $105m of
   parallel swaps. For supply analysis you must choose: note principal, or
   risk capital transferred. Tier 1 is "final terms" for the former only by
   convention, and the sum check must know which one it is checking.
2. **A third temporal tier.** Post‑issuance updates (resets: Lion's EL 1% →
   1.09%; loss events and the $195.84m IBRD payout; secondary marks "5 cents on
   the dollar") are currently glued to marketing updates. They are the only
   place this corpus records capital *leaving* — principal lost or returned —
   and deserve their own event kinds.
3. **Currency.** 50 of 1,311 index sizes are non‑USD and CHF prose is
   invisible; any cross‑deal aggregate needs a stated FX convention (Artemis's
   own parenthetical USD is available on most pages and should be captured as
   `size_usd_stated`).

### Given only this corpus: the strongest defensible analysis

Accepting round 2's conclusion: this is a **primary‑market ledger**, not a
flow record. What it *does* measure well, per deal: sponsor, final size,
issue month, perils, trigger, and — from prose — launch target, upsize %,
guidance range, final spread, EL, term. Those are the standard proxies for
how much investor capital the primary market is absorbing:

- **Build:** a monthly/quarterly *primary‑market absorption* series —
  (a) share of deals upsized and mean upsize %; (b) final spread minus
  guidance midpoint, in bps; (c) spread multiple (spread / EL); (d) gross
  issuance; (e) with term/maturity, **outstanding notional and net issuance**
  (issuance − scheduled maturities − known payouts). Net issuance is the
  closest thing to "net new capital the market had to find". Tightening vs
  guidance and upsizing are the demand‑pressure signals every market report
  uses; here you'd have them at deal granularity, 1996–2026. Index.csv alone
  already gives (d): 2025 = 124 deals, ~$25.7bn; 2021 = 98, ~$20.2bn.
- **Join:** (1) monthly NAV and shares‑outstanding for the UCITS cat bond
  funds (Schroders GAIA, GAM Star, Twelve, Plenum, LGT, Leadenhall) — flows =
  ΔAUM − return × AUM; (2) the Swiss Re Cat Bond Total Return index to
  separate performance from flow; (3) Artemis's own ILS fund‑manager AUM
  directory (semi‑annual) for the private‑fund total. With (1)–(3) you can
  ask whether absorption proxies lead or lag UCITS flows.
- **Unsupportable regardless:** subscriptions/redemptions for private funds
  and sidecars (the majority of AUM); secondary‑market flows; investor‑type
  breakdown except the handful of World Bank deals that publish it; any
  causal claim between flows and pricing; anything about the ~$50bn+ market
  total from a ~15–20% UCITS sample.

### Null results

- I could not find flow information in the prose. "Oversubscribed" and
  "fully subscribed" appear on a few pages; investor breakdown on one (IBRD).
  There is no subscription‑level data to extract, so no parser improvement
  changes the fund‑flow conclusion.
- I could not beat the structural Tier‑1 reader: across 39 pages, no Tier‑1
  value disagrees with `index.csv`, and no Tier‑1 value is wrong that I can
  see. Regex‑vs‑structure is settled in Tier 1's favour.
- I could not construct a genuine size that `_governed_by_loss_level` kills.
- I could not find a family that the roman‑numeral/series‑token merge joins
  wrongly; the residual splits ("Pte.", "Merna Re" vs "Merna Reinsurance")
  need sponsor+token matching, not another regex.

### Examined and judged correct

Tier‑1 reader and placeholder normalisation; `sentences()` splitter and its
unit cases; `_is_backward_reference` (year and series rules, parenthetical
stripping); `_clause_start` semicolon handling (Radnor 5/5 correct — M‑1B and
M‑1C are genuinely both $93,137,000); shared‑subject "each" bindings
(Hoplon); `equals_deal_total_accepted` (ResRe 2020); `_size_single`'s
terminal early return; class‑scoped cancellation guard; maturity‑after‑issue
check; conditional severity and EP ≤ EL ≤ AP; `check_tranche_sum` currency
guard; `parse_index.py`; `validate.py` parts‑vs‑whole and per‑tranche
arithmetic; the annual‑count validator's decision to validate counts only
(mortgage ILS scope gap correctly labelled `SCOPE_GAP`).
