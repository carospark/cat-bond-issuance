# Adversarial review request (round 5): Artemis cat bond parser

Fifth review. Rounds 1–4 found **8, 9, 16 and ~16** reproducible defects. You
did rounds 3 and 4. Assume more remain.

## Where to work

**This worktree only:** `~/Desktop/cat_bond_fund_flow-wt/claude-parser`, branch
`claude-parser`, one commit ahead of `main`. Another agent is working `main` in
the primary checkout — do not touch it. `raw/`, `.venv/`, `data/raw/` and the
`data/*.csv` outputs are symlinks into that checkout; read them, don't copy.

`./.venv/bin/python tests/test_golden.py` → 532 checks, all passing. Python 3.9.
~4,400 lines. `raw/` now holds **231 cached deal pages** (was 39) — random
samples have been drawn since your last look.

**No network requests.** Everything is cached; Artemis restricts AI use of its
content. Declare any fetch explicitly.

---

## What changed since round 4 — none of it reviewed

I measured the parser on **60 random deals** rather than the 38 hand-picked ones
we had been grading ourselves against. Violation rate: **30% random vs 8%
curated.** Two of the wrong values were classes already "fixed" twice — Market
Re's deal total leaking into a tranche, Alamo's `$2.6 billion` loss level read
as a size. A veto only covers the phrasing that prompted it.

So I added a layer, in `src/mentions.py`:

1. **Kind classification.** Every money mention is typed once against the
   *nearest* governing cue — attachment, exhaustion, deductible, layer, term
   loan, payout, trigger, size. `_governed_by_loss_level` now delegates to it
   and accepts only `size` or `unknown` (`unknown` admitted deliberately, to
   preserve discovery's recall).
2. **Constraint selection** (`solve_tranche_sizes`, `_reconcile_tranche_sizes`).
   Where several typed candidates exist per tranche, prefer the combination
   whose parts equal the whole. The parts-vs-whole invariant now helps *choose*
   the answer instead of only checking it.

Market Re now reads `$22m + $8m = $30m`, Alamo `$300m + $400m = $700m`.

Also: proximity beats priority in classification; `_money_to_number` requires a
leading digit (it crashed on a bare comma via `float("")`); the sampler draws
from all 1,311 deals with a fixed seed, because sampling the *uncached* pool
meant every run measured a different set.

---

## Priority A: does the constraint hide errors?

**In round 3 you warned that "a solver can hide source inconsistencies if
constraints are treated as absolute."** I have now built the thing you warned
about. Test that warning directly.

- Where does `_reconcile_tranche_sizes` select a combination that sums
  correctly but is **wrong**? Coincidental arithmetic is the failure mode:
  candidates that happen to add up while belonging to different quantities.
- It prefers the combination with the most distinct values, to avoid one figure
  counted twice. When is that heuristic wrong — genuinely equal tranches?
- It silently returns when currencies are mixed, when a label has no candidate,
  and when no combination reconciles. Are those the right refusals, and are
  they visible enough? A silent return leaves the pre-constraint value in place
  with no flag saying a constraint was attempted and failed.
- Does it ever overwrite a **correct** discovered value with an incorrect one
  that happens to reconcile?

## Priority B: the benchmark is measuring the wrong thing

The reproducible number is **seed 20260831, n=80: 22% of deals carry a
violation, 0.34 per deal, 0 crashes.** But violations only count what
`validate.py` knows to check. **A wrong value that satisfies every invariant is
invisible to this measurement**, and the constraint now actively selects values
that satisfy one of them.

- How would you measure *accuracy* rather than *violation rate*? What would a
  ground-truth exercise look like, and how large a hand-labelled sample would
  be needed to say something defensible?
- Is 80 enough for a 22% rate? What is the confidence interval, and what
  stratification would make it more informative than a uniform draw?
- Take a handful of deals the validator passes cleanly and check them by hand
  against `raw/`. Silent wrong values are the thing I most want found.

## Priority C: the newly surfaced arithmetic violations

The n=80 run produced one `EL <= attachment_probability` and one
`severity <= 1` — arithmetic impossibilities, so a wrong EL or attachment
probability. Risk metrics have had far less attention than sizes. Diagnose
those two and say whether they are instances or a class.

## Priority D: still open from your own reports

Forward-binding edge cases; the `coupon of X% to Y%` low-end return; tranche
delta tolerance; the guards your mutation table showed deletable-green; and
your deepest finding — **Tier-1 "Size" is not one thing** (Merna includes
`$122m` of term loans, IBRD excludes swaps). Has the constraint made that
worse, since it now enforces parts-vs-whole against a headline that sometimes
measures something different from the sum of its notes?

---

## Part 2: design

You proposed typed events and constraint selection. I have implemented a
narrow version of both. **Was the narrow version the right call, or does the
half-measure carry the costs of both approaches?** Specifically: `mentions.py`
now duplicates money and class-label grammars that already exist in
`parse_deal.py` — the duplicated-derivation class that has bitten this project
twice.

Then: given 231 cached pages and a working constraint layer, **is the parser
good enough to crawl the remaining 1,080?** Answer with a number and a
criterion, not a judgement. If not, what specifically must improve first?

**Be honest about null results.** "I could not find a case where the constraint
selects wrongly" is a genuinely useful answer and I would rather have it than
a speculative one.

---

## Output

**Part 1 (defects).** file:line, what breaks, a concrete input from `raw/`,
severity, minimal fix. Ranked. Reproductions over speculation.

**Part 2 (design).** Separate. What it replaces, benefit, cost, what it breaks,
how I would verify. List what you judged already correct.
