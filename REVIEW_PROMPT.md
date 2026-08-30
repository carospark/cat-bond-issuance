# Adversarial review request (round 2): Artemis cat bond parser

## Round 1 outcome — do not re-report these

A previous review found 8 wrong outputs behind 153 passing tests. All 8 were
reproduced; 7 are fixed and the 8th is now flagged rather than silent:

- year-rule off-by-one (`< year - 1`), which let a predecessor's coupon through
- `CLASS_RE` case-sensitivity (lowercase "class A" dropped) and stopword
  over-match ("class of" -> a tranche called `Class OF`)
- tranche windows snapping to sentence rather than clause, losing sizes in
  semicolon-separated lists
- a guidance range's low end returned as the settled spread
- same-year sibling contamination (foreign-series exclusion added)
- stated-multi deals given single-tranche economics
- dollar-only tranche-size grammar
- deal-level `size_history` recording a component's size

Tests went 153 -> 263: a `REJECT` table of known-wrong values, predicate unit
tests, and mutation testing of each guard. Two proposed rules were REJECTED as
not actually invariant, and I would like that judgement checked: `spread > EL`
(collateral yield) and "no deal state may equal a tranche size" (Kilimanjaro
launched at $300m and its Class D settled at $300m).

## Known-open — confirm or refute the diagnosis, do not just restate it

1. Hoplon II Class A/B have no sizes: "EUR 25m each" shared-subject phrasing.
2. Triangle Re Class B-1 and ResRe 2020 Class 12/13 have no sizes.
3. Sentence segmentation still splits on "U.S."/"Ltd."/"Inc.".
4. Seaside 2026-61 yields a false `Class 3` (an insurer regulatory class).
5. ResRe 2010 / Trinity / Mosaic state a tranche count but never describe the
   tranches; one row plus `tranche_count_understated` is intentional.

Priority for this round: defects OUTSIDE the above list, and any place a round-1
fix is wrong, incomplete, or has introduced a new failure.



Review the parsing code and logic in `src/` and `tests/`. I want correctness
problems and unsound reasoning, not style. Be adversarial and specific.

## What this does

Scrapes the Artemis.bm catastrophe bond deal directory (1,311 deals, Dec 1996 -
Aug 2026) into structured data. `raw/` holds 29 cached HTML pages: the deal-directory index plus 28 deal pages.

**Do not make network requests.** `fetch()` is cache-first and everything under
review runs off `raw/`. The source also restricts AI use of its content, so work
only from what is already cached.

Run tests with `./.venv/bin/python tests/test_golden.py` (263 checks, currently
all passing). Python is 3.9 - no match statements, no `X | Y` type syntax.

## Architecture (read `src/parse_deal.py` docstrings first)

- **Tier 1** = the page's "At a glance" `<ul>`, a real key/value block. Holds
  FINAL terms. Read structurally, confidence `high`.
- **Tier 2** = "Full details" prose, written incrementally as the deal markets,
  so it preserves LAUNCH-time terms and later `Update N:` states. Regex-mined,
  confidence `medium`/`low`.
- Every field is a record: `{value, confidence, method, evidence, flags}`.
- Risk metrics (EL, attachment/exhaustion probability, spread) are TRANCHE-level
  and live in `parse_tranches`, never on the deal row.
- `src/validate.py` holds cross-field invariants; `src/sibling_registry.py`
  detects figures belonging to a predecessor deal in the same programme.

## Intentional - do NOT report these as bugs

1. Weak/fallback regexes were deliberately DELETED rather than repaired. An
   honest `None` is preferred over a plausible wrong value.
2. Source placeholders ("Unknown", "?", "Not issued") map to `value=None` with
   confidence `high` - we are confident the SOURCE is silent. `raw_value` keeps
   the original string.
3. Tier 2 never writes into a Tier-1 field, even when they disagree. Tier 1
   constrains Tier 2 (single tranche: size comes from Tier 1; multi-tranche: no
   tranche may equal the deal total).
4. Deals whose prose states a tranche count but never describes the tranches
   (Trinity Re, Mosaic Re II, ResRe 2010) yield ONE row plus a
   `tranche_count_understated` flag. Fabricating rows would invent data.
5. Long, explanatory comments recording why a rule exists are deliberate.

## Focus your review here

**A. Sentence segmentation (known weak - assess the blast radius).**
`re.split(r"(?<=\.)\s+", text)` is used for label scoping, sizing context and
backward-reference detection. Measured: 34 mid-sentence abbreviation splits
across the 28 cached pages ("U.S. " x15, "Ltd. " x17, "Inc. " x2). Which
specific extractions does this corrupt, and what is the minimal correct fix?

**B. `_tranche_windows` boundary logic.** Windows snap to sentence starts
because Artemis writes size before the class label ("A $300 million Class A
tranche"). There is a guard for two labels in one sentence. Find cases where
snapping over- or under-reaches, or where the guard misfires.

**C. Regex correctness.** `TIER2_PATTERNS`, `TRANCHE_SIZE_RES`, `CLASS_RE`,
`MONEY_RE`, `MONTHS`. Look for catastrophic backtracking, greedy matches
crossing sentence boundaries, alternation-order bugs (MONTHS is longest-first
deliberately), and anchors that admit values they should not.

**D. `_money_to_number` and currency.** It takes the FIRST number in a string,
so "€100m ($113m)" parses as 100. Where does that assumption leak into a
comparison or a delta that should have been refused?

**E. Ordering assumptions.** `size_history` and tranche size lists assume
document order == chronological order (first mention = launch, last = final).
Where is that false?

**F. Silent failures.** Anywhere an empty result, a `continue`, or a failed
match is treated as success, or produces no flag. Two such bugs already shipped
here; assume more.

**G. Invariant gaps.** `validate.py` covers cross-source (index vs detail),
parts-vs-whole, arithmetic (EL<=AP), ordering (EP<=EL<=AP), economics
(spread>EL), self-description (stated tranche count). What relationships MUST
hold in this data that are not yet checked?

**H. Test quality.** Are the 263 golden checks actually discriminating, or are
any tautological / vacuously passing? Which of the fixes in `parse_deal.py`
could I break without a test failing?

## Output

For each finding: file:line, what breaks, a concrete input that triggers it,
severity, and the minimal fix. Rank by severity. Prefer 5 real defects with
reproductions over 30 speculative notes. If a "Focus" area is actually sound,
say so briefly and move on.
