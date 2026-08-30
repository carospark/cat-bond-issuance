# Adversarial review request (round 3): Artemis cat bond parser

You are the third independent reviewer. The two before you found **8 and 9 real
defects respectively**, every one reproducible, several of them wrong values
sitting in the output. Assume more remain. The most valuable thing you can do is
find the ones your predecessors and I both missed.

## What this is

`src/` scrapes the Artemis.bm catastrophe bond deal directory (1,311 deals,
Dec 1996 – Aug 2026) into structured tables. The eventual goal is analysing
capital flows into and out of cat bond funds.

**Do not make network requests.** `fetch()` is cache-first and `raw/` holds 39
cached deal pages plus one dashboard page. Artemis restricts AI use of its
content, so work only from what is already cached. (A previous reviewer stated
it made no network requests, yet a file appeared in `raw/` during its run. If
you fetch anything, say so explicitly.)

Run tests with `./.venv/bin/python tests/test_golden.py` — 288 checks over 17
pages, currently all passing. Python 3.9: no match statements, no `X | Y` types.
~3,000 lines across `src/` and `tests/`.

## Architecture in one paragraph

Two tiers. **Tier 1** is the page's "At a glance" list — read structurally,
confidence `high`, holds final terms. **Tier 2** is the "Full details" prose
plus appended `Update N:` blocks — regex-mined, confidence `medium`/`low`,
holds launch-time terms. Tier 2 never writes into a Tier-1 field; Tier 1
*constrains* Tier 2 (single tranche: size comes from Tier 1; multi-tranche: no
tranche may equal the deal total). Risk metrics are tranche-level. Every field
is a record: `{value, confidence, method, evidence, flags}`. `src/validate.py`
runs cross-field invariants afterwards. `data/queue.csv` orders a future crawl
family-by-family, chronologically ascending, because prose cites predecessor
deals.

---

## Already found — do NOT re-report

**Round 1:** year-rule off-by-one; `CLASS_RE` case-sensitivity and stopword
over-match; windows snapping to sentence not clause; a guidance range's low end
returned as settled spread; same-year sibling contamination; stated-multi deals
given single-tranche economics; dollar-only size grammar; `size_history`
recording a component's size.

