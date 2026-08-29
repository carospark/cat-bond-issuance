# Checkpoint — 2026-08-29

Read this first when picking the project back up. Written to be understood cold.

---

## Where everything is

Everything now lives in `~/Desktop/cat_bond_fund_flow`. The old `~/catbond-map`
was merged in and deleted — one folder, one git repo, one memory key.

```
src/parse_deal.py          the parser (the bulk of the work)
src/validate.py            cross-field invariants
src/sibling_registry.py    cross-deal contamination detection
src/build_queue.py         crawl order (family-grouped, chronological)
src/build_review_bundle.py builds the CSVs below
tests/test_golden.py       259 checks, offline, run this first
data/                      the review bundle (gitignored)
raw/                       29 cached Artemis pages (gitignored)
PROJECT_CONTEXT.md         draft of the project's CLAUDE.md
REVIEW_PROMPT.md           the adversarial-review prompt for Codex
```

Run anything with `./.venv/bin/python`. Start with:

```bash
./.venv/bin/python tests/test_golden.py     # expect 259/259
```

---

## Nothing has been pushed

The git remote is **public**: `github.com/carospark/cat_bond_fund_flow`.

There is one local commit checkpointing this work. **It has not been pushed.**
Decide that sober.

`raw/` and `data/*.csv` are gitignored on purpose: Artemis forbids reproduction
or publication of its directory content without a licence. The code that
produces them is tracked; their content is not. Do not remove those rules
without deciding the licensing question first.

---

## State of the parser

Two-tier model: Tier 1 (the "At a glance" list) holds **final** terms and is
authoritative; Tier 2 (prose) holds **launch-time** terms and is regex-mined.
Tier 1 constrains Tier 2. Risk metrics are tranche-level, in `tranches.csv`.
Every field carries `{value, confidence, method, evidence, flags}`.

An adversarial Codex review found **8 wrong outputs behind 153 passing tests**.
All 8 were reproduced and 7 fixed:

| fixed | was |
|---|---|
| year rule off-by-one | ResRe 2020 reported the 2019 bond's 8.25% coupon as its own |
| `CLASS_RE` case-sensitive | Atlantic: 1 tranche + fabricated +200%; now 2, sum OK |
| windows snapped to sentence not clause | Radnor: 1 of 5 sizes; now 5 of 5, sum OK |
| guidance sold as settled spread | Hoplon returned 11.25%, a range's low end |
| same-year sibling contamination | new foreign-series exclusion |
| stated-multi got single-tranche size | Mosaic: fabricated +80%; now refuses to guess |
| dollar-only tranche sizes | widened to EUR/GBP/JPY |

`spread > EL` was demoted from VIOLATION to WARN — total investor return
includes collateral yield, so it is not a hard invariant.

---

## OPEN — start here

`data/validation.csv` lists **7 VIOLATIONs**. All were silent before; they now
fail loudly. None are fixed.

1. **`size_history` records a TRANCHE size as the deal state.** Atlantic trips
   `tranche_sum_launch +200%` because the deal's launch state holds $100m (one
   tranche) not $300m. Same shape on FloodSmart and Kilimanjaro update states.
   Fix: require deal-level anchors (deal / issuance / offering target /
   aggregate secured) and reject class-scoped sentences.
2. **Hoplon Class A/B have no sizes** — "€25m each" shared construction.
3. **Triangle Class B-1, ResRe 2020 Class 12/13** — no sizes extracted.
4. **Sentence segmentation.** `re.split(r"(?<=\.)\s+", ...)` splits on "U.S.",
   "Ltd.", "Inc." — 34 times across 29 cached pages. It has not yet corrupted a
   scalar, but it corrupts scope and evidence. The reviewed fix is one central
   sentence-span helper (treat "U.S." as nonterminal; merge "Ltd./Inc."
   fragments when the next token is lowercase or parenthetical; keep the
   boundary before a new uppercase subject) feeding `_sentence_at`,
   `_clause_start`, sizing, stated-count validation and sibling auditing.
5. **Seaside's false `Class 3`** — an insurer regulatory class read as a tranche.
6. **Unlabelled multi-tranche deals** (ResRe 2010, Trinity 1998, Mosaic Re II)
   state a count but never describe the tranches. The data is not on the page.
   Flagged `tranche_count_understated`. **Do not fabricate rows.**

---

## Not yet done, deliberately

- **The full crawl.** 1,311 pages, ~45 min at the 2s delay. `data/queue.csv` has
  the order. Do the open items above first — several concentrate in older deals.
- **`CLAUDE.md`.** Content is written as `PROJECT_CONTEXT.md`. It is not named
  `CLAUDE.md` because that filename sits in the protected team-knowledge layer
  and this project is not on the team-brain write allowlist. Either rename it,
  or allowlist this project from `~/climate-pnl`.
- **The guard-hook patch.** The team-brain guard has a real blind spot: it only
  recognises a protected filename after whitespace or a quote, so
  `>> ~/.claude/.../MEMORY.md` is allowed while `>> MEMORY.md` is blocked. It is
  also over-broad on reads (it blocked plain `ls`). A patch was drafted and then
  dropped at your request — it must be applied from `~/climate-pnl`.

---

## Testing discipline (hard-won, do not regress)

- **259 checks, all offline.** Golden tests over `raw/` before any regex surgery.
- **`REJECT` table**: assert the absence of specific known-wrong values. A guard
  that only checks non-`None` passes when extraction fails entirely — and did.
- **Unit-test predicates, not just end-to-end.** Redundant defences mask each
  other: restoring the year off-by-one left the whole suite green because the
  foreign-series rule caught the same sentences.
- **Mutation-test every guard**, and verify the mutation actually applied. A
  syntax-erroring one-liner once reported "251/251 passed" that meant nothing.

## Data caveats for the analysis itself

- **EL / attachment / spread are sparse before ~2010.** Artemis did not publish
  them for older deals. Any such time series effectively starts around 2010.
- **Low Tier-1 fill means a private deal, not an old one.** Non-private deals
  read 9/9 in every decade. Triage by `deal_is_private`, never by year.
- **Crawl order is a correctness requirement**, not tidiness: prose cites
  predecessor deals, so older siblings must be parsed first.
