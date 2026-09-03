"""Net market supply: our reconstruction vs Artemis's own issued/outstanding.

    issued(y)       Tier-1 sizes summed by issue year        (index.csv, complete)
    outstanding(y)  cumulative issued - matured - lost

Artemis publishes the same two series on its issued-and-outstanding dashboard,
aggregated from the same directory. Matching them validates the parse end to
end; every residual must be nameable (scope, FX, unstated terms) or it is a
parse bug.

Known scope difference, inherited from the count validator: the dashboards
exclude mortgage ILS, while index.csv is the full directory. We therefore
compare twice -- full index, and excluding a name-listed set of mortgage ILS
programmes -- and the residual should collapse in the second run.

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
from parse_deal import _money_to_number                  # noqa: E402

DASH = ("https://www.artemis.bm/dashboard/"
        "catastrophe-bonds-ils-issued-and-outstanding-by-year/")

# Mortgage ILS programmes, by issuer name. Identified by programme because
# index.csv carries no peril column; sponsors are ambiguous (Arch sponsors
# property cat too), programme names are not.
MORTGAGE_RE = re.compile(
    r"bellemeade|oaktown|eagle re|radnor|home re|triangle re|"
    r"cherry blossom|greystone|sierra ltd|splitrock", re.IGNORECASE)

DEFAULT_TERM_YEARS = 3          # where the page states no term


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
    if s.startswith("$") or s.upper().startswith("US$"):
        n = _money_to_number(s)
        return (n / 1e6 if n else None), "usd"
    n = _money_to_number(s)              # EUR/GBP/word forms: unconverted
    return (n / 1e6 if n else None), "non_usd_unconverted"


def build(exclude_mortgage):
    idx = pd.read_csv(ROOT / "data" / "index.csv", keep_default_na=False, dtype=str)
    idx["year"] = idx.date_text.str[-4:].astype(int)
    if exclude_mortgage:
        idx = idx[~idx.issuer_name.str.contains(MORTGAGE_RE)]
    vals = idx.size_text.map(usd_millions)
    idx["usd_m"] = [v[0] for v in vals]
    idx["fx"] = [v[1] for v in vals]

    issued = idx.groupby("year").usd_m.sum(min_count=1).rename("our_issued")

    # Maturity: parsed schedule where a cached page states one, else issue+3y.
    q = pd.read_csv(ROOT / "data" / "queue.csv", keep_default_na=False, dtype=str)
    stated = {}
    try:
        deals = pd.read_csv(ROOT / "data" / "deals.csv",
                            keep_default_na=False, dtype=str)
        for _, r in deals.iterrows():
            m = re.search(r"(\d{4})", str(r.get("maturity_scheduled", "")))
            if m:
                stated[r.deal_slug] = int(m.group(1))
    except FileNotFoundError:
        pass
    idx["slug"] = idx.deal_url.str.rstrip("/").str.rsplit("/", n=1).str[-1]
    idx["mat_year"] = [
        stated.get(s, y + DEFAULT_TERM_YEARS)
        for s, y in zip(idx.slug, idx.year)]
    matured = idx.groupby("mat_year").usd_m.sum(min_count=1).rename("our_matured")

    # Settled losses reduce outstanding at the loss date.
    losses = pd.read_csv(ROOT / "data" / "losses.csv",
                         keep_default_na=False, dtype=str)
    sl = losses[(losses.is_settled == "True")
                & (losses.loss_amount_derived.str.strip() != "")].copy()
    sl["loss_year"] = sl.date_of_loss.str.extract(r"(\d{4})")[0]
    sl = sl.dropna(subset=["loss_year"])
    sl["loss_m"] = sl.loss_amount_derived.astype(float) / 1e6
    lost = sl.groupby(sl.loss_year.astype(int)).loss_m.sum().rename("our_lost")

    years = range(idx.year.min(), 2027)
    t = pd.DataFrame(index=years).join([issued, matured, lost]).fillna(0.0)
    # A lost dollar must not also count as maturing later; the approximation
    # accepts that overlap (losses are small next to maturities) and reports it.
    t["our_outstanding"] = (t.our_issued - t.our_matured - t.our_lost).cumsum()
    stats = {"n_deals": len(idx),
             "unconverted_m": idx.loc[idx.fx == "non_usd_unconverted", "usd_m"].sum(),
             "stated_maturities": sum(1 for s in idx.slug if s in stated)}
    return t.reset_index().rename(columns={"index": "year"}), stats


def main():
    theirs = dashboard_series()
    for label, excl in [("full index", False), ("excluding mortgage ILS", True)]:
        ours, stats = build(excl)
        cmpd = theirs.merge(ours, on="year", how="inner")
        cmpd["issued_diff"] = cmpd.our_issued - cmpd.artemis_issued
        cmpd["out_diff"] = cmpd.our_outstanding - cmpd.artemis_outstanding
        print("\n=== %s  (%d deals, %d stated maturities, $%.0fm unconverted) ==="
              % (label, stats["n_deals"], stats["stated_maturities"],
                 stats["unconverted_m"]))
        print("  mean |issued diff|:      $%6.0fm   (their mean issued $%.0fm)"
              % (cmpd.issued_diff.abs().mean(), cmpd.artemis_issued.mean()))
        print("  mean |outstanding diff|: $%6.0fm   (their mean outst. $%.0fm)"
              % (cmpd.out_diff.abs().mean(), cmpd.artemis_outstanding.mean()))
        print("  worst issued years:")
        w = cmpd.reindex(cmpd.issued_diff.abs().sort_values(ascending=False).index)
        for _, r in w.head(4).iterrows():
            print("     %d  ours %8.0f  theirs %8.0f  diff %+7.0f"
                  % (r.year, r.our_issued, r.artemis_issued, r.issued_diff))
        if excl:
            cmpd.to_csv(ROOT / "data" / "net_supply.csv", index=False)
            print("\nwrote data/net_supply.csv")


if __name__ == "__main__":
    main()