**Round 2:** cancelled deals reporting issued principal; a deductible becoming
a launch size with a +400% phantom upsize; negated language ("did not change in
size") accepted as resize corroboration; cancellation detected from a
tranche-scoped sentence.

**Known open, already diagnosed — confirm, refute, or fix, but do not merely
restate:**

1. Seaside 2026-61 yields a false `Class 3` (a Bermuda regulatory class, not a
   tranche) — and it is in the golden `TRANCHE_SUM_OK` set, so the invented
   structure is positively validated by the suite.
2. Multi-amount rejection discards genuine deal states: ResRe 2010's
   "preliminary size of $375m … final amount issued was $405m" yields nothing.
3. `validate()` is not called by any tracked output path, so
   `data/validation.csv` is not reproducible from the tracked pipeline.
4. `attachment < exhaustion` in `validate.py` reads `exhaustion_point`, a field
   no parser path creates. Dead code.
5. Stated tranche count takes the first match: ResRe 2026 says "two tranches"
   (a subgroup) before "three tranches" (the total).
6. The binding fallback in `_size_multi` bypasses the deal-total constraint,
   producing contradictory flags (`deal_total_excluded=4;size_from_label_binding`).
7. Segmentation splits "This Finca Re Ltd. Series 2022-1" before "Series".
8. ResRe 2010 / Trinity / Mosaic state a tranche count but never describe the
   tranches. One row plus `tranche_count_understated` is intentional — the data
   is not on the page and fabricating rows would invent it.

---

## Priority A: the round-2 fixes, which nobody has reviewed

- **`deal_status` / terminal status.** `TERMINAL_STATUS`, `CANCELLED_RE`, and
  the early return in `_size_single`. Cancellation is recognised only in
  sentences naming no class. Where does that miss a real cancellation, or fire
  on a deal that did issue? What about partial issuance, or a deal cancelled
  and later re-launched?
- **`_governed_by_loss_level`.** A ±45-character window around an amount vetoes
  it if a loss-level noun appears. Find a genuine size killed by this, or a
  deductible that still slips through.
- **`NEGATED_RESIZE_RE`.** Find negation forms it misses, and any place it
  wrongly suppresses a real resize.

## Priority B: code no reviewer has looked at

`src/parse_index.py`, `src/fetch.py`, `src/build_queue.py`,
`src/build_review_bundle.py`, `src/sibling_registry.py`.

Specifically: the **family-merging** logic in `build_queue.py` strips roman
numerals and embedded years so "Windmill I/II/III Re" group together. Where does
that merge unrelated programmes or split related ones? Correct crawl order is a
*correctness* requirement here, not tidiness — the sibling registry depends on
it — so an error there corrupts everything downstream. Also: is the cache key in
`fetch.py` sound, and is `index.csv` parsed correctly against `raw/`?

## Priority C: the ten newest pages, barely tested

Recently cached and deliberately chosen to stress untested dimensions. Only
three have been examined:

```
Baltic PCC 2025-1      GBP, Pool Re terrorism, PCC vehicle
Crystal Credit         "EUR 252m" — currency as a WORD, 2006
Queen Street X Re      Not issued
Everglades Re 2014-1   $1.5bn
Merna Reinsurance      $1.18bn, 2007          [Class A has no size]
IBRD CAR 111-112       pandemic, range in the name  [Class A has no size]
Beazley (Cairney)      cyber, parenthetical name
Operational Re         operational risk  [3/3 classes have no size; count 2 vs 3]
Lion I Re              €190m ($262m), no series token in the name
Eclipse Re 2021-01A    nine same-family same-year siblings
```

Operational Re is probably the most informative page in the corpus right now.

## Priority D: tests

Round 2 judged several guards vacuous: `REJECT` passes under total extraction
failure; `tranche_not_issued` can be deleted with the suite still green; nothing
asserts how many checks ran, so conditional guards can vanish along with the
data they depend on; validator tests only check severity spelling and always
pass `index_row=None`, so cross-source checks never run.

Which of the fixes above could I break without a test failing? Mutation-test if
that is the fastest way to find out.

---

## Part 2: challenge the design

Round 2 proposed typed lifecycle events (target / range / revised / priced /
issued / cancelled), entity-first tranche resolution instead of span windows,
and a two-pass crawl so output stops depending on parse order. It judged these
already correct: cache-first retrieval, Tier 1 as stronger evidence, honest
`None` over a plausible fallback, separate deal/tranche projections,
independent post-hoc validation, categorical rather than numeric confidence,
golden fixtures, and rejecting both `spread > EL` and "no deal state may equal a
tranche size" as invariants.

**Do you agree?** Say where you would diverge, and what those proposals miss.

Then the larger question. Round 2 concluded that **issuance data is not
fund-flow data** — Artemis measures primary-market supply, not subscriptions,
redemptions, AUM changes or performance — so this source alone cannot answer the
project's stated question. Assume that is right. **Given only this corpus, what
is the strongest defensible analysis?** What would you build, what second
dataset would you join, and what claims would remain unsupportable?

**Be honest about null results.** "I could not beat the current approach on X,
because Y" is a genuinely useful answer. Do not invent improvements to look
useful, and do not propose a rewrite whose benefit you cannot name.

---

## Output

**Part 1 (defects).** For each: file:line, what breaks, a concrete input from
`raw/` that triggers it, severity, minimal fix. Ranked by severity. Five real
defects with reproductions beat thirty speculative notes. If a focus area is
sound, say so in one line.

**Part 2 (design).** Kept separate. For each proposal: what it replaces, the
concrete benefit, the cost, what it breaks, how I would verify it helped. List
what you examined and judged already correct — that list is as valuable as the
proposals.
