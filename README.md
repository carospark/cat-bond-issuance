# Catastrophe Bond Issuance

Structured extraction of the public catastrophe bond and ILS deal directory
(1996–present), built as the issuance and identifier layer for later analysis
of capital flows into and out of cat bond funds.

**Status: active. The parser works and is measured; the analysis is not built.**

---

## The problem this solves

Deal pages look like a table and behave like prose. Each page has a structured
summary block and a narrative body, and they carry *different* information:

- The **summary block** is kept current and holds **final** terms.
- The **body** is written incrementally as a deal comes to market, so it
  preserves the **launch-time** terms and every revision after them, appended
  as update blocks.

That gap is not an inconsistency to reconcile away — it is signal. The
difference between a deal's launch size and its final size is a measure of
investor demand, and the same shape recurs in pricing (initial guidance →
narrowed guidance → settled spread). A parser that keeps only the final value
silently discards the measurement.

Almost every hard problem here follows from that: which of several numbers on a
page is *this* deal's size, which belongs to one of its tranches, which belongs
to a predecessor deal being cited comparatively, and which is not a size at all
but an attachment point, a deductible, or a loss layer.

## Design

**Two tiers, with the structured one constraining the prose one.** Values mined
from the body never overwrite a value read from the summary block. Where the
summary is authoritative it is used directly; where several prose candidates
compete it is used to *rule them out*.

**Every field carries its provenance**, never a bare value:

```
{value, confidence, method, evidence, flags}
```

Confidence is graded by *how the value was obtained*, not by how plausible it
looks — a deterministic structural read is not the same as a regex with two
candidates and a tie-break rule. Source placeholders map to `None` at high
confidence: "the source is silent" and "our parser failed" are different facts
and must not look alike.

**Risk metrics are tranche-level, not deal-level.** Expected loss, attachment
and exhaustion probability and spread describe a tranche. Holding them on the
deal row silently reports one tranche as the whole deal.

**Cross-field invariants**, because per-field confidence is structurally blind
to a class of error where every value is individually plausible and only the
*relationships* are wrong:

| family | check |
|---|---|
| cross-source | the same deal is published twice; size, sponsor and date must agree |
| parts vs whole | tranche sizes sum to the deal size, at launch and at final |
| arithmetic | expected loss ≤ attachment probability; conditional severity ≤ 1 |
| ordering | exhaustion ≤ expected loss ≤ attachment; maturity after issue |
| self-description | text stating "four tranches" must yield four |

**Constraint selection.** Where several typed candidates exist for a tranche,
the parts-vs-whole invariant helps *choose* the answer rather than only check
it afterwards. Amounts are first classified by kind — size, attachment,
exhaustion, deductible, layer, payout — so a loss level is excluded
structurally rather than by a veto written for one phrasing.

**Order is a correctness requirement.** Pages cite predecessor deals, so the
crawl runs family-by-family, chronologically ascending, and programme
generations are merged first. A sibling's known values are then available to
attribute a figure rather than guess at it.

An honest `None` is always preferred to a plausible wrong value.

## Establishing correctness

- **1,759 assertions**, all offline against cached fixtures, including exact
  expected values, a table of *known-wrong* values that must never reappear,
  and unit tests for individual predicates.
- **Mutation testing.** Every guard is verified by reintroducing the bug it
  covers and confirming the suite goes red. Guards that stayed green were
  deleted or rewritten — several looked meaningful and were not.
- **Five rounds of independent adversarial review**, which found defects the
  test suite did not. Reports are in `REVIEW_ROUND*.md`.
- **Random-sample benchmarking.** Accuracy is measured on deals drawn uniformly
  at random with a fixed seed, not on the hand-picked pages the parser was
  developed against — those showed a violation rate roughly a third of the true
  one, because they were exactly the pages already fixed.

## A note on data

**No source data is in this repository, deliberately.** The upstream directory
prohibits reproduction without a licence, and licensed research exports used
for validation carry stricter terms still. Cached pages, extracted tables and
vendor payloads are all gitignored; only the code that produces them is
tracked. Every script is cache-first and rate-limited, and the pipeline runs
entirely offline once populated.

## Layout

```
src/parse_index.py       the directory index -> one row per deal
src/parse_deal.py        deal pages -> deal and tranche records with provenance
src/mentions.py          typed money mentions and constraint selection
src/validate.py          cross-field invariants
src/sibling_registry.py  figures belonging to a predecessor deal
src/build_queue.py       crawl order: family-grouped, chronological
src/build_tables.py      flat deal and tranche projections
src/random_sample.py     fixed-seed accuracy benchmark
tests/test_golden.py     the assertion suite
```

## Setup

Python ≥ 3.9.

```bash
python3 -m venv .venv && ./.venv/bin/python -m pip install -e .
./.venv/bin/python tests/test_golden.py
```

## Validation: annual deal counts

A parser smoke test compares unique deal URLs per issue year against the
transaction-count series published in the source's own cumulative-issuance
dashboard. It validates counts only, deliberately — before currency, size,
tranche or prose parsing can obscure a basic crawl failure.

```bash
./.venv/bin/python src/validate_annual_deal_counts.py
```

Outputs are local and gitignored. The dashboard excludes mortgage ILS while the
parsed directory is complete, so a positive scope gap is expected; a deficit
means the parse is missing deals and exits non-zero.

## External source archive

The tracked inventory, access notes and pull status are in
[`data/MANIFEST.md`](data/MANIFEST.md).

```bash
./.venv/bin/python src/pull_tier1_sources.py
```

Publisher payloads, parsed snapshots, checksums and pull logs are written under
`data/raw/` and are gitignored. Licensed exports are archived separately and
must not be redistributed; the manifest records their tables, query IDs, row
counts, coverage and checksums.

## Scope

The directory measures **primary-market issuance**. It does not contain
subscriptions, redemptions, secondary trading or fund AUM, so it cannot on its
own answer a question about fund flows — that requires joining fund NAV and
return series, where

```
AUM change = investor net flow + investment performance + FX
```

What this repository does produce is the issuance and identifier layer that
such a join needs, plus primary-market demand proxies: upsize share, final
spread against guidance midpoint, and gross versus net issuance.
