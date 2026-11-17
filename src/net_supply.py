"""Net market supply: our reconstruction vs Artemis's own issued/outstanding.

    issued(y)       Tier-1 sizes summed by issue year        (index.csv, complete)
    outstanding(y)  deal-level roll-forward                  (roll_forward.py)

Artemis publishes the same two series on its issued-and-outstanding dashboard,
aggregated from the same directory. Matching them validates the parse end to
end; every residual must be nameable (scope, FX, unstated terms) or it is a
parse bug.

Known scope difference, inherited from the count validator: the dashboards
exclude mortgage ILS, while index.csv is the full directory. We therefore
compare twice -- full index, and excluding a name-listed set of mortgage ILS
programmes -- and the residual should collapse in the second run.

Currency: a size stated in EUR, GBP, CAD or NZD with no parenthetical USD
equivalent is converted at the monthly average rate of its issue month from
`src/fx_monthly_usd.csv` (ECB reference rates; Bank of England for GBP; the
file header cites both). `convert_size` is the one derivation; it returns the
USD figure, the basis it rests on, and the local amount and currency so the
original is never lost. A deal whose month has no rate is returned with a
None USD value and basis `fx_rate_missing`, never summed as dollars and never
silently dropped: callers report it.

Outstanding principal used to be approximated here (issue + 3 years where no
maturity was stated, settled losses subtracted at the loss date and the full
size subtracted again at maturity). That double subtraction ran 2.4 to 4.9bn
low in 2020-2026 and is gone: the stock now comes from `roll_forward.py`, a
deal-level ledger with netted write-downs, extensions and recoveries, the
TRACE maturity of the bridged CUSIPs where the companion analysis repository
provides one (`roll_forward.TRACE_DEFAULT`; `build(trace_path=None)` runs
without it), and a flagged imputed term for the rest.

Outputs stay local (data derived from Artemis): data/net_supply.csv,
plots/net_supply.png.
"""

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fetch import fetch, _cache_path                     # noqa: E402
from parse_deal import _money_to_number, unit_missing, _currency, MONTHS  # noqa: E402

DASH = ("https://www.artemis.bm/dashboard/"
        "catastrophe-bonds-ils-issued-and-outstanding-by-year/")

# Mortgage ILS programmes, by issuer name. Identified by programme because
# index.csv carries no peril column; sponsors are ambiguous (Arch sponsors
# property cat too), programme names are not.
MORTGAGE_RE = re.compile(
    r"bellemeade|oaktown|eagle re|radnor|home re|triangle re|"
    r"cherry blossom|greystone|sierra ltd|splitrock", re.IGNORECASE)

