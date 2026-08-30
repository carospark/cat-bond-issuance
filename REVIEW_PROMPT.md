# Adversarial review request (round 4): Artemis cat bond parser

Fourth review. The previous three found **8, 9 and 16 real defects** — every one
reproducible, several of them wrong values sitting in the output. **The count is
rising, not falling.** Either the defect density is not dropping, or each round
of fixes creates new surface. Work out which, and assume more remain.

## What this is

`src/` scrapes the Artemis.bm catastrophe bond deal directory (1,311 deals,
Dec 1996 – Aug 2026) into structured tables. ~3,100 lines. `raw/` holds 38
cached deal pages plus the index and one stray dashboard page.

**Do not make network requests.** `fetch()` is cache-first, and Artemis
restricts AI use of its content — work only from what is cached. Say explicitly
if you fetch anything. (An earlier reviewer declared no network activity while a
file appeared in `raw/`; the likely cause was found and fixed, but declare
regardless.)

`./.venv/bin/python tests/test_golden.py` → 290 checks over 17 pages, all
passing. Python 3.9: no match statements, no `X | Y` types.

**Two tiers.** Tier 1 = the "At a glance" list, read structurally, `high`
confidence, final terms. Tier 2 = "Full details" prose plus `Update N:` blocks,
regex-mined, `medium`/`low`, launch-time terms. Tier 2 never writes into a
Tier-1 field; Tier 1 *constrains* Tier 2. Risk metrics are tranche-level. Every
field is `{value, confidence, method, evidence, flags}`. `src/validate.py` runs
cross-field invariants. `data/queue.csv` orders a future crawl family-by-family,
chronologically ascending, because prose cites predecessor deals.

---

## First: verify the round-3 fixes actually work

I fixed the following after your last report. **Do not take the commit messages
on trust** — I have twice committed code that was broken in ways the tests did
not catch. Check each against `raw/`, and check whether the fix introduced a new
defect:

- **Sibling registry revived** (`sentences` shadowing). Now has a unit test.
  It then produced a false `LIKELY_CONTAMINATION` on FloodSmart's genuine
  `$575m`, so `size` was removed from `CHECK_FIELDS` as a Tier-1 field. Is that
  the right cut, or does it now under-audit?
- **`layer` and `term loan` added to the loss-level veto.** Everglades now reads
  `$400m → $1.5bn +275%`. Does the veto now kill a genuine size?
- **Range low-end matching** (`between $25m and $100m in size`). Correct for a
  launch state — is it wrong anywhere a range describes something else?
- **Update headers with dates** (`Update 2 (May 4th 2016):`). Operational Re
  went 1 → 5 states, IBRD 111-112 to 15. Are those segment labels usable, and
  did gluing stop in the right places?
- **Roman numerals to XXX and the orphaned `-N` strip** in `build_queue.py`.
  1,108 deals now in serial families. Any wrong merge?
- **Same-month sibling ordering** reversed to oldest-first.
- **`fetch()` cache-key normalisation**, plus three modules that derived the
  cache filename independently and silently emitted zero rows when it changed.

## Still open from your report — I have not touched these

Forward-binding in `_bindings_by_label` (Merna's `Class A – $256m Class B –
$647.6m` binds each amount to the *next* label); the currency gaps (CHF, EUR
as a word, C$, NZ$ — Operational Re still 0/3 sizes); `coupon of X% to Y%`
returning the low end; tranche delta lacking tolerance; and the eight guards
your mutation table showed as deletable-green.

**Your deepest finding was that Tier-1 "Size" is not one thing** — Merna's
`$1.18bn` includes `$122m` of term loans, IBRD's excludes swaps. That
undermines parts-vs-whole wherever it holds. **How widespread is it across the
38 cached pages, and what is the right representation?** This matters more than
any single parse bug.

## Where to look that nobody has

- **The outputs, not the code.** `data/deals.csv` (38 × 100), `tranches.csv`
  (56 × 24), `review_long.csv` (1,736 rows). Are the values right? Sample
  aggressively against `raw/`. Prior rounds reviewed logic; nobody has audited
  the product.
- **`data/queue.csv` as a crawl plan.** 1,311 rows, and only 38 pages have ever
  been parsed. What breaks at scale that 38 pages cannot show — pathological
  names, families of 69, deals whose page does not exist?
- **My two process failures**, which may indicate classes of bug rather than
  incidents: I changed a cache key without migrating (17 needless refetches),
  and committed a builder that emitted zero rows because a second module
  duplicated a key derivation. Where else is a derivation, constant or
  assumption duplicated across modules such that changing one silently breaks
  another?

---

## Part 2: design and analysis

Your round-3 conclusion was that the strongest defensible output is a
**primary-market absorption series** — upsize share, final spread vs guidance
midpoint, spread multiple, gross issuance, net issuance — joined to UCITS
cat-bond fund NAV, the Swiss Re index and Artemis's ILS-manager AUM directory,
with private-fund subscriptions, secondary flows and causal claims
unsupportable regardless.

Push that from a conclusion to a plan:

1. **Which fields does that series actually need**, and which of them does the
   parser produce reliably today? Name the ones that are not yet trustworthy.
2. **What is the minimum viable version** using only this corpus, with no join?
3. **What would falsify it?** If the absorption series were misleading, how
   would that show up?
4. You said post-issuance updates (resets, payouts, marks) are a third temporal
   tier and the only place the corpus records capital *leaving*. **How should
   that be modelled**, and how much of it is actually present across the 38
   pages?
5. Given the defect trend, **is continuing to patch this parser the right
   call**, or should the Tier-2 pipeline be rebuilt around typed events before
   the crawl? Answer concretely — cost, what carries over, how I would know.

**Be honest about null results.** "I could not beat the current approach on X,
because Y" is a useful answer. Do not invent improvements to look useful.

---

## Output

**Part 1 (defects).** file:line, what breaks, a concrete input from `raw/`,
severity, minimal fix. Ranked. Five real defects with reproductions beat thirty
speculative notes. Say in one line where a focus area is sound.

**Part 2 (design).** Kept separate. What it replaces, the benefit, the cost,
what it breaks, how I would verify it helped. List what you judged already
correct — that list is as valuable as the proposals.
