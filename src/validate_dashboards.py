"""Validate parsed series against the publisher's own dashboard charts.

One comparison per chart, each saved as a CSV table plus one combined plot:

    data/validation_dashboards/issuance.csv       Tier-1 sizes by year
    data/validation_dashboards/trigger_mix.csv    Tier-1 trigger shares by year
    data/validation_dashboards/el_spread.csv      tranche EL & spread averages
    data/validation_dashboards/size_change.csv    launch->final deltas by quarter
    plots/validation_dashboards.png

All outputs are derived from Artemis data and stay gitignored; this script is
the tracked, reproducible part. Every number reported in conversation should be
re-derivable by running this.
"""

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fetch import fetch                                  # noqa: E402
from parse_deal import _pct_to_float                     # noqa: E402
import net_supply as ns                                  # noqa: E402

OUT = ROOT / "data" / "validation_dashboards"
MON = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}


def series(slug, year_categories=True):
    h = fetch("https://www.artemis.bm/dashboard/%s/" % slug)
    cat_m = re.search(r"categories\s*:\s*\[(.*?)\]", h, re.S)
    cats = re.findall(r"['\"]([^'\"]+)['\"]", cat_m.group(1))
    out = {}
    for m in re.finditer(r"name\s*:\s*['\"]([^'\"]+)['\"].*?data\s*:\s*\[(.*?)\]",
                         h, re.S):
        vals = []
        for v in m.group(2).split(","):
            v = v.strip().strip("'\"")
            vals.append(float(v) if re.match(r"^-?[\d.]+$", v) else None)
        if len(vals) == len(cats) and m.group(1) not in out:
            out[m.group(1)] = vals
    df = pd.DataFrame({"cat": cats, **out})
    if year_categories:
        df["cat"] = df.cat.astype(int)
    return df


