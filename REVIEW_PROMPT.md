# Adversarial review request (round 2): Artemis cat bond parser

Review the parsing code and logic in `src/` and `tests/`. I want correctness
problems and unsound reasoning, not style. Be adversarial and specific.

**Do not make network requests.** `fetch()` is cache-first; `raw/` holds 29
cached pages (the deal-directory index plus 28 deal pages). The source also
restricts AI use of its content, so work only from what is already cached.

Run tests with `./.venv/bin/python tests/test_golden.py` (284 checks, currently
all passing). Python 3.9 — no match statements, no `X | Y` type syntax.

---

## Round 1 outcome — do NOT re-report these

Round 1 found 8 wrong outputs behind 153 passing tests. All were reproduced;
all are now fixed or explicitly flagged:

- year-rule off-by-one (`< year - 1`) admitting a predecessor's coupon
- `CLASS_RE` case-sensitivity (lowercase "class A" dropped) and stopword
  over-match ("class of" → a tranche named `Class OF`)
- tranche windows snapping to sentence rather than clause
- a guidance range's low end returned as the settled spread
- same-year sibling contamination
- stated-multi deals given single-tranche economics
- dollar-only tranche-size grammar
- deal-level `size_history` recording a component's size

Also since fixed: Triangle/Radnor label-to-amount misattribution, Hoplon's
"€25m each" shared subject, ResRe 2020 Class 13 (suppressed because it equals
the deal total, which is correct there since Class 12 was never issued), and
sentence segmentation.

Validation is down to 3 VIOLATIONs, all the same shape: ResRe 2010, Trinity Re
and Mosaic Re II state a tranche count but never describe the tranches. One row
plus `tranche_count_understated` is intentional — the data is not on the page
and fabricating rows would invent it.

---

## Priority: the code written to fix round 1 has never been reviewed

Assume the fixes introduced new defects. Concentrate here.

**A. The label→amount binding map** (`_bindings_by_label`, `_bound_to_other_label`,
the fallback in `_size_multi`). Amounts are matched to class labels across the
WHOLE prose, then used to veto candidates inside a window and to supply sizes
when a window yields none. Failure modes to hunt: an amount legitimately shared
by two labels; the same amount appearing for different tranches; a label
mentioned in a comparative clause capturing an amount; binding beating a more
specific in-window value; `Class 1` vs `Class 1A` collisions.

**B. Shared-subject "each" distribution.** One amount is copied to every class
named in a sentence containing "each". Where does that over-distribute — e.g. a
sentence naming three classes where "each" applies to only two, or "each year"
/ "each event" rather than each tranche?

**C. The sentence segmenter** (`sentences`, `_sentence_spans`). U.S./U.K./D.C.
never terminate; company suffixes (Ltd/Inc/Co/Corp/plc/No/St/Mr/Ms/Dr) split
only before an uppercase next character. Find text where that is wrong in
either direction. Note the span cache is keyed on full text — check it cannot
return stale or wrong spans.

**D. Deal-scope discriminators for `size_history`** (`CLASS_SCOPED_RE`,
`AGGREGATE_RE`). A sentence naming any `Class X` is rejected as a deal state,
and enumerated amounts without an aggregate word are rejected. Where does that
discard a genuine deal state, or admit a tranche one?

**E. `equals_deal_total_accepted`.** When the only tranche-size candidate equals
the Tier-1 total it is now accepted rather than dropped. Justified for ResRe
2020; where is it wrong?

**F. `tranche_not_issued`.** Detected by `"<label> ... will not be issued"`
within 120 chars. Check the window and the negation handling.

---

## Also worth checking

**G. Invariants** (`src/validate.py`). Cross-source vs the index, parts-vs-whole
at launch and final, `EL <= attachment`, `exhaustion <= EL <= attachment`,
maturity after issue, completeness of labelled tranches, stated tranche count.
What must hold in this data that is not checked? Two rules were deliberately
REJECTED as not invariant and I want that judgement challenged: `spread > EL`
(collateral yield) and "no deal-level state may equal a tranche size"
(Kilimanjaro launched at $300m and its Class D settled at $300m).

**H. Test quality.** 284 checks over 17 pages, including a `REJECT` table of
known-wrong values and unit tests for `_is_backward_reference` and `sentences`.
Which of the fixes above could I break without a test failing? Are any guards
vacuous — passing when extraction returns nothing, or restating the
implementation rather than the source text?

**I. Regex hygiene.** `_M` ends with `\s*`, which has already caused one regex
to silently never match (a following `\s+` could not fire). Look for the same
class of bug elsewhere. Numeric grammars such as `[\d.]+` admit malformed values
like `...%`.

---

## Part 2: challenge the design, not just the defects

Everything above asks "is this correct?". This part asks "is this the right
approach at all?" — including decisions that predate the bugs and that nobody
has questioned. Propose things I did not think of. Ignore the boundaries of the
existing code.

Load-bearing decisions, all open to challenge:

1. **Regex extraction over prose.** Every Tier-2 value comes from anchored
   regexes with a confidence grade. Is there a better instrument — a real
   grammar, a dependency parse, an LLM extraction pass with the invariants as
   the check, something else? What would it cost, and where would it be worse?
2. **The two-tier model** (structured summary = final terms; prose = launch-time
   terms, with Tier 1 constraining Tier 2). Sound abstraction, or is it
   smuggling an assumption that will break on pages neither of us has seen?
3. **Windows as the unit of tranche scope.** Prose is sliced per class label and
   values mined inside each slice. The binding map already works around this.
   Is windowing the wrong primitive — should extraction be
   entity-first (find tranches, then attach values) rather than span-first?
4. **The per-field record** `{value, confidence, method, evidence, flags}` and a
   3-level confidence rubric graded by extraction method. Right granularity?
   Should confidence be numeric, or per-invariant rather than per-field?
5. **Validation as a separate post-hoc pass** rather than inline constraints
   that steer extraction. Would constraint-first extraction (choose the
   candidate set that satisfies parts-vs-whole) be better than extract-then-check?
6. **Flat CSVs** (`deals` + `tranches` + a long-format review sheet). Right
   shape for fund-flow analysis, or should this be normalised differently —
   an events table, a bitemporal record of what was known when?
7. **Golden tests over 17 cached fixtures.** Would property-based testing,
   differential testing, or generated cases catch more than hand-picked pages?
8. **Crawl design** — family-grouped ascending, 2s delay, cache-first, with a
   sibling registry built as it goes. Better ordering or architecture?

Also: **what would you do differently if you started this from scratch today,
knowing the corpus?** And **what is missing entirely** — a capability, a check,
an output that this project should have and does not?

**Be honest about the null result.** If a decision is already the right one,
say so in a line and move on. Do not invent improvements to look useful, and do
not propose a rewrite whose benefit you cannot name concretely. "I could not
beat the current approach on X, because Y" is a genuinely useful answer and I
would rather have it than a plausible-sounding alternative. Where you do propose
a change, state what it costs, what it breaks, and how I would know it worked.

---

## Output

**Part 1 (defects).** For each finding: file:line, what breaks, a concrete
input from `raw/` that triggers it, severity, and the minimal fix. Rank by
severity. Prefer 5 real defects with reproductions over 30 speculative notes.
If a focus area is sound, say so in one line and move on.

**Part 2 (design).** Keep it separate from Part 1 so I can act on defects
without wading through redesigns. For each proposal: what it replaces, the
concrete benefit, the cost, what it breaks, and how I would verify it helped.
List the decisions you examined and judged already correct — that list is as
valuable to me as the proposals.
