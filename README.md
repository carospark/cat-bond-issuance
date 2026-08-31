# Catastrophe Bond Fund Flow

Analysis of capital flows into and out of catastrophe bond funds.

## Setup

Requires Python >= 3.9.

```bash
pip install -e .
```

This installs the local `pkg` package and all dependencies.

## Layout

```
data/          input and intermediate data files
plots/         generated figures
src/pkg/       reusable analysis functions
src/scripts/   numbered pipeline scripts, run from the repository root
```

## Running the pipeline

Run all scripts from the **repository root**:

```bash
python src/scripts/0.load_data.py
```

## Validation 1: annual deal counts

The first parser smoke test compares unique Deal Directory URLs per issue year
with the transaction-count series embedded in Artemis's cumulative-issuance
dashboard. It intentionally validates counts only, before currency, size,
tranche, or prose parsing can obscure a basic crawl failure.

```bash
./.venv/bin/python src/validate_annual_deal_counts.py
```

It writes two local, gitignored outputs:

- `data/annual_deal_count_validation.csv` — year-by-year counts, differences,
  and `MATCH` / `SCOPE_GAP` / `FAIL_MISSING` status.
- `plots/annual_deal_count_validation.png` — dashboard counts against the full
  parsed directory.

Artemis excludes mortgage ILS from this dashboard, while `data/index.csv`
contains the full directory. Therefore a positive `SCOPE_GAP` is expected;
`FAIL_MISSING` means the parsed directory has fewer deals than the dashboard
and makes the command exit non-zero.

## Tier 1 external-source archive

The tracked source inventory, access notes, coverage, and current pull status
are in [`data/MANIFEST.md`](data/MANIFEST.md). To refresh all automatable Tier 1
sources and the snapshot-only Artemis manager directory:

```bash
./.venv/bin/python src/pull_tier1_sources.py
```

Raw publisher payloads, parsed snapshots, checksums, and pull logs are written
under `data/raw/` and are gitignored. The Swiss Re Bloomberg histories remain a
manual licensed export; see the manifest for exact tickers and the ticker-name
discrepancy that must be checked at the terminal.
