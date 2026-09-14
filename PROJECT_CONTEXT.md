# cat-bond-issuance — project context

Analysis of capital flows into and out of catastrophe bond funds, built on the
Artemis.bm catastrophe bond & ILS deal directory (1,311 deals, Dec 1996 – Aug 2026).

> Draft of the project's `CLAUDE.md`. It is not named that yet because
> `CLAUDE.md` sits in the protected team-knowledge layer and this project is not
> on the team-brain write allowlist.

## Data licensing — read before committing anything

**This repository is public.** Artemis states that reproduction or publication of
its directory content without permission is not permitted, that use within a
commercial product or for profit requires a licence, and that AI-related use of
its data requires a commercial licence.

Therefore `raw/` (cached HTML) and `data/*.csv` (tables extracted from it) are
**gitignored deliberately**. The code that produces them is tracked; their
content is not. Do not remove those ignore rules. Re-fetch locally instead:
every script is cache-first via `src/fetch.py`.

## Running

```bash
python3 -m venv .venv && ./.venv/bin/python -m pip install -e .
./.venv/bin/python tests/test_golden.py      # 153 checks, no network
```

`fetch.py` is cache-first, sets a descriptive User-Agent, and sleeps 2s before
any real request. Nothing re-fetches a page already in `raw/`.

## Parser architecture

Source pages have two content tiers with **different temporal meaning**, because
Artemis writes deal prose incrementally as a deal comes to market:

- **Tier 1** — the "At a glance" `<ul>`. A real key/value block, read
  structurally, confidence `high`. Holds **final** terms.
- **Tier 2** — the "Full details" prose plus appended `Update N:` blocks.
  Regex-mined, confidence `medium`/`low`. Preserves **launch-time** terms.

**Tier 2 never writes into a Tier-1 field. Tier 1 constrains Tier 2:** with one
tranche the deal size *is* the tranche size (take it from Tier 1); with several,
no tranche may equal the deal total.

Every field is a record, never a bare value:
`{value, confidence, method, evidence, flags}`. Confidence is graded by *how the
value was obtained*, not how plausible it looks. A source placeholder
("Unknown", "?", "Not issued") maps to `value=None` at confidence `high` — we
are confident the source is silent — with `raw_value` preserved.

Risk metrics (expected loss, attachment/exhaustion probability, spread) are
**tranche-level** and live in `tranches.csv`, never on the deal row. Putting
them on the deal row silently reports tranche 1 as the whole deal.

## Invariants (`src/validate.py`)

Cross-field checks catch a class of error per-field confidence cannot see: every
value individually plausible, the relationships wrong.

| family | check |
|---|---|
| cross-source | detail page size/sponsor/date agree with `index.csv` |
| parts vs whole | tranche sizes sum to the deal size, at launch and final |
| arithmetic | `EL ≤ attachment probability`; `conditional_severity ≤ 1` |
| ordering | `exhaustion ≤ EL ≤ attachment`; maturity after issue |
| economics | spread must exceed EL, else the note loses money in expectation |
| self-description | prose stating "four tranches" must yield four |

`conditional_severity = EL / attachment_probability` — the share of the layer
that burns once it is hit.

## Crawl order is a correctness requirement

`data/queue.csv` is family-grouped and **chronologically ascending**. Artemis
prose cites *predecessor* deals ("the notes issued by Ursa Re in 2014, which
priced at 5%"), so a deal must be parsed only after its older siblings, whose
values are then known and can be attributed rather than guessed.

Programme generations must be merged before grouping — "Windmill I/II/III Re",
"Kilimanjaro Re/II/III", "Sanders Re III" — or one programme splits into several
and the sibling registry is empty exactly where it is needed.

## Known gaps

- **Sentence segmentation.** `re.split(r"(?<=\.)\s+", ...)` fires on
  abbreviations: 34 mid-sentence splits across 28 cached pages ("U.S.", "Ltd.",
  "Inc."). Every sentence-scoped rule runs on fragments when it does.
- **Unlabelled multi-tranche deals.** Some pages state a tranche count but never
  describe the tranches (Trinity Re 1998, Mosaic Re II 1999, ResRe 2010's
  "Classes 1 to 3"). These yield one row plus `tranche_count_understated`.
  The per-tranche data does not exist on the page; do not fabricate rows.
- **Tier-2 sparsity before ~2010.** Artemis did not publish EL, attachment
  probability or spread for older deals. Any EL/spread time series effectively
  starts around 2010. This is data availability, not parser failure.
- **Fill rates track deal privacy, not era.** Non-private deals read 9/9 on
  Tier 1 regardless of decade; private/cat-bond-lite deals (Seaside Re, Eclipse
  Re, Artex Axcell — ~128 deals in two families alone) trip placeholders on
  sponsor, agents, modeller and trigger. Triage by `deal_is_private`.

## Conventions

- Golden tests over cached fixtures before any regex surgery. Every bug so far
  came from a parser calibrated on a single page.
- Prefer an honest `None` over a plausible wrong value; delete weak fallback
  patterns rather than repairing them.
- Where a source reveals a value's history (launch → final, guidance → priced),
  keep the earlier value, the delta, and the stated reason — not just the
  endpoint.