FX_TABLE = ROOT / "src" / "fx_monthly_usd.csv"
_FX_CACHE = None
MONTH_RE = re.compile(r"(" + MONTHS + r")[a-z]*\.?\s+(\d{4})", re.IGNORECASE)
MONTH_NUM = {m: i for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


def load_fx():
    """{(currency, 'YYYY-MM'): USD per unit} from the tracked monthly table."""
    global _FX_CACHE
    if _FX_CACHE is None:
        t = pd.read_csv(FX_TABLE, comment="#", dtype={"month": str, "currency": str})
        _FX_CACHE = {(r.currency, r.month): float(r.usd_per_unit)
                     for r in t.itertuples(index=False)}
    return _FX_CACHE


def issue_month(date_text):
    """'Nov 2005' / 'November 2005' / '12 Dec 2013' / '2005-11' -> '2005-11'."""
    s = str(date_text or "")
    m = MONTH_RE.search(s)
    if m:
        return "%s-%02d" % (m.group(2), MONTH_NUM[m.group(1)[:3].lower()])
    m = re.search(r"\b(\d{4})-(\d{2})\b", s)
    return "%s-%s" % (m.group(1), m.group(2)) if m else None


def convert_size(size_text, date_text):
    """Size cell + issue date -> one dict, the single USD derivation.

    usd_m            USD millions, or None
    basis            usd | usd_equiv | usd_converted | fx_rate_missing |
                     unit_missing | excluded
    local_m          the stated amount in its own currency (millions), if any
    currency         ISO code of that currency
    fx_usd_per_unit  rate applied, only for usd_converted
    fx_month         issue month the rate was looked up for
    """
    usd, basis = usd_millions(size_text)
    s = str(size_text or "").strip()
    ccy = _currency(s) if basis not in ("excluded", "unit_missing") else None
    out = {"usd_m": usd, "basis": basis, "local_m": None, "currency": ccy,
           "fx_usd_per_unit": None, "fx_month": None}
    if basis == "usd_equiv":
        # Keep the stated local amount beside the publisher's own USD figure.
        n = _money_to_number(re.sub(r"\(.*?\)", "", s))
        out["local_m"] = n / 1e6 if n else None
        return out
    if basis != "non_usd_unconverted":
        return out
    out["local_m"] = usd           # usd_millions read the local figure as-is
    out["usd_m"] = None
    month = issue_month(date_text)
    rate = load_fx().get((ccy, month)) if (ccy and month) else None
    out["fx_month"] = month
    if rate is None:
        out["basis"] = "fx_rate_missing"
        return out
    out.update(basis="usd_converted", fx_usd_per_unit=rate,
               usd_m=out["local_m"] * rate if out["local_m"] is not None else None)
    return out


def dashboard_series():
    h = fetch(DASH)
    cats = re.search(r"categories\s*:\s*\[(.*?)\]", h, re.S)
    years = [int(y) for y in re.findall(r"['\"](\d{4})['\"]", cats.group(1))]
    out = {"year": years}
    for m in re.finditer(r"name\s*:\s*['\"]([^'\"]+)['\"].*?data\s*:\s*\[(.*?)\]",
                         h, re.S):
        name = m.group(1).lower().replace(" ", "_").replace(".", "")
        vals = []
        for v in m.group(2).split(","):
            v = v.strip().strip("'\"")
            vals.append(float(v) if re.match(r"^-?[\d.]+$", v) else None)
        if len(vals) == len(years):
            out["artemis_" + name] = vals
    return pd.DataFrame(out)


def usd_millions(size_text):
    """Size cell -> USD millions. Prefers a parenthetical USD equivalent."""
    s = str(size_text).strip()
    if not s or s.lower() in ("not issued", "unknown", "?", "tbc", "n/a"):
        return None, "excluded"
    par = re.search(r"\(\s*\$([\d,.]+)\s*(m|million|bn|billion)?\s*\)", s)
    if par:
        n = _money_to_number("$" + par.group(1) + (par.group(2) or ""))
        return (n / 1e6 if n else None), "usd_equiv"
    if unit_missing(s):
        return None, "unit_missing"         # "$473.18" (Radnor 2019-1)
    if s.startswith("$") or s.upper().startswith("US$"):
        n = _money_to_number(s)
        return (n / 1e6 if n else None), "usd"
    n = _money_to_number(s)              # EUR/GBP/word forms: unconverted
    return (n / 1e6 if n else None), "non_usd_unconverted"


def issued_by_year(exclude_mortgage):
    """Tier-1 sizes by issue year from index.csv, on a USD basis."""
    idx = pd.read_csv(ROOT / "data" / "index.csv", keep_default_na=False, dtype=str)
    idx["year"] = idx.date_text.str[-4:].astype(int)
    if exclude_mortgage:
        idx = idx[~idx.issuer_name.str.contains(MORTGAGE_RE)]
    conv = [convert_size(sz, dt) for sz, dt in zip(idx.size_text, idx.date_text)]
    idx["usd_m"] = [c["usd_m"] for c in conv]
    idx["fx"] = [c["basis"] for c in conv]
    idx["local_m"] = [c["local_m"] for c in conv]
    issued = idx.groupby("year").usd_m.sum(min_count=1).rename("our_issued")
    conv_rows = idx[idx.fx == "usd_converted"]
    miss_rows = idx[idx.fx == "fx_rate_missing"]
    stats = {"n_deals": len(idx),
             "n_converted": len(conv_rows),
             "converted_local_m": conv_rows.local_m.sum(),
             "converted_usd_m": conv_rows.usd_m.sum(),
             "n_fx_missing": len(miss_rows),
             "fx_missing_local_m": miss_rows.local_m.sum()}
    return issued, stats


def build(exclude_mortgage, trace_path="auto"):
    """Issued by year joined to the roll-forward's stock and flows."""
    import roll_forward as rf
    issued, stats = issued_by_year(exclude_mortgage)
    book, losses, flows = rf.build(exclude_mortgage=exclude_mortgage, trace_path=trace_path)
    yearly = rf.outstanding_by_year(flows).set_index("year")
    t = pd.DataFrame(index=range(int(issued.index.min()), int(rf.AS_OF[:4]) + 1))
    t = t.join(issued).join(yearly[["repaid", "written_down", "recovered", "outstanding", "measured_at"]]
                            .rename(columns={"repaid": "our_repaid", "written_down": "our_written_down",
                                             "recovered": "our_recovered", "outstanding": "our_outstanding"}))
    cov = rf.coverage(book).set_index("maturity_source").share_pct
    stats.update({"book_deals": len(book),
                  "stated_maturities": int((book.maturity_source == "stated").sum()),
                  "trace_maturities": int((book.maturity_source == "trace").sum()),
                  "pct_dollars_stated_or_derived": float(cov.get("stated", 0) + cov.get("derived_from_term", 0)),
                  "pct_dollars_known": float(cov.get("stated", 0) + cov.get("derived_from_term", 0) + cov.get("trace", 0)),
                  "trace_path": book.attrs.get("trace_path")})
    return t.reset_index().rename(columns={"index": "year"}), stats


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--trace-maturities", default="auto", metavar="PATH",
                    help="the analysis repository's bridge.csv; default: the sibling checkout when present")
    ap.add_argument("--no-trace-maturities", action="store_true")
    args = ap.parse_args()
    trace_path = None if args.no_trace_maturities else args.trace_maturities
    theirs = dashboard_series()
    for label, excl in [("full index", False), ("excluding mortgage ILS", True)]:
        ours, stats = build(excl, trace_path=trace_path)
        cmpd = theirs.merge(ours, on="year", how="inner")
        cmpd["issued_diff"] = cmpd.our_issued - cmpd.artemis_issued
        cmpd["out_diff"] = cmpd.our_outstanding - cmpd.artemis_outstanding
        print("\n=== %s  (%d deals, %d stated maturities, %d TRACE maturities%s; %.1f%% of issued "
              "dollars with a stated or term-derived maturity, %.1f%% with one of those or TRACE; "
              "%d non-USD deals converted at issue-month rates, "
              "%.0fm local -> $%.0fm; %d with no rate, %.0fm local, excluded from sums) ==="
              % (label, stats["n_deals"], stats["stated_maturities"], stats["trace_maturities"],
                 " from %s" % stats["trace_path"] if stats["trace_path"] else " (off)",
                 stats["pct_dollars_stated_or_derived"], stats["pct_dollars_known"], stats["n_converted"],
                 stats["converted_local_m"], stats["converted_usd_m"], stats["n_fx_missing"],
                 stats["fx_missing_local_m"]))
        print("  mean |issued diff|:      $%6.0fm   (their mean issued $%.0fm)"
              % (cmpd.issued_diff.abs().mean(), cmpd.artemis_issued.mean()))
        print("  mean |outstanding diff|: $%6.0fm   (their mean outst. $%.0fm)"
              % (cmpd.out_diff.abs().mean(), cmpd.artemis_outstanding.mean()))
        print("  worst issued years:")
        w = cmpd.reindex(cmpd.issued_diff.abs().sort_values(ascending=False).index)
        for _, r in w.head(4).iterrows():
            print("     %d  ours %8.0f  theirs %8.0f  diff %+7.0f"
                  % (r.year, r.our_issued, r.artemis_issued, r.issued_diff))
        print("  outstanding, 2019 onward (ours / theirs / diff):")
        for _, r in cmpd[cmpd.year >= 2019].iterrows():
            print("     %d  %8.0f  %8.0f  %+7.0f   (measured at %s)"
                  % (r.year, r.our_outstanding, r.artemis_outstanding, r.out_diff, r.measured_at))
        if excl:
            cmpd.to_csv(ROOT / "data" / "net_supply.csv", index=False)
            print("\nwrote data/net_supply.csv")


if __name__ == "__main__":
    main()
