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
