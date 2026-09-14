# Handoff

Read `PARSER_BACKLOG.md` first. It is the current state: what is parsed, what
is validated, and everything still worth fixing, ordered by value per hour.

## NEXT — start here (set 2026-09-14)

1. **Human-check five deals** against their Artemis pages, verifying the
   launch-size reading from commit 4df0cde:
   - PoleStar Re 2024-3: launch $75m (not the $800m attachment point, not the
     "$400m maximum" speculation)
   - Kilimanjaro III Re 2026-2: launch None, flagged
     `launch_target_shared_across_series` ($530m is across two entries)
   - Sanders Re III 2022-2: launch $250m (not Series 2022-1's $550m)
   - Everglades Re II 2023-1/2023-2: one entry for two series, so "$600m
     across the two series" is kept as this deal's update
   - Meadows Ltd 2025-1: launch $125m (not the investor's $8bn AUM)
2. **Backlog item 10**: size-change series correlation is 0.72 but the level
   runs ~11pp high. First step: include `no_size_change_detected` deals as 0
   and see if the level closes.
3. **Rename the project.** The repo is `cat_bond_fund_flow` but the work is
   data extraction, not fund flow. Rename folder, GitHub remote, README,
   the analysis repo's companion link, and this doc once a name is chosen.

Commits e0688a1 and 4df0cde are local and **not pushed**.

## State (2026-09-14)

- Full crawl done: 1,311 deals parsed; `raw/` and `data/` are gitignored under
  the Artemis licence rule (`DATA_POLICY.md`). Code is tracked, content is not.
- `./.venv/bin/python tests/test_golden.py` — expect 626/626, offline.
- `src/validate_dashboards.py` reproduces every publisher comparison. Issuance,
  trigger mix and EL validate; spread carries a bias (backlog 9); the offering
  size-change series does NOT validate (backlog 10).
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