def load_deals():
    d = pd.read_csv(ROOT / "data" / "deals.csv", keep_default_na=False, dtype=str)
    d["year"] = d.date_of_issue.str.extract(r"(\d{4})")[0].astype(float)
    d["usd_m"] = [ns.usd_millions(s)[0] for s in d["size"].fillna("")]

    def quarter(s):
        m = re.match(r"([A-Z][a-z]{2})[a-z]*\s+(\d{4})", str(s))
        if m and m.group(1) in MON:
            return "Q%d %s" % ((MON[m.group(1)] - 1) // 3 + 1, m.group(2))
        return None
    d["q"] = d.date_of_issue.map(quarter)
    return d


def cmp_issuance(d):
    t = series("catastrophe-bonds-ils-issued-and-outstanding-by-year")
    mort = d[~d.deal_slug.str.contains(ns.MORTGAGE_RE)]
    ours = mort.groupby("year").usd_m.sum().rename("our_issued_m")
    c = t.rename(columns={"cat": "year"}).set_index("year")[
        ["Issued"]].join(ours).dropna()
    c.columns = ["artemis_issued_m", "our_issued_m"]
    c["diff_m"] = c.our_issued_m - c.artemis_issued_m
    return c.reset_index()


def cmp_trigger(d):
    t = series("cat-bonds-ils-by-trigger-by-year")
    ours = d.dropna(subset=["usd_m", "year"]).copy()
    ours["trig"] = ours.apply(
        lambda r: r.trigger_type or r.get("trigger_type__raw", "") or "Unknown",
        axis=1)
    tot = ours.groupby("year").usd_m.sum()
    rows = []
    for name in ["Indemnity", "Parametric", "Industry loss index", "Unknown"]:
        share = (ours[ours.trig.str.strip().str.lower() == name.lower()]
                 .groupby("year").usd_m.sum() / tot * 100)
        c = (t.rename(columns={"cat": "year"}).set_index("year")[[name]]
             .join(share.rename("ours")).dropna())
        for y, r in c.iterrows():
            rows.append({"year": y, "trigger": name,
                         "artemis_pct": r[name], "our_pct": r.ours})
    return pd.DataFrame(rows)


def cmp_el_spread(d):
    t = series("cat-bonds-ils-expected-loss-coupon")
    tr = pd.read_csv(ROOT / "data" / "tranches.csv",
                     keep_default_na=False, dtype=str)
    tr = tr.merge(d[["deal_slug", "year"]], on="deal_slug")
    tr["el"] = tr.expected_loss.map(_pct_to_float)
    tr["sp"] = tr.spread_risk_margin.map(_pct_to_float)
    g = tr.groupby("year").agg(our_el=("el", "mean"), n_el=("el", "count"),
                               our_spread=("sp", "mean"), n_spread=("sp", "count"))
    c = (t.rename(columns={"cat": "year"}).set_index("year")
         [["Avg. expected Loss", "Avg. spread"]].join(g)
         .dropna(subset=["our_el"]).reset_index())
    c = c.rename(columns={"Avg. expected Loss": "artemis_el",
                          "Avg. spread": "artemis_spread"})
    return c


def cmp_size_change(d):
    """Artemis: "we track the initial target size for each catastrophe bond
    that comes to market and the final confirmed issuance size at settlement,
    then work out the average percentage move ... across all cat bond issues
    during the period", "where we have the information" (dashboard text).

    Two readings, both emitted. `ours_changed_mean` averages only deals whose
    prose states a launch size different from the final; it drops every deal
    that settled at its target, so it runs high. `ours_tracked_mean` also
    counts a deal as 0% when a launch size was stated AND at least one later
    size update restated it -- the deals Artemis demonstrably tracked through
    marketing. Counting EVERY deal with a launch state as 0% overshoots the
    other way (2026-09-15: -14pp, corr 0.33): a single stated size on a page
    written after pricing is the final, not a tracked target, and private
    deals are the bulk of them.
    """
    t = series("catastrophe-bond-offering-size-changes", year_categories=False)
    t = t.rename(columns={"cat": "q", "% Size change": "artemis_pct"})
    d = d.copy()
    d["delta"] = d.size_change.str.extract(r"'delta_pct':\s*(-?[\d.]+)")[0].astype(float)
    states = d.size_history.map(lambda h: re.findall(r"'state':\s*'([^']+)'", h or ""))
    d["tracked_zero"] = d.delta.isna() & states.map(
        lambda L: "launch" in L and len(L) >= 2)
    sub = d[d.q.isin(set(t.q))]
    a = sub.dropna(subset=["delta"]).groupby("q").agg(
        ours_changed_mean=("delta", "mean"), n_changed=("delta", "size"))
    tracked = sub[sub.delta.notna() | sub.tracked_zero]
    b = tracked.assign(delta=tracked.delta.fillna(0.0)).groupby("q").agg(
        ours_tracked_mean=("delta", "mean"), n_tracked=("delta", "size"))
    c = t.set_index("q").join(a).join(b).reset_index()
    c["qsort"] = [int(q.split()[1]) * 4 + int(q[1]) for q in c.q]
    return c.sort_values("qsort").drop(columns="qsort")


def main():
    OUT.mkdir(exist_ok=True)
    d = load_deals()
    results = {
        "issuance": cmp_issuance(d),
        "trigger_mix": cmp_trigger(d),
        "el_spread": cmp_el_spread(d),
        "size_change": cmp_size_change(d),
    }
    for name, df in results.items():
        df.to_csv(OUT / (name + ".csv"), index=False)
        print("wrote %s (%d rows)" % (OUT / (name + ".csv"), len(df)))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(13, 9))

    c = results["issuance"]
    ax[0, 0].bar(c.year - 0.2, c.artemis_issued_m / 1e3, 0.4,
                 color="#888", label="Artemis")
    ax[0, 0].bar(c.year + 0.2, c.our_issued_m / 1e3, 0.4,
                 color="#2b6cb0", label="ours")
    ax[0, 0].set_title("Issuance by year, $bn (ex-mortgage) — mean |diff| $%.0fm"
                       % c.diff_m.abs().mean())
    ax[0, 0].legend()

    for name, grp in results["trigger_mix"].groupby("trigger"):
        line, = ax[0, 1].plot(grp.year, grp.artemis_pct, lw=1.6, label=name)
        ax[0, 1].plot(grp.year, grp.our_pct, "--", lw=1.2, color=line.get_color())
    ax[0, 1].set_title("Trigger mix, % of issuance (solid Artemis, dashed ours)")
    ax[0, 1].legend(fontsize=7)

    c = results["el_spread"]
    ax[1, 0].plot(c.year, c.artemis_el, "k-", label="Artemis EL")
    ax[1, 0].plot(c.year, c.our_el, "k--", label="our EL")
    ax[1, 0].plot(c.year, c.artemis_spread, "-", color="#2b6cb0", label="Artemis spread")
    ax[1, 0].plot(c.year, c.our_spread, "--", color="#2b6cb0", label="our spread")
    post = c[c.year >= 2012]
    ax[1, 0].set_title("Avg EL & spread, %% — EL corr %.2f, spread biased high"
                       % post.our_el.corr(post.artemis_el))
    ax[1, 0].legend(fontsize=8)

    c = results["size_change"]
    x = range(len(c))
    ax[1, 1].plot(x, c.artemis_pct, "k-", label="Artemis % size change")
    ax[1, 1].plot(x, c.ours_changed_mean, "--", color="#c0392b",
                  label="our mean delta (changed deals only)")
    ax[1, 1].plot(x, c.ours_tracked_mean, "--", color="#2b6cb0",
                  label="our mean delta (tracked deals, unchanged = 0)")
    ax[1, 1].set_xticks(list(x)[::4])
    ax[1, 1].set_xticklabels(c.q[::4], rotation=45, fontsize=7)
    # No hard-coded verdict: the numbers ARE the verdict. Changed-only was
    # corr 0.10-0.22 before the 2026-09-14 launch-size fixes and 0.72 after,
    # running +11pp; the tracked-deals reading is what closes the level.
    def fit(col):
        v = c.dropna(subset=[col])
        return v.artemis_pct.corr(v[col]), (v[col] - v.artemis_pct).mean()
    ax[1, 1].set_title("Offering size change by quarter — changed-only corr %.2f (%+.0fpp), "
                       "tracked corr %.2f (%+.0fpp)"
                       % (fit("ours_changed_mean") + fit("ours_tracked_mean")), fontsize=9)
    ax[1, 1].legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(ROOT / "plots" / "validation_dashboards.png", dpi=110)
    print("wrote plots/validation_dashboards.png")


if __name__ == "__main__":
    main()
